"""Command-line interface for verified Cantonese paragraph synthesis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .benchmark import load_jsonl_cases, load_paragraph_cases, run_benchmark
from .engines import DEFAULT_CACHE_ROOT, load_engines
from .models import GenerationControls, SynthesisRequest, VoiceMode
from .service import ClosedLoopGenerator


DEFAULT_TTS_MODEL = "k2-fsa/OmniVoice"
DEFAULT_ASR_MODEL = "iic/SenseVoiceSmall"
DEFAULT_CORPUS = Path("benchmarks/cantonese.jsonl")


def build_parser() -> argparse.ArgumentParser:
    """Build the yue-voice CLI parser without importing or loading models."""
    parser = argparse.ArgumentParser(
        prog="yue-voice",
        description="Generate one Cantonese paragraph and verify it with SenseVoiceSmall.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate and verify one paragraph")
    _add_common_options(generate_parser)
    source = generate_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="One Cantonese paragraph to synthesize")
    source.add_argument("--text-file", type=Path, help="UTF-8 file containing one paragraph")
    expected = generate_parser.add_mutually_exclusive_group()
    expected.add_argument(
        "--expected-text",
        help="Optional CER verification target; it is not sent to the TTS model",
    )
    expected.add_argument(
        "--expected-text-file",
        type=Path,
        help="UTF-8 file containing the optional CER verification target",
    )
    generate_parser.add_argument(
        "--allow-best-effort",
        action="store_true",
        help="Exit successfully even when no candidate reached the strict CER threshold",
    )

    benchmark_parser = subparsers.add_parser(
        "benchmark", help="Compare each first candidate with the closed-loop result"
    )
    _add_common_options(benchmark_parser)
    benchmark_source = benchmark_parser.add_mutually_exclusive_group()
    benchmark_source.add_argument("--corpus", type=Path, help="UTF-8 JSONL benchmark corpus")
    benchmark_source.add_argument(
        "--text-file",
        type=Path,
        help="UTF-8 input split into non-empty benchmark paragraphs at blank lines",
    )

    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--model-cache-dir", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--device", help="Explicit model device, for example mps, cpu, or cuda:0")
    parser.add_argument("--tts-model", default=DEFAULT_TTS_MODEL)
    parser.add_argument("--asr-model", default=DEFAULT_ASR_MODEL)
    parser.add_argument("--mode", choices=[mode.value for mode in VoiceMode], default=VoiceMode.AUTO.value)
    parser.add_argument("--ref-audio", type=Path, help="Reference WAV/audio for clone mode")
    reference_text = parser.add_mutually_exclusive_group()
    reference_text.add_argument("--ref-text", help="Verbatim reference-audio transcript for clone mode")
    reference_text.add_argument("--ref-text-file", type=Path, help="UTF-8 reference transcript for clone mode")
    parser.add_argument("--instruct", help="Voice-design instruction for design mode")
    parser.add_argument("--seed", type=int, help="Initial random seed; later attempts increment it")
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--keep-candidates", action="store_true")
    parser.add_argument("--num-step", type=int, default=32)
    parser.add_argument("--guidance-scale", type=float, default=2.0)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--t-shift", type=float, default=0.1)
    parser.add_argument("--denoise", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--postprocess-output", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--layer-penalty-factor", type=float, default=5.0)
    parser.add_argument("--position-temperature", type=float, default=5.0)
    parser.add_argument("--class-temperature", type=float, default=0.0)


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ValueError(f"unable to read {path}: {error}") from error


def _request_from_args(args: argparse.Namespace, text: str) -> SynthesisRequest:
    reference_text = _read_utf8(args.ref_text_file) if args.ref_text_file else args.ref_text
    expected_text_file = getattr(args, "expected_text_file", None)
    expected_transcription = (
        _read_utf8(expected_text_file)
        if expected_text_file
        else getattr(args, "expected_text", None)
    )
    controls = GenerationControls(
        num_step=args.num_step,
        guidance_scale=args.guidance_scale,
        speed=args.speed,
        duration=args.duration,
        t_shift=args.t_shift,
        denoise=args.denoise,
        postprocess_output=args.postprocess_output,
        layer_penalty_factor=args.layer_penalty_factor,
        position_temperature=args.position_temperature,
        class_temperature=args.class_temperature,
    )
    return SynthesisRequest(
        text=text,
        expected_transcription=expected_transcription,
        voice_mode=VoiceMode(args.mode),
        reference_audio=args.ref_audio,
        reference_text=reference_text,
        instruct=args.instruct,
        controls=controls,
        seed=args.seed,
        max_attempts=args.max_attempts,
    )


def _generator_from_args(args: argparse.Namespace) -> ClosedLoopGenerator:
    engines = load_engines(
        cache_root=args.model_cache_dir,
        requested_device=args.device,
        tts_model_id=args.tts_model,
        asr_model_id=args.asr_model,
    )
    return ClosedLoopGenerator(
        engines.synthesizer,
        engines.verifier,
        metadata=engines.metadata,
    )


def run(argv: Sequence[str] | None = None) -> int:
    """Run one CLI command and return a process exit code."""
    args = build_parser().parse_args(argv)
    try:
        generator = _generator_from_args(args)
        if args.command == "generate":
            text = _read_utf8(args.text_file) if args.text_file else args.text
            result = generator.generate(
                _request_from_args(args, text),
                artifact_root=args.artifact_dir,
                keep_candidates=args.keep_candidates,
            )
            print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
            return 0 if result.accepted or args.allow_best_effort else 2

        if args.text_file:
            cases = load_paragraph_cases(args.text_file)
            source = str(args.text_file)
        else:
            corpus_path = args.corpus or DEFAULT_CORPUS
            cases = load_jsonl_cases(corpus_path)
            source = str(corpus_path)
        template = _request_from_args(args, str(cases[0]["text"]))
        report, report_path, markdown_path = run_benchmark(
            generator,
            cases,
            template,
            artifact_root=args.artifact_dir,
            keep_candidates=args.keep_candidates,
        )
        print(
            json.dumps(
                {
                    "source": source,
                    "report_path": str(report_path),
                    "markdown_path": str(markdown_path),
                    "summary": report["summary"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def main() -> None:
    """Console-script entry point."""
    raise SystemExit(run())
