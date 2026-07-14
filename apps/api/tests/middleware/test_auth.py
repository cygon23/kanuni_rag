"""Tests for API-key authentication and scope-based authorization."""

import hashlib
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from kanuni_api.db import api_keys_repository
from kanuni_api.dependencies import get_db_connection
from kanuni_api.middleware.auth import require_scope
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.models.api_key import ApiKeyRecord

VALID_KEY = "test-key-with-query-scope"
VALID_KEY_HASH = hashlib.sha256(VALID_KEY.encode("utf-8")).hexdigest()
ADMIN_KEY = "test-key-with-admin-scope"
ADMIN_KEY_HASH = hashlib.sha256(ADMIN_KEY.encode("utf-8")).hexdigest()

_KEYS_BY_HASH = {
    VALID_KEY_HASH: ApiKeyRecord(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        name="query key",
        scopes=["query"],
        rate_limit_per_min=60,
    ),
    ADMIN_KEY_HASH: ApiKeyRecord(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        name="admin key",
        scopes=["query", "ingest:admin"],
        rate_limit_per_min=60,
    ),
}


@pytest.fixture(autouse=True)
def _stub_api_key_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_find_active_by_key_hash(
        connection: object, key_hash: str
    ) -> ApiKeyRecord | None:
        return _KEYS_BY_HASH.get(key_hash)

    monkeypatch.setattr(
        api_keys_repository, "find_active_by_key_hash", _fake_find_active_by_key_hash
    )


_require_query_scope = require_scope("query")
_require_admin_scope = require_scope("ingest:admin")


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_db_connection] = lambda: None

    @app.get("/query-only")
    async def query_only(
        _key: Annotated[ApiKeyRecord, Depends(_require_query_scope)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/admin-only")
    async def admin_only(
        _key: Annotated[ApiKeyRecord, Depends(_require_admin_scope)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_missing_api_key_is_rejected() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/query-only")

    assert response.status_code == 401
    assert response.json()["error_code"] == "authentication_failed"


def test_unknown_api_key_is_rejected() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/query-only", headers={"X-API-Key": "not-a-real-key"})

    assert response.status_code == 401


def test_valid_key_with_required_scope_is_accepted() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/query-only", headers={"X-API-Key": VALID_KEY})

    assert response.status_code == 200


def test_valid_key_without_required_scope_is_forbidden() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/admin-only", headers={"X-API-Key": VALID_KEY})

    assert response.status_code == 403
    assert response.json()["error_code"] == "authorization_failed"


def test_admin_key_can_access_both_query_and_admin_routes() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    assert client.get("/query-only", headers={"X-API-Key": ADMIN_KEY}).status_code == 200
    assert client.get("/admin-only", headers={"X-API-Key": ADMIN_KEY}).status_code == 200
