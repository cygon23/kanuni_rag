"""Fixtures for ingestion integration tests: a real Postgres+pgvector connection.

These tests are skipped (not failed) when no reachable Postgres is
configured, since that's expected in most local dev environments — they run
for real in CI's `integration-tests` job (§12), which provisions
`pgvector/pgvector:pg15` as a service container.
"""

import os
import shutil
from collections.abc import AsyncIterator

import asyncpg
import pytest

_DEFAULT_DATABASE_URL = "postgresql://kanuni:kanuni@localhost:5432/kanuni"
_TABLES_TO_TRUNCATE = (
    "chunks",
    "document_relations",
    "ingestion_jobs",
    "documents",
    "queries",
    "api_keys",
)


def _database_url() -> str:
    return os.environ.get("KANUNI_DATABASE_URL") or os.environ.get(
        "DATABASE_URL", _DEFAULT_DATABASE_URL
    )


@pytest.fixture
async def db_pool() -> AsyncIterator[asyncpg.Pool]:
    """A connection pool to a real Postgres, or a skip if none is reachable."""
    try:
        pool = await asyncpg.create_pool(_database_url(), min_size=1, max_size=5, timeout=3)
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        pytest.skip(f"no reachable Postgres for integration tests: {exc}")
    assert pool is not None
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture(autouse=True)
async def _clean_tables(db_pool: asyncpg.Pool) -> None:
    """Truncate every ingestion-relevant table before each integration test."""
    async with db_pool.acquire() as connection:
        await connection.execute(f"TRUNCATE {', '.join(_TABLES_TO_TRUNCATE)} CASCADE")


@pytest.fixture
def require_tesseract() -> None:
    """Skip a test if the `tesseract` binary isn't installed."""
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract is not installed in this environment")
