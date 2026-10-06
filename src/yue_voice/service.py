"""Bounded candidate generation, SenseVoice verification, and artifact reporting."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import time
from typing import Any

import soundfile as sound_file

from .engines import OmniVoiceSynthesizer, SenseVoiceVerifier, seed_everything
from .models import AttemptRecord, GenerationResult, SynthesisRequest
from .text import compare_strict_cer, normalize_for_strict_cer


class ClosedLoopGenerator:
    """Generate and verify a paragraph without ever silently accepting a fallback."""

    def __init__(
        self,
        synthesizer: OmniVoiceSynthesizer,
        verifier: SenseVoiceVerifier,
        *,
        metadata: dict[str, Any],
    ) -> None:
        self._synthesizer = synthesizer
        self._verifier = verifier
        self._metadata = metadata

    def generate(
        self,
        request: SynthesisRequest,
        *,
        artifact_root: Path | str = Path("artifacts"),
        keep_candidates: bool = False,
    ) -> GenerationResult:
        """Run at most ten verified attempts and persist the selected outcome."""
        length_units = request.validate()
        started = time.monotonic()
        run_id = self._run_id()
        run_directory = Path(artifact_root).expanduser().resolve() / run_id
        run_directory.mkdir(parents=True, exist_ok=False)
        result_path = run_directory / "result.json"
        candidate_directory = run_directory / "candidates"
        candidate_directory.mkdir()
        best_path = run_directory / ".best.wav"

        base_seed = request.seed if request.seed is not None else secrets.randbelow(2**31)
        seen_hashes: set[str] = set()
        attempts: list[AttemptRecord] = []
        best_attempt: AttemptRecord | None = None
        accepted_attempt: AttemptRecord | None = None

        for attempt_number in range(1, request.max_attempts + 1):
            seed = (base_seed + attempt_number - 1) % (2**31)
            candidate_path = candidate_directory / f"attempt-{attempt_number:02d}.wav"
            attempt = AttemptRecord(number=attempt_number, seed=seed)
            attempts.append(attempt)

            try:
                seed_everything(seed)
                generation_started = time.monotonic()
                audio, sample_rate = self._synthesizer.synthesize(request)
                sound_file.write(candidate_path, audio, sample_rate)
                attempt.generation_seconds = time.monotonic() - generation_started
                attempt.audio_sha256 = self._file_sha256(candidate_path)

                if attempt.audio_sha256 in seen_hashes:
                    attempt.error = "duplicate candidate audio; closed loop stopped before a redundant retry"
                    break
                seen_hashes.add(attempt.audio_sha256)

                verification_started = time.monotonic()
                attempt.transcription = self._verifier.transcribe(candidate_path)
                attempt.verification_seconds = time.monotonic() - verification_started
                comparison = compare_strict_cer(request.text, attempt.transcription)
                attempt.normalized_transcription = comparison.normalized_transcription
                attempt.cer = comparison.cer
                attempt.accepted = comparison.cer < request.cer_threshold

                if best_attempt is None or attempt.cer < (best_attempt.cer or float("inf")):
                    shutil.copy2(candidate_path, best_path)
                    best_attempt = attempt
                if attempt.accepted:
                    accepted_attempt = attempt
                    break
            except Exception as error:  # Preserve evidence, then allow a later seed to recover.
                attempt.error = f"{type(error).__name__}: {error}"

        selected_attempt = accepted_attempt or best_attempt
        output_path: Path | None = None
        if selected_attempt is not None and best_path.is_file():
            output_path = run_directory / "output.wav"
            best_path.replace(output_path)

        if not keep_candidates:
            shutil.rmtree(candidate_directory)
        elif candidate_directory.exists():
            for attempt in attempts:
                if attempt.number <= request.max_attempts:
                    path = candidate_directory / f"attempt-{attempt.number:02d}.wav"
                    if path.is_file():
                        attempt.candidate_path = path

        result = GenerationResult(
            run_id=run_id,
            requested_text=request.text,
            normalized_source=normalize_for_strict_cer(request.text),
            length_units=length_units,
            cer_threshold=request.cer_threshold,
            max_attempts=request.max_attempts,
            accepted=accepted_attempt is not None,
            selected_attempt=selected_attempt.number if selected_attempt else None,
            selected_cer=selected_attempt.cer if selected_attempt else None,
            output_path=output_path,
            result_path=result_path,
            attempts=attempts,
            total_seconds=time.monotonic() - started,
            metadata={**self._metadata, "seed_base": base_seed, "keep_candidates": keep_candidates},
        )
        result_path.write_text(
            json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return result

    @staticmethod
    def _run_id() -> str:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
