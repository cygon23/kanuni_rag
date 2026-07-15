"""Tests for admin routes: document upload, failed-job listing, and retry."""

import hashlib
from uuid import UUID, uuid4

import pytest
from api_fakes import FakeDocumentStorage
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kanuni_api.config import Settings, get_settings
from kanuni_api.db import api_keys_repository, ingestion_jobs_repository
from kanuni_api.dependencies import get_db_connection, get_storage
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.models.api_key import ApiKeyRecord
from kanuni_api.models.document import PipelineStage
from kanuni_api.models.ingestion_job import IngestionJobSummary
from kanuni_api.routes import admin
from kanuni_api.services import document_ingestion_service
from kanuni_api.services.document_ingestion_service import UploadOutcome

ADMIN_KEY = "test-admin-key"
ADMIN_KEY_HASH = hashlib.sha256(ADMIN_KEY.encode("utf-8")).hexdigest()
QUERY_ONLY_KEY = "test-query-only-key"
QUERY_ONLY_KEY_HASH = hashlib.sha256(QUERY_ONLY_KEY.encode("utf-8")).hexdigest()

_PDF_BYTES = b"%PDF-1.4\n%fake pdf content for tests\n"


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_find_active_by_key_hash(
        connection: object, key_hash: str
    ) -> ApiKeyRecord | None:
        if key_hash == ADMIN_KEY_HASH:
            return ApiKeyRecord(
                id=uuid4(), name="admin key", scopes=["ingest:admin"], rate_limit_per_min=60
            )
        if key_hash == QUERY_ONLY_KEY_HASH:
            return ApiKeyRecord(
                id=uuid4(), name="query key", scopes=["query"], rate_limit_per_min=60
            )
        return None

    monkeypatch.setattr(
        api_keys_repository, "find_active_by_key_hash", _fake_find_active_by_key_hash
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_db_connection] = lambda: None
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_size_bytes=10_000_000)
    app.dependency_overrides[get_storage] = lambda: FakeDocumentStorage()
    app.include_router(admin.router)
    return app


def test_upload_document_requires_admin_scope() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post(
        "/v1/admin/documents",
        headers={"X-API-Key": QUERY_ONLY_KEY},
        data={"source_id": "bot", "title": "T", "doc_type": "regulation"},
        files={"file": ("doc.pdf", _PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 403


def test_upload_document_returns_201_for_a_new_document(monkeypatch: pytest.MonkeyPatch) -> None:
    new_id = uuid4()

    async def _fake_ingest_upload(*args: object, **kwargs: object) -> UploadOutcome:
        return UploadOutcome(document_id=new_id, created=True)

    monkeypatch.setattr(document_ingestion_service, "ingest_upload", _fake_ingest_upload)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post(
        "/v1/admin/documents",
        headers={"X-API-Key": ADMIN_KEY},
        data={"source_id": "bot", "title": "T", "doc_type": "regulation"},
        files={"file": ("doc.pdf", _PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json() == {"status": "created", "document_id": str(new_id)}


def test_upload_document_returns_200_for_a_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    existing_id = uuid4()

    async def _fake_ingest_upload(*args: object, **kwargs: object) -> UploadOutcome:
        return UploadOutcome(document_id=existing_id, created=False)

    monkeypatch.setattr(document_ingestion_service, "ingest_upload", _fake_ingest_upload)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post(
        "/v1/admin/documents",
        headers={"X-API-Key": ADMIN_KEY},
        data={"source_id": "bot", "title": "T", "doc_type": "regulation"},
        files={"file": ("doc.pdf", _PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "skipped", "document_id": str(existing_id)}


def test_upload_document_rejects_unknown_source() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post(
        "/v1/admin/documents",
        headers={"X-API-Key": ADMIN_KEY},
        data={"source_id": "not-a-real-source", "title": "T", "doc_type": "regulation"},
        files={"file": ("doc.pdf", _PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_failed"


def test_list_failed_ingestion_jobs_requires_admin_scope() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/v1/admin/ingestion-jobs", headers={"X-API-Key": QUERY_ONLY_KEY})

    assert response.status_code == 403


def test_list_failed_ingestion_jobs_returns_repository_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = IngestionJobSummary(
        id=uuid4(),
        document_id=uuid4(),
        stage=PipelineStage.FAILED,
        attempt_count=2,
        error_details={"error": "boom"},
    )

    async def _fake_list_failed(connection: object) -> list[IngestionJobSummary]:
        return [job]

    monkeypatch.setattr(ingestion_jobs_repository, "list_failed", _fake_list_failed)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/v1/admin/ingestion-jobs", headers={"X-API-Key": ADMIN_KEY})

    assert response.status_code == 200
    assert response.json()[0]["attempt_count"] == 2


def test_retry_ingestion_job_resets_the_document(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid4()
    reset_calls: list[UUID] = []

    async def _fake_reset_for_retry(connection: object, target_id: UUID) -> None:
        reset_calls.append(target_id)

    monkeypatch.setattr(ingestion_jobs_repository, "reset_for_retry", _fake_reset_for_retry)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post(
        f"/v1/admin/ingestion-jobs/{document_id}/retry", headers={"X-API-Key": ADMIN_KEY}
    )

    assert response.status_code == 202
    assert reset_calls == [document_id]
