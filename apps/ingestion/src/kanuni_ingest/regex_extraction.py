"""Pure regex helpers for the first half of PROJECT_SPEC.md §7 stage 4: candidate
reference numbers, issue dates, and cited-document relations, ahead of the LLM
extraction call that validates and supplements them.
"""

import re
from datetime import date
from typing import Literal

_OWN_NOTICE_PATTERN = re.compile(
    r"(?:GOVERNMENT\s+NOTICE\s+NO\.?|G\.?N\.?\s*No\.?|TANGAZO\s+LA\s+SERIKALI\s+NA\.?)"
    r"\s*(\d+)\b(?!\s+of\s+\d{4})",
    re.IGNORECASE,
)
_ISSUED_DATE_PATTERN = re.compile(
    r"(?:published\s+on\.?|la\s+tarehe)\s*(\d{1,2})/(\d{1,2})/(\d{4})",
    re.IGNORECASE,
)
_CITATION_PATTERN = re.compile(
    r"G\.?N\.?\s*No\.?\s*(\d+)\s+of\s+(\d{4})",
    re.IGNORECASE,
)
_SUPERSEDE_KEYWORDS = ("supersede", "revoke", "repeal")
_AMEND_KEYWORDS = ("amend",)


def extract_reference_number(text: str) -> str | None:
    """Find this document's own gazette/notice reference number.

    Args:
        text: The document's extracted text (native or OCR).

    Returns:
        A normalized reference number like `"G.N. No. 297"`, or `None` if no
        notice number is present — never a guess.
    """
    match = _OWN_NOTICE_PATTERN.search(text)
    if match is None:
        return None
    return f"G.N. No. {match.group(1)}"


def extract_issued_date(text: str) -> date | None:
    """Find this document's publication date.

    Args:
        text: The document's extracted text (native or OCR).

    Returns:
        The publication date, or `None` if absent (e.g. an unfilled
        placeholder in the source) — never a guess.
    """
    match = _ISSUED_DATE_PATTERN.search(text)
    if match is None:
        return None
    day, month, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_cited_reference_numbers(text: str) -> list[str]:
    """Find every `"G.N. No. <n> of <year>"`-style citation to another document.

    Args:
        text: The document's extracted text (native or OCR).

    Returns:
        Normalized reference numbers of cited documents, e.g. `["G.N. No. 297"]`.
        A citation's own year is folded into the returned string's meaning via
        cross-referencing against the citing document's known documents, not
        returned separately, since the target lookup matches on the number
        alone (PROJECT_SPEC.md §6's `reference_number` is not year-qualified).
    """
    return [f"G.N. No. {number}" for number, _year in _CITATION_PATTERN.findall(text)]


def classify_relation_keyword(text: str) -> Literal["supersedes", "amends", "refers_to"] | None:
    """Classify how this document relates to any document it cites.

    Args:
        text: The document's extracted text (native or OCR).

    Returns:
        `"supersedes"` if revocation/repeal/supersession language is present,
        `"amends"` if amendment language is present (checked only if no
        supersession language matched), `"refers_to"` if the text contains a
        citation but neither keyword group, or `None` if no citation exists.
    """
    lowered = text.lower()
    has_citation = bool(_CITATION_PATTERN.search(text))
    if any(keyword in lowered for keyword in _SUPERSEDE_KEYWORDS):
        return "supersedes"
    if any(keyword in lowered for keyword in _AMEND_KEYWORDS):
        return "amends"
    if has_citation:
        return "refers_to"
    return None
