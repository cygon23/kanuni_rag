"""Integration test: SHA-256 dedup on the real admin upload endpoint against real Postgres.

Re-uploading an already-ingested file must be a no-op reported as skipped
(PROJECT_SPEC.md §7 stage 1), verified here against a real database rather
than a mocked repository (see `apps/ingestion/tests/integration/` for the
mocked-vs-real split rationale).
"""

import hashlib
from collections.abc import AsyncIterator

import asyncpg
from api_fakes import FakeDocumentStorage
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kanuni_api.config import Settings, get_settings
from kanuni_api.dependencies import get_db_connection, get_storage
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.routes import admin

ADMIN_KEY = "integration-test-admin-key"
ADMIN_KEY_HASH = hashlib.sha256(ADMIN_KEY.encode("utf-8")).hexdigest()
_PDF_BYTES = b"%PDF-1.4\n%integration test pdf content\n"


async def _seed_admin_api_key(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO api_keys (key_hash, name, scopes, rate_limit_per_min)
            VALUES ($1, 'integration test key', ARRAY['ingest:admin'], 60)
            """,
            ADMIN_KEY_HASH,
        )


def _build_app(db_pool: asyncpg.Pool) -> FastAPI:
    async def _override_get_db_connection() -> AsyncIterator[asyncpg.Connection]:
        async with db_pool.acquire() as connection:
            yield connection

    app = FastAPI()
    register_exception_handlers(app)
    app.state.db_pool = db_pool
    app.dependency_overrides[get_db_connection] = _override_get_db_connection
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_size_bytes=10_000_000)
    app.dependency_overrides[get_storage] = lambda: FakeDocumentStorage()
    app.include_router(admin.router)
    return app


async def test_reuploading_the_same_file_is_reported_as_skipped(db_pool: asyncpg.Pool) -> None:
    """The second upload of identical bytes must be a 200 skip, not a second document."""
    await _seed_admin_api_key(db_pool)
    client = TestClient(_build_app(db_pool), raise_server_exceptions=False)
    headers = {"X-API-Key": ADMIN_KEY}
    data = {"source_id": "bot", "title": "Duplicate test", "doc_type": "regulation"}

    first_response = client.post(
        "/v1/admin/documents",
        headers=headers,
        data=data,
        files={"file": ("doc.pdf", _PDF_BYTES, "application/pdf")},
    )
    second_response = client.post(
        "/v1/admin/documents",
        headers=headers,
        data=data,
        files={"file": ("doc.pdf", _PDF_BYTES, "application/pdf")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    first_id = first_response.json()["document_id"]
    second_id = second_response.json()["document_id"]
    assert first_id == second_id

    async with db_pool.acquire() as connection:
        document_count = await connection.fetchval(
            "SELECT count(*) FROM documents WHERE file_sha256 = $1",
            hashlib.sha256(_PDF_BYTES).hexdigest(),
        )
    assert document_count == 1


async def test_different_files_produce_separate_documents(db_pool: asyncpg.Pool) -> None:
    """Two different files must never be deduplicated against each other."""
    await _seed_admin_api_key(db_pool)
    client = TestClient(_build_app(db_pool), raise_server_exceptions=False)

    first_response = client.post(
        "/v1/admin/documents",
        headers={"X-API-Key": ADMIN_KEY},
        data={"source_id": "bot", "title": "Doc A", "doc_type": "regulation"},
        files={"file": ("a.pdf", _PDF_BYTES, "application/pdf")},
    )
    second_response = client.post(
        "/v1/admin/documents",
        headers={"X-API-Key": ADMIN_KEY},
        data={"source_id": "bot", "title": "Doc B", "doc_type": "regulation"},
        files={"file": ("b.pdf", _PDF_BYTES + b"\nextra bytes", "application/pdf")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["document_id"] != second_response.json()["document_id"]
