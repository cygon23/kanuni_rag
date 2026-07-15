"""In-memory per-API-key rate limiting (§4.3's auth model requires it; verified under load in
§12 via infra/k6/smoke-load-test.js).

A fixed-window counter per key id: not exact (a burst straddling a
window boundary can momentarily allow up to ~2x the configured rate),
but simple, dependency-free, and adequate for a single-instance v1
deployment. Known limitation, recorded as an Open ADR candidate in
docs/PROGRESS.md's Phase 6 notes: this state is per-process — running
more than one machine/worker would need a shared store (Redis, or a
Postgres-backed counter) for the limit to hold across replicas.
"""

import time
from uuid import UUID

from kanuni_api.exceptions import RateLimitExceededError
from kanuni_api.models.api_key import ApiKeyRecord

_WINDOW_SECONDS = 60.0
_windows: dict[UUID, tuple[float, int]] = {}


def check_rate_limit(key_record: ApiKeyRecord) -> None:
    """Raise if this key has exceeded its per-minute limit in the current window.

    Args:
        key_record: The authenticated caller's API key record.

    Raises:
        RateLimitExceededError: If this key has made more than
            `key_record.rate_limit_per_min` requests in the current
            60-second window.
    """
    now = time.monotonic()
    window_start, count = _windows.get(key_record.id, (now, 0))
    if now - window_start >= _WINDOW_SECONDS:
        window_start, count = now, 0
    count += 1
    _windows[key_record.id] = (window_start, count)
    if count > key_record.rate_limit_per_min:
        raise RateLimitExceededError()
