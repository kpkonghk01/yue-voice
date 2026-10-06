"""Strict text normalization, comparison, and paragraph-length measurement."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True, slots=True)
class TextComparison:
    """The strict-CER comparison result for a source and ASR transcript."""

    normalized_source: str
    normalized_transcription: str
    distance: int
    cer: float


def normalize_for_strict_cer(text: str) -> str:
    """Normalize case and width while ignoring whitespace and punctuation only."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith(("P", "Z"))
    )


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2EBEF
        or 0x30000 <= codepoint <= 0x323AF
    )


def chinese_equivalent_units(text: str) -> float:
    """Return the configured mixed-text length in Chinese-character equivalents.

    Han characters and non-ASCII letters/digits each count as one unit. Two ASCII
    letters/digits count as one unit. Whitespace and punctuation do not count.
    """
    half_units = 0
    for character in unicodedata.normalize("NFKC", text):
        category = unicodedata.category(character)
        if category.startswith(("P", "Z")):
            continue
        if _is_han(character):
            half_units += 2
        elif character.isascii() and character.isalnum():
            half_units += 1
        elif category.startswith(("L", "N")):
            half_units += 2
    return half_units / 2


def levenshtein_distance(source: str, target: str) -> int:
    """Compute character edit distance without adding a runtime dependency."""
    if source == target:
        return 0
    if not source:
        return len(target)
    if not target:
        return len(source)

    if len(source) < len(target):
        source, target = target, source

    previous = list(range(len(target) + 1))
    for source_index, source_character in enumerate(source, start=1):
        current = [source_index]
        for target_index, target_character in enumerate(target, start=1):
            insertion = current[target_index - 1] + 1
            deletion = previous[target_index] + 1
            replacement = previous[target_index - 1] + (source_character != target_character)
            current.append(min(insertion, deletion, replacement))
        previous = current
    return previous[-1]


def compare_strict_cer(source: str, transcription: str) -> TextComparison:
    """Compare source and transcription using the project's strict-CER policy."""
    normalized_source = normalize_for_strict_cer(source)
    normalized_transcription = normalize_for_strict_cer(transcription)
    if not normalized_source:
        raise ValueError("source text is empty after strict-CER normalization")

    distance = levenshtein_distance(normalized_source, normalized_transcription)
    return TextComparison(
        normalized_source=normalized_source,
        normalized_transcription=normalized_transcription,
        distance=distance,
        cer=distance / len(normalized_source),
    )
