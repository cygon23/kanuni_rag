"""Chunking stage: layout-aware splitting into ~450-token chunks with 60-token overlap."""

import io
import re
from dataclasses import dataclass

import pdfplumber
import structlog

from kanuni_ingest.models import DocumentChunk, ExtractedDocument, ExtractedPage

logger = structlog.get_logger()

_PART_PATTERN = re.compile(r"^PART\s+([IVXLCDM]+)\b", re.IGNORECASE)
_CLAUSE_PATTERN = re.compile(r"^(\d{1,3})\.[-\s(]")
# Approximate tokens-per-word for a BPE-style tokenizer. Documented
# approximation: exact counts would require loading the embedding model's
# tokenizer just to count tokens, which this stage deliberately avoids.
_TOKENS_PER_WORD = 1.33


@dataclass
class _Segment:
    """One indivisible unit of chunk content: a whole clause's text, or a whole table."""

    text: str
    section_ref: str | None
    page_start: int
    page_end: int
    is_table: bool = False


def _approximate_token_count(text: str) -> int:
    """Estimate token count from word count.

    Args:
        text: The text to estimate.

    Returns:
        An approximate token count, at least 1 for non-empty text.
    """
    word_count = len(text.split())
    return max(1, round(word_count * _TOKENS_PER_WORD))


def _build_section_ref(part: str | None, clause: str | None) -> str | None:
    """Compose a human-readable section reference from the current part/clause.

    Args:
        part: The current Part numeral (e.g. `"III"`), if known.
        clause: The current clause/regulation number (e.g. `"12"`), if known.

    Returns:
        A string like `"Part III, s.12"`, or `None` if neither is known.
    """
    if part and clause:
        return f"Part {part}, s.{clause}"
    if clause:
        return f"s.{clause}"
    if part:
        return f"Part {part}"
    return None


def _render_markdown_table(rows: list[list[str | None]]) -> str | None:
    """Render extracted table rows as a Markdown table.

    Args:
        rows: Table rows as returned by `pdfplumber`'s `extract_tables`.

    Returns:
        A Markdown table string, or `None` if the table has no header row.
    """
    cleaned_rows = [[(cell or "").strip() for cell in row] for row in rows]
    if not cleaned_rows:
        return None
    header, *body = cleaned_rows
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _extract_tables_by_page(pdf_bytes: bytes) -> dict[int, list[str]]:
    """Extract every table on every page as Markdown, keyed by 1-indexed page number.

    Args:
        pdf_bytes: The raw PDF bytes.

    Returns:
        A mapping of page number to the Markdown tables found on that page.
    """
    tables_by_page: dict[int, list[str]] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            markdown_tables = [
                markdown
                for rows in page.extract_tables()
                if rows and (markdown := _render_markdown_table(rows))
            ]
            if markdown_tables:
                tables_by_page[page_index + 1] = markdown_tables
    return tables_by_page


