"""Tests for GET /v1/admin/retrieve: the retrieval debug endpoint."""

import hashlib
from uuid import uuid4

import pytest
from api_fakes import FakeEmbeddingProvider, FakeRerankerProvider
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kanuni_api.db import api_keys_repository
from kanuni_api.dependencies import (
    get_db_connection,
    get_embedding_provider,
    get_reranker_provider,
)
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.models.api_key import ApiKeyRecord
from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.routes import admin

ADMIN_KEY = "test-admin-key"
ADMIN_KEY_HASH = hashlib.sha256(ADMIN_KEY.encode("utf-8")).hexdigest()
QUERY_ONLY_KEY = "test-query-only-key"
QUERY_ONLY_KEY_HASH = hashlib.sha256(QUERY_ONLY_KEY.encode("utf-8")).hexdigest()


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
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    app.dependency_overrides[get_reranker_provider] = lambda: FakeRerankerProvider()
    app.include_router(admin.router)
    return app


def test_debug_retrieve_requires_admin_scope() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get(
        "/v1/admin/retrieve", params={"question": "x"}, headers={"X-API-Key": QUERY_ONLY_KEY}
    )

    assert response.status_code == 403


def test_debug_retrieve_returns_scored_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    scored = [
        ScoredChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            content="relevant text",
            section_ref="s.5",
            page_start=1,
            page_end=1,
            rerank_score=0.9,
        )
    ]

    async def _fake_retrieve(
        connection: object, question: str, **kwargs: object
    ) -> list[ScoredChunk]:
        assert question == "What is the minimum capital?"
        return scored

    monkeypatch.setattr(admin, "retrieve", _fake_retrieve)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get(
        "/v1/admin/retrieve",
        params={"question": "What is the minimum capital?"},
        headers={"X-API-Key": ADMIN_KEY},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["content"] == "relevant text"
    assert body[0]["rerank_score"] == 0.9
