# Ubiquitous Language

| Term | Definition |
| --- | --- |
| Paragraph | One caller-supplied, non-empty text unit. It is not automatically split by this project. |
| Chinese-character equivalent | The paragraph-length unit: one Han character counts as one unit; two ASCII letters or digits count as one unit; whitespace and punctuation do not count. |
| Synthesis text | The text sent to the TTS model. It may contain a substitution for a rare or unsupported target character. |
| Verification target | The text that candidate audio must match for CER acceptance. It defaults to the synthesis text when no explicit expected transcription is supplied. |
| Expected transcription | An optional explicit verification target in a benchmark case or generation request. |
| Voice mode | The mutually exclusive synthesis intent: auto voice, voice cloning, or voice design. |
| Reference voice | A private audio recording plus its supplied verbatim transcript, used only by voice-cloning mode. |
| Candidate audio | The audio produced by one synthesis attempt from the synthesis text. |
| Baseline | The first candidate produced for a benchmark case, without selection by verification. |
| Verification | Transcribing candidate audio and comparing it with the verification target under the configured text-comparison policy. |
| Character error rate (CER) | The edit distance divided by the normalized verification target length. The target is normalized to simplified Chinese; whitespace, punctuation, and emoji sequences are ignored on both sides. |
| Accepted output | A candidate whose T2S-normalized CER is below the acceptance threshold. |
| Best-effort output | The candidate with the lowest CER when no candidate was accepted before the attempt limit. It is explicitly not an accepted output. |
| Closed loop | The bounded process that creates candidates, verifies each one, and selects an accepted or best-effort output. |
| Benchmark corpus | Version-controlled text cases used to compare a baseline with the closed loop. |
