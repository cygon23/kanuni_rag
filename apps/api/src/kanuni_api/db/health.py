"""Lightweight database connectivity check used by the /readyz endpoint."""

import asyncpg
import structlog

logger = structlog.get_logger()

_CONNECT_TIMEOUT_SECONDS = 2.0


async def check_database_connection(database_url: str) -> bool:
    """Verify that the database is reachable and accepting queries.

    Args:
        database_url: Postgres DSN to connect to.

    Returns:
        True if a connection could be opened and a trivial query executed,
        False otherwise. Never raises: connection failures are logged and
        reported as a negative readiness signal instead of propagating.
    """
    try:
        connection = await asyncpg.connect(database_url, timeout=_CONNECT_TIMEOUT_SECONDS)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        logger.warning("readiness_database_check_failed")
        return False
    try:
        await connection.fetchval("SELECT 1")
    except asyncpg.PostgresError:
        logger.warning("readiness_database_check_failed")
        return False
    finally:
        await connection.close()
    return True
