"""Tests for the in-memory per-API-key rate limiter."""

import time
from uuid import uuid4

import pytest

from kanuni_api.exceptions import RateLimitExceededError
from kanuni_api.middleware.rate_limit import _WINDOW_SECONDS, check_rate_limit
from kanuni_api.models.api_key import ApiKeyRecord


def _key(rate_limit_per_min: int = 3) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=uuid4(), name="test key", scopes=["query"], rate_limit_per_min=rate_limit_per_min
    )


def test_requests_within_the_limit_are_allowed() -> None:
    key = _key(rate_limit_per_min=3)
    for _ in range(3):
        check_rate_limit(key)  # must not raise


def test_a_request_beyond_the_limit_raises() -> None:
    key = _key(rate_limit_per_min=3)
    for _ in range(3):
        check_rate_limit(key)

    with pytest.raises(RateLimitExceededError):
        check_rate_limit(key)


def test_different_keys_have_independent_limits() -> None:
    first_key = _key(rate_limit_per_min=1)
    second_key = _key(rate_limit_per_min=1)

    check_rate_limit(first_key)
    check_rate_limit(second_key)  # must not raise — a different key's window


def test_a_new_window_resets_the_count(monkeypatch: pytest.MonkeyPatch) -> None:
    key = _key(rate_limit_per_min=1)
    current_time = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: current_time)

    check_rate_limit(key)
    with pytest.raises(RateLimitExceededError):
        check_rate_limit(key)

    current_time += _WINDOW_SECONDS + 1
    check_rate_limit(key)  # must not raise — a fresh window