def _split_into_segments(
    pages: list[ExtractedPage], tables_by_page: dict[int, list[str]]
) -> list[_Segment]:
    """Group page text into one segment per clause, plus one segment per table.

    Scans line by line rather than on blank-line paragraph breaks: PDF text
    extraction commonly emits one line per visual line with no blank line
    between list-style clauses (e.g. a table-of-contents-style
    "ARRANGEMENT OF REGULATIONS" block), so relying on blank lines would
    miss most clause boundaries. Grouping by clause (rather than by line)
    is what guarantees a clause is never split across chunk boundaries
    downstream: each segment here is later packed as a single indivisible
    unit.

    Args:
        pages: Extracted pages in document order.
        tables_by_page: Markdown tables keyed by page number.

    Returns:
        Segments in document order.
    """
    segments: list[_Segment] = []
    current_part: str | None = None
    current_clause: str | None = None
    buffer_lines: list[str] = []
    buffer_page_start: int | None = None
    buffer_page_end: int | None = None

    def flush_buffer() -> None:
        nonlocal buffer_page_start, buffer_page_end
        if buffer_lines:
            segments.append(
                _Segment(
                    text="\n".join(buffer_lines),
                    section_ref=_build_section_ref(current_part, current_clause),
                    page_start=buffer_page_start or 1,
                    page_end=buffer_page_end or 1,
                )
            )
            buffer_lines.clear()
        buffer_page_start = None
        buffer_page_end = None

    for page in pages:
        lines = [line.strip() for line in page.text.split("\n") if line.strip()]
        for line in lines:
            part_match = _PART_PATTERN.search(line)
            clause_match = _CLAUSE_PATTERN.match(line)

            if part_match and part_match.group(1) != current_part:
                flush_buffer()
                current_part = part_match.group(1)
            if clause_match and clause_match.group(1) != current_clause:
                flush_buffer()
                current_clause = clause_match.group(1)

            if buffer_page_start is None:
                buffer_page_start = page.page_number
            buffer_page_end = page.page_number
            buffer_lines.append(line)

        for table_markdown in tables_by_page.get(page.page_number, []):
            flush_buffer()
            segments.append(
                _Segment(
                    text=table_markdown,
                    section_ref=_build_section_ref(current_part, current_clause),
                    page_start=page.page_number,
                    page_end=page.page_number,
                    is_table=True,
                )
            )

    flush_buffer()
    return segments


def chunk_document(
    pdf_bytes: bytes,
    extracted: ExtractedDocument,
    *,
    target_tokens: int = 450,
    overlap_tokens: int = 60,
    language: str = "en",
) -> list[DocumentChunk]:
    """Split extracted text into layout-aware chunks, keeping clauses and tables intact.

    Splits on structural boundaries (Parts, numbered clauses/regulations)
    first, then packs whole clauses/tables into chunks up to `target_tokens`,
    carrying `overlap_tokens` worth of trailing clauses into the next chunk.
    A single table is never split, and a single clause is never split even
    if that means a chunk exceeds `target_tokens`.

    Args:
        pdf_bytes: The raw PDF bytes, re-opened here to extract tables.
        extracted: The stage-2 extraction result.
        target_tokens: Target chunk size in (approximate) tokens.
        overlap_tokens: Approximate token overlap between consecutive chunks.
        language: The parent document's language code, stamped onto every
            chunk (ADR 0004 — selects the sparse-index text-search config).

    Returns:
        Chunks in document order, each carrying a section reference and page range.
    """
    tables_by_page = _extract_tables_by_page(pdf_bytes)
    segments = _split_into_segments(extracted.pages, tables_by_page)

    chunks: list[DocumentChunk] = []
    current_segments: list[_Segment] = []
    current_tokens = 0

    def flush_chunk() -> None:
        if not current_segments:
            return
        content = "\n\n".join(segment.text for segment in current_segments)
        section_ref = next((s.section_ref for s in current_segments if s.section_ref), None)
        chunks.append(
            DocumentChunk(
                chunk_index=len(chunks),
                content=content,
                section_ref=section_ref,
                page_start=current_segments[0].page_start,
                page_end=current_segments[-1].page_end,
                token_count=current_tokens,
                language=language,
            )
        )

    for segment in segments:
        segment_tokens = _approximate_token_count(segment.text)

        if current_segments and current_tokens + segment_tokens > target_tokens:
            flush_chunk()
            overlap_segments: list[_Segment] = []
            overlap_count = 0
            for previous in reversed(current_segments):
                if previous.is_table:
                    break
                previous_tokens = _approximate_token_count(previous.text)
                if overlap_count + previous_tokens > overlap_tokens:
                    break
                overlap_segments.insert(0, previous)
                overlap_count += previous_tokens
            current_segments = overlap_segments
            current_tokens = overlap_count

        current_segments.append(segment)
        current_tokens += segment_tokens

    flush_chunk()
    return chunks
