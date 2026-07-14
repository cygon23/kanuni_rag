"""Shared pytest fixtures for the kanuni_api test suite."""

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kanuni_api.config import get_settings

_KANUNI_ENV_PREFIX = "KANUNI_"

# This tests/ tree has no __init__.py (apps/api/tests and apps/ingestion/tests
# would otherwise both resolve to the same dotted module name "tests" and
# collide during conftest collection). Adding this directory to sys.path lets
# test modules do a plain `from fakes import ...` regardless of nesting depth.
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
