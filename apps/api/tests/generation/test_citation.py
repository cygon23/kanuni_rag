"""Tests for citation validation: parsing, stripping invalid ids, density, refusal signal."""

from uuid import uuid4

from kanuni_api.generation.citation import validate_citations


def test_valid_citation_survives_and_is_counted() -> None:
    """A citation whose id is in the valid set must survive and be reported."""
    chunk_id = uuid4()
    text = f"Banks must hold minimum capital. [chunk:{chunk_id}]"

    result = validate_citations(text, {chunk_id})

    assert result.has_valid_citations is True
    assert result.valid_chunk_ids == [chunk_id]
    assert f"[chunk:{chunk_id}]" in result.text


def test_invalid_citation_is_stripped() -> None:
    """A citation for an id not in the valid set (hallucinated) must be removed."""
    real_id = uuid4()
    hallucinated_id = uuid4()
    text = f"Some claim. [chunk:{hallucinated_id}] Another claim. [chunk:{real_id}]"

    result = validate_citations(text, {real_id})

    assert result.valid_chunk_ids == [real_id]
    assert str(hallucinated_id) not in result.text
    assert f"[chunk:{real_id}]" in result.text


def test_zero_valid_citations_signals_refusal() -> None:
    """An answer with no surviving valid citations must report has_valid_citations=False."""
    text = f"A claim with a made-up citation. [chunk:{uuid4()}]"

    result = validate_citations(text, {uuid4()})

    assert result.has_valid_citations is False
    assert result.valid_chunk_ids == []


def test_duplicate_citations_are_deduplicated_in_order() -> None:
    """Citing the same chunk twice must appear once in valid_chunk_ids, first-seen order."""
    first_id = uuid4()
    second_id = uuid4()
    text = f"Claim A. [chunk:{first_id}] Claim B. [chunk:{second_id}] Claim C. [chunk:{first_id}]"

    result = validate_citations(text, {first_id, second_id})

    assert result.valid_chunk_ids == [first_id, second_id]


def test_citation_density_is_valid_citations_over_sentence_count() -> None:
    """citation_density must equal valid citation count divided by sentence count."""
    chunk_id = uuid4()
    text = f"First sentence. [chunk:{chunk_id}] Second sentence. Third sentence."

    result = validate_citations(text, {chunk_id})

    assert result.citation_density == 1 / 3


def test_malformed_citation_marker_is_stripped_without_raising() -> None:
    """A citation-shaped marker that isn't a valid UUID must be stripped, not raise.

    36 hex-charset characters with no hyphens matches the marker's regex
    shape but fails `UUID()` parsing (wrong grouping) — exercising the
    ValueError branch specifically, not just a regex non-match.
    """
    text = "A claim. [chunk:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa]"

    result = validate_citations(text, set())

    assert result.has_valid_citations is False


def test_answer_with_no_citations_at_all_has_zero_density() -> None:
    """An answer with no citation markers at all must have zero density and no valid citations."""
    result = validate_citations("Just plain text with no citations.", {uuid4()})

    assert result.has_valid_citations is False
    assert result.citation_density == 0.0
