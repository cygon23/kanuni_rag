"""Shared pytest fixtures for the kanuni_api test suite."""

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kanuni_api.config import get_settings
from kanuni_api.middleware import rate_limit

_KANUNI_ENV_PREFIX = "KANUNI_"

# This tests/ tree has no __init__.py (apps/api/tests and apps/ingestion/tests
# would otherwise both resolve to the same dotted module name "tests" and
# collide during conftest collection). Adding this directory to sys.path lets
# test modules do a plain `from api_fakes import ...` regardless of nesting
# depth — named api_fakes, not fakes, since apps/ingestion/tests/fakes.py
# would otherwise shadow (or be shadowed by) this one in sys.modules once
# both trees are collected in the same pytest session.
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def _clean_kanuni_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip KANUNI_-prefixed env vars and reset the settings cache around each test."""
    for key in list(os.environ):
        if key.startswith(_KANUNI_ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_rate_limit_windows() -> None:
    """Clear the in-memory rate-limit state before each test.

    Without this, tests that reuse a fixed API-key id (e.g.
    `tests/middleware/test_auth.py`'s hardcoded UUIDs) would accumulate
    request counts across test functions in the same pytest session,
    eventually tripping `RateLimitExceededError` for reasons unrelated to
    what any individual test is checking.
    """
    rate_limit._windows.clear()
