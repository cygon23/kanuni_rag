"""Tests for the chunking stage: clause boundaries, tables, and overlap — real fixtures."""

from pathlib import Path

import pytest
from fakes import FakeOCREngine

from kanuni_ingest.stages.chunk import chunk_document
from kanuni_ingest.stages.extract import extract_document


@pytest.mark.asyncio
async def test_chunks_never_split_a_table(fixtures_dir: Path) -> None:
    """The capital adequacy regulation's First Schedule table must stay in one chunk."""
    pdf_bytes = (fixtures_dir / "bot-2023-capital-adequacy.pdf").read_bytes()
    extracted = await extract_document(pdf_bytes, ocr_engine=FakeOCREngine(), ocr_languages="eng")

    chunks = chunk_document(pdf_bytes, extracted)

    table_chunks = [
        chunk for chunk in chunks if "| S/No." in chunk.content or "|---" in chunk.content
    ]
    assert table_chunks, "expected at least one chunk to contain the rendered Markdown table"
    for chunk in table_chunks:
        assert "Fully-fledged Banks" in chunk.content
        assert "Mortgage Refinance Company" in chunk.content


@pytest.mark.asyncio
async def test_chunks_carry_page_ranges_within_document_bounds(fixtures_dir: Path) -> None:
    """Every chunk's page range must be within the document's actual page count."""
    pdf_bytes = (fixtures_dir / "bot-2014-licensing.pdf").read_bytes()
    extracted = await extract_document(pdf_bytes, ocr_engine=FakeOCREngine(), ocr_languages="eng")

    chunks = chunk_document(pdf_bytes, extracted)

    max_page = max(page.page_number for page in extracted.pages)
    assert chunks
    for chunk in chunks:
        assert 1 <= chunk.page_start <= chunk.page_end <= max_page


@pytest.mark.asyncio
async def test_chunk_indices_are_sequential(fixtures_dir: Path) -> None:
    """Chunks must be indexed 0..N-1 in document order."""
    pdf_bytes = (fixtures_dir / "bot-2014-licensing.pdf").read_bytes()
    extracted = await extract_document(pdf_bytes, ocr_engine=FakeOCREngine(), ocr_languages="eng")

    chunks = chunk_document(pdf_bytes, extracted)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


@pytest.mark.asyncio
async def test_chunks_carry_section_references(fixtures_dir: Path) -> None:
    """Most chunks of a clause-numbered regulation should carry a section_ref."""
    pdf_bytes = (fixtures_dir / "bot-2014-licensing.pdf").read_bytes()
    extracted = await extract_document(pdf_bytes, ocr_engine=FakeOCREngine(), ocr_languages="eng")

    chunks = chunk_document(pdf_bytes, extracted)

    chunks_with_section_ref = [chunk for chunk in chunks if chunk.section_ref is not None]
    assert len(chunks_with_section_ref) > len(chunks) / 2


@pytest.mark.asyncio
async def test_consecutive_chunks_overlap_when_a_document_exceeds_one_chunk(
    fixtures_dir: Path,
) -> None:
    """A long document should produce more than one chunk, with shared trailing content."""
    pdf_bytes = (fixtures_dir / "bot-2014-licensing.pdf").read_bytes()
    extracted = await extract_document(pdf_bytes, ocr_engine=FakeOCREngine(), ocr_languages="eng")

    chunks = chunk_document(pdf_bytes, extracted, target_tokens=450, overlap_tokens=60)

    assert len(chunks) > 1
    first_chunk_tail = chunks[0].content[-80:]
    assert (
        any(
            fragment in chunks[1].content for fragment in (first_chunk_tail, first_chunk_tail[-40:])
        )
        or chunks[0].content.split("\n\n")[-1] in chunks[1].content
    )


def test_single_clause_is_never_split_even_if_it_exceeds_target_tokens() -> None:
    """A pathologically long single clause must remain one chunk, not be truncated."""
    import fitz

    from kanuni_ingest.models import ExtractedDocument, ExtractedPage, ExtractionMethod

    long_clause = "1. " + " ".join(["word"] * 2000)
    blank_document = fitz.open()
    blank_document.new_page()
    pdf_bytes = blank_document.tobytes()
    blank_document.close()

    extracted = ExtractedDocument(
        pages=[
            ExtractedPage(
                page_number=1, text=long_clause, extraction_method=ExtractionMethod.NATIVE
            )
        ]
    )

    chunks = chunk_document(pdf_bytes, extracted, target_tokens=450, overlap_tokens=60)

    assert len(chunks) == 1
    assert chunks[0].token_count > 450
