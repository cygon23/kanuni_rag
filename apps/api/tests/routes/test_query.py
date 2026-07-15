"""Tests for POST /v1/query: auth and SSE wiring at the HTTP layer."""

import hashlib
import json
from datetime import date
from uuid import uuid4

import pytest
from api_fakes import FakeEmbeddingProvider, FakeLLMProvider, FakeRerankerProvider
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kanuni_api.db import api_keys_repository, documents_repository, queries_repository
from kanuni_api.dependencies import (
    get_db_connection,
    get_embedding_provider,
    get_llm_provider,
    get_reranker_provider,
)
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.models.api_key import ApiKeyRecord
from kanuni_api.models.document import DocumentStatus, DocumentSummary, DocumentType, PipelineStage
from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.routes import query
from kanuni_api.services import query_service

QUERY_KEY = "test-query-key"
QUERY_KEY_HASH = hashlib.sha256(QUERY_KEY.encode("utf-8")).hexdigest()
ADMIN_ONLY_KEY = "test-admin-only-key"
ADMIN_ONLY_KEY_HASH = hashlib.sha256(ADMIN_ONLY_KEY.encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_find_active_by_key_hash(
        connection: object, key_hash: str
    ) -> ApiKeyRecord | None:
        if key_hash == QUERY_KEY_HASH:
            return ApiKeyRecord(
                id=uuid4(), name="query key", scopes=["query"], rate_limit_per_min=60
            )
        if key_hash == ADMIN_ONLY_KEY_HASH:
            return ApiKeyRecord(
                id=uuid4(), name="admin key", scopes=["ingest:admin"], rate_limit_per_min=60
            )
        return None

    monkeypatch.setattr(
        api_keys_repository, "find_active_by_key_hash", _fake_find_active_by_key_hash
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_db_connection] = lambda: None
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    app.dependency_overrides[get_reranker_provider] = lambda: FakeRerankerProvider()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    app.include_router(query.router)
    return app


def test_query_requires_query_scope() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post(
        "/v1/query", json={"question": "What is X?"}, headers={"X-API-Key": ADMIN_ONLY_KEY}
    )

    assert response.status_code == 403


def test_query_rejects_missing_api_key() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post("/v1/query", json={"question": "What is X?"})

    assert response.status_code == 401


def test_query_rejects_empty_question() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post("/v1/query", json={"question": ""}, headers={"X-API-Key": QUERY_KEY})

    assert response.status_code == 422


def test_query_streams_sse_with_a_json_encoded_done_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wire format's `done` event must parse as JSON, not a Python dict repr.

    Regression test: `EventSourceResponse`'s default `ServerSentEvent`
    encodes a dict `data` value with plain `str()`, not `json.dumps` — see
    `query_service.run_query`'s docstring. This exercises the real SSE
    encoding path (unlike the query_service-level tests, which call
    `run_query` directly and never touch `EventSourceResponse`).
    """
    document_id = uuid4()
    chunk = ScoredChunk(
        chunk_id=uuid4(),
        document_id=document_id,
        content="Applicants must hold minimum capital.",
        section_ref="s.5",
        page_start=3,
        page_end=3,
        rerank_score=0.9,
    )
    document = DocumentSummary(
        id=document_id,
        source_id="bot",
        title="Licensing Regulations",
        doc_type=DocumentType.REGULATION,
        jurisdiction="Tanzania",
        issuing_body="Bank of Tanzania",
        reference_number="G.N. No. 297",
        language="en",
        issued_date=date(2014, 8, 22),
        effective_date=None,
        status=DocumentStatus.IN_FORCE,
        pipeline_status=PipelineStage.INDEXED,
    )

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[ScoredChunk]:
        return [chunk]

    async def _fake_find_by_id(connection: object, requested_id: object) -> DocumentSummary:
        return document

    async def _fake_find_storage_path(connection: object, requested_id: object) -> str | None:
        return "abc123.pdf"

    async def _fake_log_query(connection: object, **kwargs: object) -> None:
        pass

    monkeypatch.setattr(query_service, "retrieve", _fake_retrieve)
    monkeypatch.setattr(documents_repository, "find_by_id", _fake_find_by_id)
    monkeypatch.setattr(documents_repository, "find_storage_path", _fake_find_storage_path)
    monkeypatch.setattr(queries_repository, "log_query", _fake_log_query)

    app = _build_app()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        text_deltas=[f"Answer. [chunk:{chunk.chunk_id}]"]
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/v1/query",
        json={"question": "What is the minimum capital?"},
        headers={"X-API-Key": QUERY_KEY},
    )

    assert response.status_code == 200
    lines = response.text.splitlines()
    done_data_lines = [
        lines[i + 1].removeprefix("data: ") for i, line in enumerate(lines) if line == "event: done"
    ]
    assert len(done_data_lines) == 1
    parsed = json.loads(done_data_lines[0])
    assert parsed["confidence"] == "ok"
    assert parsed["answered"] is True
    assert parsed["citations"][0]["chunk_id"] == str(chunk.chunk_id)
