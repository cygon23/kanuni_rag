"""FastAPI dependency providers for the database connection pool."""

from collections.abc import AsyncIterator
from typing import Annotated

import asyncpg
from fastapi import Depends, Request


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Return the app-wide connection pool created at startup.

    Args:
        request: The current request, used to reach `app.state`.

    Returns:
        The connection pool.
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    return pool


async def get_db_connection(
    pool: Annotated[asyncpg.Pool, Depends(get_db_pool)],
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection from the pool for the duration of one request.

    Args:
        pool: The app-wide connection pool.

    Yields:
        A connection, released back to the pool when the request completes.
    """
    async with pool.acquire() as connection:
        yield connection


DbConnection = Annotated[asyncpg.Connection, Depends(get_db_connection)]
