"""Tests for kanuni_api.config: env var parsing, defaults, and settings caching."""

import pytest

from kanuni_api.config import Settings, get_settings


def test_defaults_are_used_when_no_env_vars_set() -> None:
    """With no KANUNI_ environment variables set, defaults should apply."""
    settings = Settings()

    assert settings.environment == "development"
    assert settings.log_level == "info"
    assert settings.api_port == 8000
    assert settings.cors_allowed_origins == ["http://localhost:3000"]


def test_defaults_are_used_even_when_a_real_env_file_exists_on_disk() -> None:
    """Settings() must never pick up the real repo-root .env file during tests.

    Regression test: `conftest.py`'s `_clean_kanuni_env` fixture used to only
    strip env vars from `os.environ`, which doesn't stop pydantic-settings
    from reading `env_file=".env"` directly off disk as a separate source —
    a maintainer's real GROQ_API_KEY/SENTRY_DSN/SUPABASE_SERVICE_ROLE_KEY
    leaked into every test's Settings() as a result (caught live: pytest was
    sending real sampled trace events to a real GlitchTip project). The
    fixture now also points `env_file` at a nonexistent path for the
    duration of each test — this asserts that actually holds, for exactly
    the bare (non-KANUNI_-prefixed) fields that carry real secrets.
    """
    settings = Settings()

    assert settings.groq_api_key == ""
    assert settings.sentry_dsn == ""
    assert settings.supabase_url == ""
    assert settings.supabase_service_role_key == ""
    assert settings.release_sha == "dev"
    assert settings.database_url == "postgresql://kanuni:kanuni@localhost:5432/kanuni"


def test_environment_variable_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """A KANUNI_-prefixed env var should override the corresponding field's default."""
    monkeypatch.setenv("KANUNI_ENVIRONMENT", "production")
    monkeypatch.setenv("KANUNI_API_PORT", "9000")

    settings = Settings()

    assert settings.environment == "production"
    assert settings.api_port == 9000


def test_cors_allowed_origins_parses_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A comma-separated KANUNI_CORS_ALLOWED_ORIGINS should split into a list, trimmed."""
    monkeypatch.setenv(
        "KANUNI_CORS_ALLOWED_ORIGINS", "https://a.example.com, https://b.example.com"
    )

    settings = Settings()

    assert settings.cors_allowed_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_get_settings_returns_cached_instance() -> None:
    """get_settings should construct Settings once per process and reuse the instance."""
    first = get_settings()
    second = get_settings()

    assert first is second


def test_get_settings_cache_clear_forces_reconstruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearing the cache should cause the next call to re-read the environment."""
    first = get_settings()

    monkeypatch.setenv("KANUNI_ENVIRONMENT", "staging")
    get_settings.cache_clear()
    second = get_settings()

    assert first is not second
    assert second.environment == "staging"
