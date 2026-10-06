# Ubiquitous Language

| Term | Definition |
| --- | --- |
| Paragraph | One caller-supplied, non-empty text unit. It is not automatically split by this project. |
| Chinese-character equivalent | The paragraph-length unit: one Han character counts as one unit; two ASCII letters or digits count as one unit; whitespace and punctuation do not count. |
| Voice mode | The mutually exclusive synthesis intent: auto voice, voice cloning, or voice design. |
| Reference voice | A private audio recording plus its supplied verbatim transcript, used only by voice-cloning mode. |
| Candidate audio | The audio produced by one synthesis attempt for a paragraph. |
| Baseline | The first candidate produced for a benchmark case, without selection by verification. |
| Verification | Transcribing candidate audio and comparing it with the requested paragraph under the configured text-comparison policy. |
| Character error rate (CER) | The normalized character edit distance divided by the normalized source length. |
| Accepted output | A candidate whose strict CER is below the acceptance threshold. |
| Best-effort output | The candidate with the lowest CER when no candidate was accepted before the attempt limit. It is explicitly not an accepted output. |
| Closed loop | The bounded process that creates candidates, verifies each one, and selects an accepted or best-effort output. |
| Benchmark corpus | Version-controlled public text cases used to compare a baseline with the closed loop. |
