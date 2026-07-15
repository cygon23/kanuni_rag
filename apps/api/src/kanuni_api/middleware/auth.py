"""API-key authentication and scope-based authorization for admin/query routes.

PROJECT_SPEC.md §4.3: API-key auth via `X-API-Key`, keys stored hashed
(SHA-256), with scopes (`query`, `ingest:admin`).
"""

import hashlib
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header

from kanuni_api.db import api_keys_repository
from kanuni_api.dependencies import DbConnection
from kanuni_api.exceptions import AuthenticationError, AuthorizationError
from kanuni_api.middleware.rate_limit import check_rate_limit
from kanuni_api.models.api_key import ApiKeyRecord


async def _authenticate(
    connection: DbConnection,
    x_api_key: Annotated[str | None, Header()] = None,
) -> ApiKeyRecord:
    """Resolve the API key presented in the `X-API-Key` header and enforce its rate limit.

    Args:
        connection: A database connection, used to look up the key.
        x_api_key: The raw API key from the request header.

    Returns:
        The authenticated key record.

    Raises:
        AuthenticationError: If no key is presented, or it is unknown/revoked.
        RateLimitExceededError: If this key has exceeded `rate_limit_per_min`.
    """
    if not x_api_key:
        raise AuthenticationError()
    key_hash = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()
    key_record = await api_keys_repository.find_active_by_key_hash(connection, key_hash)
    if key_record is None:
        raise AuthenticationError()
    check_rate_limit(key_record)
    return key_record


def require_scope(scope: str) -> Callable[..., Coroutine[Any, Any, ApiKeyRecord]]:
    """Build a FastAPI dependency that authenticates and requires a scope.

    Args:
        scope: The scope the caller's API key must have (e.g. `"ingest:admin"`).

    Returns:
        A dependency function suitable for use in a route's `Depends(...)`.
    """

    async def _dependency(
        key_record: Annotated[ApiKeyRecord, Depends(_authenticate)],
    ) -> ApiKeyRecord:
        if scope not in key_record.scopes:
            raise AuthorizationError()
        return key_record

    return _dependency
