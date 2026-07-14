"""Smoke tests for the app factory: health/readiness endpoints and header wiring."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from kanuni_api.main import create_app
from kanuni_api.middleware.request_id import REQUEST_ID_HEADER


def test_healthz_reports_ok_without_checking_dependencies() -> None:
    """/healthz is a pure liveness check and should always report ok."""
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert REQUEST_ID_HEADER in response.headers


def test_readyz_reports_ok_when_database_is_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """/readyz should report 200 and status ok when the database check succeeds."""

    async def _fake_check(_database_url: str) -> bool:
        return True

    monkeypatch.setattr("kanuni_api.routes.health.check_database_connection", _fake_check)
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": True}


def test_readyz_reports_503_when_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/readyz should report 503 and status not_ready when the database check fails."""

    async def _fake_check(_database_url: str) -> bool:
        return False

    monkeypatch.setattr("kanuni_api.routes.health.check_database_connection", _fake_check)
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 503
    body: dict[str, Any] = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == {"database": False}
