"""Server-side citation validation: every cited chunk id must exist, per §8.3."""

import re
from dataclasses import dataclass
from uuid import UUID

_CITATION_PATTERN = re.compile(r"\[chunk:([0-9a-fA-F-]{36})\]")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ValidatedAnswer:
    """The result of validating an LLM answer's citations."""

    text: str
    valid_chunk_ids: list[UUID]
    citation_density: float
    has_valid_citations: bool


def validate_citations(answer_text: str, valid_chunk_ids: set[UUID]) -> ValidatedAnswer:
    """Parse citation markers, strip invalid ones, and compute citation density.

    Args:
        answer_text: The raw LLM output.
        valid_chunk_ids: Chunk ids that were actually provided as context —
            any citation outside this set is a hallucination and is stripped.

    Returns:
        The cleaned text (invalid citation markers removed), the valid
        chunk ids actually cited (first-appearance order, deduplicated),
        the citation density (valid citations / sentence count), and
        whether any valid citation survived. Callers must treat
        `has_valid_citations=False` as a signal to convert the answer to
        a refusal (§8.3).
    """
    found_valid: list[UUID] = []
    seen: set[UUID] = set()

    def _replace(match: re.Match[str]) -> str:
        try:
            chunk_id = UUID(match.group(1))
        except ValueError:
            return ""
        if chunk_id not in valid_chunk_ids:
            return ""
        if chunk_id not in seen:
            seen.add(chunk_id)
            found_valid.append(chunk_id)
        return match.group(0)

    cleaned_text = _CITATION_PATTERN.sub(_replace, answer_text)
    sentence_count = len([s for s in _SENTENCE_SPLIT_PATTERN.split(cleaned_text.strip()) if s])
    citation_density = len(found_valid) / sentence_count if sentence_count else 0.0

    return ValidatedAnswer(
        text=cleaned_text,
        valid_chunk_ids=found_valid,
        citation_density=citation_density,
        has_valid_citations=bool(found_valid),
    )
