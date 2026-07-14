"""Creates the asyncpg connection pool shared by the ingestion worker and CLI-adjacent code."""

import asyncpg


async def create_pool(database_url: str) -> asyncpg.Pool:
    """Create a connection pool for the ingestion worker.

    Args:
        database_url: Postgres DSN to connect to.

    Returns:
        An open connection pool. Callers are responsible for closing it.
    """
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    if pool is None:  # pragma: no cover - asyncpg only returns None if closed mid-creation
        raise RuntimeError("Failed to create database connection pool")
    return pool
