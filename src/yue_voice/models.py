"""Domain data structures for Cantonese synthesis and verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .text import chinese_equivalent_units


MAX_PARAGRAPH_UNITS = 180
STRICT_CER_THRESHOLD = 0.05
MAX_ATTEMPTS = 10


class VoiceMode(str, Enum):
    """The mutually exclusive voice selection modes supported by OmniVoice."""

    AUTO = "auto"
    CLONE = "clone"
    DESIGN = "design"


@dataclass(frozen=True, slots=True)
class GenerationControls:
    """Explicitly supported OmniVoice generation controls."""

    num_step: int = 32
    guidance_scale: float = 2.0
    speed: float = 1.0
    duration: float | None = None
    t_shift: float = 0.1
    denoise: bool = True
    postprocess_output: bool = True
    layer_penalty_factor: float = 5.0
    position_temperature: float = 5.0
    class_temperature: float = 0.0

    def validate(self) -> None:
        if self.num_step < 1:
            raise ValueError("num_step must be at least 1")
        if self.guidance_scale < 0:
            raise ValueError("guidance_scale must not be negative")
        if self.speed <= 0:
            raise ValueError("speed must be positive")
        if self.duration is not None and self.duration <= 0:
            raise ValueError("duration must be positive when provided")
        if self.t_shift < 0:
            raise ValueError("t_shift must not be negative")
        if self.layer_penalty_factor < 0:
            raise ValueError("layer_penalty_factor must not be negative")
        if self.position_temperature < 0 or self.class_temperature < 0:
            raise ValueError("generation temperatures must not be negative")


@dataclass(frozen=True, slots=True)
class TextLengthUnits:
    """Validated lengths for TTS input and its independent verification target."""

    synthesis_text: float
    verification_target: float


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    """One paragraph synthesis request and its bounded verification policy."""

    text: str
    expected_transcription: str | None = None
    voice_mode: VoiceMode = VoiceMode.AUTO
    reference_audio: Path | None = None
    reference_text: str | None = None
    instruct: str | None = None
    controls: GenerationControls = field(default_factory=GenerationControls)
    seed: int | None = None
    max_attempts: int = MAX_ATTEMPTS
    cer_threshold: float = STRICT_CER_THRESHOLD

    @property
    def verification_target(self) -> str:
        """Return the expected target, falling back to the text supplied to TTS."""
        return self.expected_transcription if self.expected_transcription is not None else self.text

    def validate(self) -> TextLengthUnits:
        """Validate both texts and return their Chinese-character-equivalent lengths."""
        synthesis_length = self._validate_paragraph("text", self.text)
        verification_length = self._validate_paragraph(
            "expected_transcription", self.verification_target
        )

        if not 1 <= self.max_attempts <= MAX_ATTEMPTS:
            raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS}")
        if not 0 < self.cer_threshold < 1:
            raise ValueError("cer_threshold must be between 0 and 1")
        self.controls.validate()

        mode = VoiceMode(self.voice_mode)
        if mode is VoiceMode.AUTO:
            if self.reference_audio or self.reference_text or self.instruct:
                raise ValueError("auto voice mode does not accept reference audio, text, or instruct")
        elif mode is VoiceMode.CLONE:
            if not self.reference_audio or not self.reference_text or not self.reference_text.strip():
                raise ValueError("clone mode requires both reference_audio and reference_text")
            if not self.reference_audio.is_file():
                raise ValueError(f"reference audio does not exist: {self.reference_audio}")
            if self.instruct:
                raise ValueError("clone mode does not accept instruct")
        elif mode is VoiceMode.DESIGN:
            if not self.instruct or not self.instruct.strip():
                raise ValueError("design mode requires instruct")
            if self.reference_audio or self.reference_text:
                raise ValueError("design mode does not accept reference audio or text")

        return TextLengthUnits(
            synthesis_text=synthesis_length,
            verification_target=verification_length,
        )

    @staticmethod
    def _validate_paragraph(field_name: str, text: str) -> float:
        if not text.strip():
            raise ValueError(f"{field_name} must contain at least one non-whitespace character")

        length_units = chinese_equivalent_units(text)
        if length_units == 0:
            raise ValueError(f"{field_name} must contain letters, digits, or Han characters")
        if length_units > MAX_PARAGRAPH_UNITS:
            raise ValueError(
                f"{field_name} is {length_units:g} Chinese-character equivalents; "
                f"the maximum is {MAX_PARAGRAPH_UNITS}"
            )
        return length_units


@dataclass(slots=True)
class AttemptRecord:
    """Evidence captured for one candidate-generation attempt."""

    number: int
    seed: int
    audio_sha256: str | None = None
    transcription: str | None = None
    normalized_transcription: str | None = None
    cer: float | None = None
    accepted: bool = False
    generation_seconds: float | None = None
    verification_seconds: float | None = None
    candidate_path: Path | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "seed": self.seed,
            "audio_sha256": self.audio_sha256,
            "transcription": self.transcription,
            "normalized_transcription": self.normalized_transcription,
            "cer": self.cer,
            "accepted": self.accepted,
            "generation_seconds": self.generation_seconds,
            "verification_seconds": self.verification_seconds,
            "candidate_path": str(self.candidate_path) if self.candidate_path else None,
            "error": self.error,
        }


@dataclass(slots=True)
class GenerationResult:
    """The final closed-loop outcome plus auditable per-attempt evidence."""

    run_id: str
    synthesis_text: str
    expected_transcription: str | None
    normalized_source: str
    synthesis_length_units: float
    verification_target_length_units: float
    cer_threshold: float
    max_attempts: int
    accepted: bool
    selected_attempt: int | None
    selected_cer: float | None
    output_path: Path | None
    result_path: Path
    attempts: list[AttemptRecord]
    total_seconds: float
    metadata: dict[str, Any]

    @property
    def has_audio(self) -> bool:
        return self.output_path is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "synthesis_text": self.synthesis_text,
            "expected_transcription": self.expected_transcription,
            "normalized_source": self.normalized_source,
            "synthesis_length_units": self.synthesis_length_units,
            "verification_target_length_units": self.verification_target_length_units,
            "cer_threshold": self.cer_threshold,
            "max_attempts": self.max_attempts,
            "accepted": self.accepted,
            "selected_attempt": self.selected_attempt,
            "selected_cer": self.selected_cer,
            "output_path": str(self.output_path) if self.output_path else None,
            "result_path": str(self.result_path),
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "total_seconds": self.total_seconds,
            "metadata": self.metadata,
        }
