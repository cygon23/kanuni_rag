"""Shared pytest fixtures for the kanuni_api test suite."""

import os
from collections.abc import Iterator

import pytest

from kanuni_api.config import get_settings

_KANUNI_ENV_PREFIX = "KANUNI_"


@pytest.fixture(autouse=True)
def _clean_kanuni_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip KANUNI_-prefixed env vars and reset the settings cache around each test."""
    for key in list(os.environ):
        if key.startswith(_KANUNI_ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
