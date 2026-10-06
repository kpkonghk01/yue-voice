# ADR 0001: Bound closed-loop acceptance by T2S-normalized CER

- **Status:** Accepted
- **Date:** 2026-10-06

## Context

A synthesis request can contain omissions or substitutions that are not observable from a successful model call alone. The project must make its acceptance rule visible and must not silently label a low-quality fallback as verified.

SenseVoice frequently emits simplified Chinese and may include emoji components in a transcription. Treating these representation artifacts as speech errors prevents correctly spoken traditional-Chinese input from ever reaching the intended 5% threshold.

## Decision

For every paragraph, normalize punctuation, whitespace, and emoji components away. Convert only the requested source text from Traditional Chinese to Simplified Chinese with OpenCC `t2s`; leave the SenseVoice transcription in its emitted Han form. Compare the results with character error rate (CER). A candidate is accepted only when its CER is strictly below 5%.

The closed loop makes at most ten attempts. If none is accepted, it selects the lowest-CER candidate as a best-effort output and reports `accepted: false`. Command-line use treats that outcome as a failure unless the caller explicitly allows best effort.

## Consequences

- Traditional/simplified representation differences no longer mask spoken-text agreement.
- Emoji output from ASR does not create a spurious insertion or deletion.
- Callers receive a usable fallback without confusing it for validated audio.
- The result records per-attempt evidence, so a quality claim can be audited.
- Phonetic equivalence remains a separately named future policy and cannot retroactively change this T2S-normalized CER result.
