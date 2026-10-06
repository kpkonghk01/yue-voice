# ADR 0001: Bound closed-loop acceptance by strict CER

- **Status:** Accepted
- **Date:** 2026-10-06

## Context

A synthesis request can contain omissions or substitutions that are not observable from a successful model call alone. The project must make its acceptance rule visible and must not silently label a low-quality fallback as verified.

## Decision

For every paragraph, compare the requested text with the SenseVoice transcription using strict normalized character error rate (CER). A candidate is accepted only when its CER is strictly below 5%.

The closed loop makes at most ten attempts. If none is accepted, it selects the lowest-CER candidate as a best-effort output and reports `accepted: false`. Command-line use treats that outcome as a failure unless the caller explicitly allows best effort.

## Consequences

- Callers receive a usable fallback without confusing it for validated audio.
- The result records per-attempt evidence, so a quality claim can be audited.
- A later comparator may recognize traditional/simplified or phonetic equivalence, but it must be a separately named policy and cannot retroactively change strict-CER results.
