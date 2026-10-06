"""CER normalization, comparison, and paragraph-length measurement."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import unicodedata


@dataclass(frozen=True, slots=True)
class TextComparison:
    """The T2S-normalized CER comparison result for a source and ASR transcript."""

    normalized_source: str
    normalized_transcription: str
    distance: int
    cer: float


def _is_emoji_component(character: str) -> bool:
    """Identify emoji code points and the joiners/modifiers that compose them."""
    codepoint = ord(character)
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x2300 <= codepoint <= 0x23FF
        or 0x2B00 <= codepoint <= 0x2BFF
        or codepoint in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}
        or codepoint in {0x200D, 0x20E3, 0xFE0E, 0xFE0F}
        or 0xE0020 <= codepoint <= 0xE007F
    )


def normalize_for_strict_cer(text: str) -> str:
    """Normalize text while ignoring punctuation, whitespace, and emoji components."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith(("P", "Z"))
        and not _is_emoji_component(character)
    )


@lru_cache(maxsize=1)
def _traditional_to_simplified_converter():
    """Load one process-wide OpenCC Traditional-to-Simplified converter."""
    from opencc import OpenCC

    return OpenCC("t2s")


def normalize_source_for_cer(text: str) -> str:
    """Normalize a requested paragraph and convert its Han text to simplified Chinese."""
    return _traditional_to_simplified_converter().convert(normalize_for_strict_cer(text))


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
    """Compare text with T2S-normalized source and emoji-free ASR transcription."""
    normalized_source = normalize_source_for_cer(source)
    normalized_transcription = normalize_for_strict_cer(transcription)
    if not normalized_source:
        raise ValueError("source text is empty after CER normalization")

    distance = levenshtein_distance(normalized_source, normalized_transcription)
    return TextComparison(
        normalized_source=normalized_source,
        normalized_transcription=normalized_transcription,
        distance=distance,
        cer=distance / len(normalized_source),
    )
