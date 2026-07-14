"""Tests for the domain exception hierarchy: default details, overrides, and stable codes."""

import pytest

from kanuni_api.exceptions import (
    DocumentNotFoundError,
    GenerationError,
    IngestionError,
    KanuniError,
    LowConfidenceError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    RetrievalError,
    ValidationFailedError,
)

ALL_DOMAIN_EXCEPTIONS = [
    RetrievalError,
    GenerationError,
    IngestionError,
    DocumentNotFoundError,
    LowConfidenceError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ValidationFailedError,
]


@pytest.mark.parametrize("exception_class", ALL_DOMAIN_EXCEPTIONS)
def test_domain_exception_is_a_kanuni_error(exception_class: type[KanuniError]) -> None:
    """Every domain exception must subclass KanuniError so the global handler catches it."""
    assert issubclass(exception_class, KanuniError)


@pytest.mark.parametrize("exception_class", ALL_DOMAIN_EXCEPTIONS)
def test_domain_exception_has_a_unique_stable_error_code(
    exception_class: type[KanuniError],
) -> None:
    """Each domain exception must declare its own non-default error_code."""
    assert exception_class.error_code != KanuniError.error_code
    assert exception_class.error_code


@pytest.mark.parametrize("exception_class", ALL_DOMAIN_EXCEPTIONS)
def test_domain_exception_uses_default_detail_when_not_overridden(
    exception_class: type[KanuniError],
) -> None:
    """Instantiating without an explicit detail should fall back to the class default."""
    instance = exception_class()

    assert instance.detail == exception_class.detail
    assert str(instance) == exception_class.detail


def test_detail_can_be_overridden_per_instance() -> None:
    """Passing a detail string should override the class default for that instance only."""
    instance = DocumentNotFoundError("Document 'abc-123' was not found.")

    assert instance.detail == "Document 'abc-123' was not found."
    assert DocumentNotFoundError.detail == "The requested document was not found."


def test_error_codes_are_all_unique() -> None:
    """No two domain exceptions should share an error_code — clients branch on it."""
    error_codes = [exc.error_code for exc in ALL_DOMAIN_EXCEPTIONS]

    assert len(error_codes) == len(set(error_codes))
