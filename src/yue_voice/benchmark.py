"""Reproducible baseline-versus-closed-loop benchmark reporting."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import statistics
import time
from typing import Any

from .models import GenerationResult, SynthesisRequest
from .service import ClosedLoopGenerator


class BenchmarkError(ValueError):
    """Raised when a benchmark corpus cannot produce valid paragraph cases."""


def load_jsonl_cases(path: Path) -> list[dict[str, str]]:
    """Load public benchmark cases from UTF-8 JSON Lines."""
    cases: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise BenchmarkError(f"invalid JSON on line {line_number} of {path}: {error.msg}") from error
        case_id = str(item.get("id", "")).strip()
        text = str(item.get("text", "")).strip()
        if not case_id or not text:
            raise BenchmarkError(f"case on line {line_number} needs non-empty id and text")
        cases.append({"id": case_id, "text": text})
    if not cases:
        raise BenchmarkError(f"no non-empty cases found in {path}")
    return cases


def load_paragraph_cases(path: Path) -> list[dict[str, str]]:
    """Split a local text file on blank lines and omit empty paragraphs."""
    paragraphs = re.split(r"\r?\n[\t ]*\r?\n", path.read_text(encoding="utf-8"))
    cases = [
        {"id": f"{path.stem}-{index:03d}", "text": paragraph.strip()}
        for index, paragraph in enumerate(paragraphs, start=1)
        if paragraph.strip()
    ]
    if not cases:
        raise BenchmarkError(f"no non-empty paragraphs found in {path}")
    return cases


def run_benchmark(
    generator: ClosedLoopGenerator,
    cases: list[dict[str, str]],
    template: SynthesisRequest,
    *,
    artifact_root: Path | str = Path("artifacts"),
    keep_candidates: bool = False,
) -> tuple[dict[str, Any], Path, Path]:
    """Use each closed loop's first attempt as its fair single-generation baseline."""
    benchmark_id = datetime.now(UTC).strftime("benchmark-%Y%m%dT%H%M%S%fZ")
    benchmark_directory = Path(artifact_root).expanduser().resolve() / benchmark_id
    benchmark_directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    records: list[dict[str, Any]] = []

    for index, case in enumerate(cases):
        request = replace(
            template,
            text=case["text"],
            seed=(template.seed + index * 100) if template.seed is not None else None,
        )
        result = generator.generate(
            request,
            artifact_root=benchmark_directory / "runs",
            keep_candidates=keep_candidates,
        )
        records.append(_record_case(case["id"], result))

    report = {
        "benchmark_id": benchmark_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "definition": {
            "baseline": "The first candidate in each closed loop before verification selection.",
            "verified": "The candidate selected by T2S-normalized CER verification after at most ten attempts.",
        },
        "case_count": len(records),
        "summary": _summarize(records),
        "cases": records,
        "total_seconds": time.monotonic() - started,
    }
    report_path = benchmark_directory / "report.json"
    markdown_path = benchmark_directory / "report.md"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return report, report_path, markdown_path


def _record_case(case_id: str, result: GenerationResult) -> dict[str, Any]:
    baseline = result.attempts[0] if result.attempts else None
    return {
        "id": case_id,
        "baseline_cer": baseline.cer if baseline else None,
        "baseline_accepted": baseline.accepted if baseline else False,
        "verified_cer": result.selected_cer,
        "verified_accepted": result.accepted,
        "attempt_count": len(result.attempts),
        "total_seconds": result.total_seconds,
        "selected_attempt": result.selected_attempt,
        "result_path": str(result.result_path),
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, float | int | None]:
    baseline_cers = [record["baseline_cer"] for record in records if record["baseline_cer"] is not None]
    verified_cers = [record["verified_cer"] for record in records if record["verified_cer"] is not None]
    return {
        "baseline_mean_cer": _mean(baseline_cers),
        "verified_mean_cer": _mean(verified_cers),
        "baseline_acceptance_rate": _rate(records, "baseline_accepted"),
        "verified_acceptance_rate": _rate(records, "verified_accepted"),
        "mean_attempts": _mean([record["attempt_count"] for record in records]),
        "mean_case_seconds": _mean([record["total_seconds"] for record in records]),
    }


def _mean(values: list[float | int]) -> float | None:
    return statistics.fmean(values) if values else None


def _rate(records: list[dict[str, Any]], key: str) -> float:
    return sum(bool(record[key]) for record in records) / len(records) if records else 0.0


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    percent = lambda value: "N/A" if value is None else f"{value:.2%}"
    decimal = lambda value: "N/A" if value is None else f"{value:.3f}"
    rows = [
        "# Benchmark report",
        "",
        f"- Benchmark: `{report['benchmark_id']}`",
        f"- Cases: {report['case_count']}",
        "- Baseline: first candidate before closed-loop selection.",
        "- Verified: selected candidate after T2S-normalized CER checks, limited to ten attempts.",
        "",
        "| Metric | Baseline | Verified |",
        "| --- | ---: | ---: |",
        f"| Mean CER | {percent(summary['baseline_mean_cer'])} | {percent(summary['verified_mean_cer'])} |",
        f"| Acceptance rate (< 5% CER) | {percent(summary['baseline_acceptance_rate'])} | {percent(summary['verified_acceptance_rate'])} |",
        "",
        f"Mean attempts: {decimal(summary['mean_attempts'])}  ",
        f"Mean case time: {decimal(summary['mean_case_seconds'])} seconds",
        "",
        "| Case | Baseline CER | Verified CER | Attempts | Selected attempt | Accepted |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for record in report["cases"]:
        rows.append(
            "| {id} | {baseline} | {verified} | {attempts} | {selected} | {accepted} |".format(
                id=record["id"],
                baseline=percent(record["baseline_cer"]),
                verified=percent(record["verified_cer"]),
                attempts=record["attempt_count"],
                selected=record["selected_attempt"] or "N/A",
                accepted="yes" if record["verified_accepted"] else "no",
            )
        )
    return "\n".join(rows) + "\n"
