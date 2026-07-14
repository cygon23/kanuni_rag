"""Tests for regex_extraction: verified against the real fixture PDFs' actual text."""

from datetime import date
from pathlib import Path

import fitz
import pytest

from kanuni_ingest.regex_extraction import (
    classify_relation_keyword,
    extract_issued_date,
    extract_reference_number,
    find_cited_reference_numbers,
)


def _first_page_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as document:
        return str(document[0].get_text())


def test_extract_reference_number_from_licensing_regulation(fixtures_dir: Path) -> None:
    """The 2014 licensing regulation's own gazette number should be found."""
    text = _first_page_text(fixtures_dir / "bot-2014-licensing.pdf")

    assert extract_reference_number(text) == "G.N. No. 297"


def test_extract_issued_date_from_licensing_regulation(fixtures_dir: Path) -> None:
    """The 2014 licensing regulation's publication date should be parsed."""
    text = _first_page_text(fixtures_dir / "bot-2014-licensing.pdf")

    assert extract_issued_date(text) == date(2014, 8, 22)


def test_extract_reference_number_handles_missing_period_after_no(fixtures_dir: Path) -> None:
    """'GOVERNMENT NOTICE NO 13' (no period after NO) should still be found."""
    text = _first_page_text(fixtures_dir / "bot-2023-licensing-amendment.pdf")

    assert extract_reference_number(text) == "G.N. No. 13"
    assert extract_issued_date(text) == date(2023, 1, 20)


def test_find_cited_reference_numbers_detects_amendment_citation(fixtures_dir: Path) -> None:
    """The amendment document cites 'G.N. No. 297 of 2014' — the regulation it amends."""
    text = _first_page_text(fixtures_dir / "bot-2023-licensing-amendment.pdf")

    assert find_cited_reference_numbers(text) == ["G.N. No. 297"]


def test_own_reference_number_is_not_confused_with_a_cited_document() -> None:
    """A citation ('...GN. No. 999 of 1999...') must never be read as this document's own number.

    Regression test: `_OWN_NOTICE_PATTERN` originally matched the number
    inside a "GN. No. <n> of <year>" citation too, since that citation form
    is a superset of the own-notice form. When a document has no separate
    own-notice header preceding a citation, this misread the cited
    document's number as the current document's own reference number.
    """
    text = "This circular supersedes GN. No. 999 of 1999, which was never ingested."

    assert extract_reference_number(text) is None
    assert find_cited_reference_numbers(text) == ["G.N. No. 999"]


def test_classify_relation_keyword_detects_amends(fixtures_dir: Path) -> None:
    """The amendment document's own text says regulations 'are amended by deleting...'."""
    text = _first_page_text(fixtures_dir / "bot-2023-licensing-amendment.pdf")

    assert classify_relation_keyword(text) == "amends"


def test_classify_relation_keyword_is_none_without_a_citation(fixtures_dir: Path) -> None:
    """A standalone regulation with no citations has no relation to classify."""
    text = _first_page_text(fixtures_dir / "bot-2014-licensing.pdf")

    assert classify_relation_keyword(text) is None


def test_extract_reference_number_returns_none_for_unfilled_placeholder(
    fixtures_dir: Path,
) -> None:
    """The electronic money regulation's gazette number is a literal blank placeholder."""
    text = _first_page_text(fixtures_dir / "bot-2015-electronic-money.pdf")

    assert extract_reference_number(text) is None
    assert extract_issued_date(text) is None


def test_extract_reference_number_handles_swahili_notice_form(fixtures_dir: Path) -> None:
    """'TANGAZO LA SERIKALI NA. 198' (Swahili) should be found like its English equivalent."""
    text = _first_page_text(fixtures_dir / "bot-2019-huduma-ndogo-swahili.pdf")

    assert extract_reference_number(text) == "G.N. No. 198"
    assert extract_issued_date(text) == date(2025, 3, 28)


@pytest.mark.parametrize(
    ("filename", "expected_reference"),
    [
        ("bot-2023-capital-adequacy.pdf", "G.N. No. 727"),
    ],
)
def test_extract_reference_number_capital_adequacy(
    fixtures_dir: Path, filename: str, expected_reference: str
) -> None:
    """The capital adequacy regulation's gazette number should be found."""
    text = _first_page_text(fixtures_dir / filename)

    assert extract_reference_number(text) == expected_reference
    assert extract_issued_date(text) == date(2023, 10, 6)
