"""Tests for GET /v1/documents and GET /v1/documents/{id}."""

import hashlib
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kanuni_api.db import api_keys_repository, documents_repository
from kanuni_api.dependencies import get_db_connection
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.models.api_key import ApiKeyRecord
from kanuni_api.models.document import DocumentStatus, DocumentSummary, DocumentType, PipelineStage
from kanuni_api.routes import documents

QUERY_KEY = "test-query-key"
QUERY_KEY_HASH = hashlib.sha256(QUERY_KEY.encode("utf-8")).hexdigest()


def _make_summary(document_id: UUID | None = None, **overrides: object) -> DocumentSummary:
    defaults: dict[str, object] = {
        "id": document_id or uuid4(),
        "source_id": "bot",
        "title": "A Regulation",
        "doc_type": DocumentType.REGULATION,
        "jurisdiction": "Tanzania",
        "issuing_body": "Bank of Tanzania",
        "reference_number": "G.N. No. 1",
        "language": "en",
        "issued_date": date(2024, 1, 1),
        "effective_date": None,
        "status": DocumentStatus.IN_FORCE,
        "pipeline_status": PipelineStage.INDEXED,
    }
    defaults.update(overrides)
    return DocumentSummary.model_validate(defaults)


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_find_active_by_key_hash(
        connection: object, key_hash: str
    ) -> ApiKeyRecord | None:
        if key_hash == QUERY_KEY_HASH:
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
    app.include_router(documents.router)
    return app


def test_list_documents_requires_authentication() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/v1/documents")

    assert response.status_code == 401


def test_list_documents_returns_repository_results(monkeypatch: pytest.MonkeyPatch) -> None:
    summaries = [_make_summary(), _make_summary()]

    async def _fake_list_documents(
        connection: object, *, status: object, doc_type: object, limit: int, offset: int
    ) -> list[DocumentSummary]:
        return summaries

    monkeypatch.setattr(documents_repository, "list_documents", _fake_list_documents)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/v1/documents", headers={"X-API-Key": QUERY_KEY})

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_document_returns_404_for_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_find_by_id(connection: object, document_id: UUID) -> DocumentSummary | None:
        return None

    monkeypatch.setattr(documents_repository, "find_by_id", _fake_find_by_id)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get(f"/v1/documents/{uuid4()}", headers={"X-API-Key": QUERY_KEY})

    assert response.status_code == 404
    assert response.json()["error_code"] == "document_not_found"


def test_get_document_returns_the_document_when_found(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid4()
    summary = _make_summary(document_id)

    async def _fake_find_by_id(connection: object, requested_id: UUID) -> DocumentSummary | None:
        return summary if requested_id == document_id else None

    monkeypatch.setattr(documents_repository, "find_by_id", _fake_find_by_id)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get(f"/v1/documents/{document_id}", headers={"X-API-Key": QUERY_KEY})

    assert response.status_code == 200
    assert response.json()["id"] == str(document_id)
