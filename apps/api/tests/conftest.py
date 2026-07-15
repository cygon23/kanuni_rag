"""Shared pytest fixtures for the kanuni_api test suite."""

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kanuni_api.config import Settings, get_settings
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


def _bare_env_var_names() -> list[str]:
    """Every env var Settings reads without the KANUNI_ prefix (via validation_alias).

    E.g. GROQ_API_KEY, SENTRY_DSN, SUPABASE_URL — read from Settings.model_fields
    rather than hardcoded, so a newly-added bare-var field can't silently leak a
    maintainer's real .env value into a test the way SENTRY_DSN did (see below).
    """
    return [
        str(field.validation_alias)
        for field in Settings.model_fields.values()
        if field.validation_alias is not None
    ]


@pytest.fixture(autouse=True)
def _clean_kanuni_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate Settings() from the real environment and .env file around each test.

    Found live: pytest was sending real sampled trace events to a real
    GlitchTip project during a normal test run. Root cause was two layered
    problems, both fixed here:

    1. Only KANUNI_-prefixed env vars were being stripped — SENTRY_DSN,
       GROQ_API_KEY, SUPABASE_URL, and SUPABASE_SERVICE_ROLE_KEY are bare
       (no prefix) by deliberate design (matching each provider's own
       conventional variable name), so a maintainer's real values for
       those were never cleared.
    2. Even stripping *every* var from os.environ isn't sufficient:
       pydantic-settings' `env_file=".env"` is a second, separate source
       it reads directly off disk — a var merely deleted from the process
       environment still gets its value from the real .env file on the
       next `Settings()` call. `monkeypatch.delenv` cannot prevent this;
       only disabling the dotenv source itself does.

    So: os.environ is cleaned (defense in depth, and it's what lets a
    real KANUNI_-prefixed CI env var reach a test if one is ever set
    directly), *and* `env_file` is monkeypatched to a nonexistent path,
    which cleanly disables pydantic-settings' dotenv loading altogether —
    every test then gets pure class-default Settings unless it
    constructs Settings(...) with explicit overrides, as intended.
    """
    for key in list(os.environ):
        if key.startswith(_KANUNI_ENV_PREFIX) or key in _bare_env_var_names():
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", "/nonexistent/.env")
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
