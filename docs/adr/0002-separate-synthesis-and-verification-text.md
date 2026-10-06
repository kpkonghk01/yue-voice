# ADR 0002: Separate synthesis text from verification target

- **Status:** Accepted
- **Date:** 2026-10-06

## Context

A rare or unsupported character can cause OmniVoice to omit or mispronounce a sound. Callers may need to replace that character in the text sent to TTS, while still requiring ASR verification against the original intended text.

Using a single `text` field for both purposes would either prevent pronunciation substitutions or incorrectly accept a transcript that matches only the substitute character.

## Decision

A request has a required synthesis text and an optional expected transcription. TTS always receives the synthesis text. The expected transcription, when supplied, becomes the verification target for T2S-normalized CER, candidate selection, acceptance, and best-effort ranking. When it is absent, the synthesis text remains the verification target for backward-compatible behavior.

Both texts must be non-empty and fit the same 180 Chinese-character-equivalent limit. Result evidence records synthesis text, optional expected transcription, and the normalized verification target.

## Consequences

- A caller can use a pronounceable substitute without lowering the intended verification standard.
- A benchmark report exposes both the spoken input and the target, making substitutions auditable.
- Acceptance now intentionally evaluates semantic target text rather than blindly echoing the exact TTS input.
- Future phonetic equivalence remains a separate comparator policy.
