"""Parameterized SQL for the `api_keys` table."""

import asyncpg

from kanuni_api.models.api_key import ApiKeyRecord


async def find_active_by_key_hash(
    connection: asyncpg.Connection, key_hash: str
) -> ApiKeyRecord | None:
    """Fetch a non-revoked API key by its hash.

    Args:
        connection: An open database connection.
        key_hash: The SHA-256 hex digest of the presented API key.

    Returns:
        The matching key record, or `None` if no such key exists or it has
        been revoked.
    """
    row = await connection.fetchrow(
        "SELECT * FROM api_keys WHERE key_hash = $1 AND revoked_at IS NULL", key_hash
    )
    if row is None:
        return None
    return ApiKeyRecord(
        id=row["id"],
        name=row["name"],
        scopes=list(row["scopes"]),
        rate_limit_per_min=row["rate_limit_per_min"],
    )
