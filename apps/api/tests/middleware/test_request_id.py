"""Tests for RequestIDMiddleware: correlation ID generation, propagation, and log binding."""

import uuid

import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kanuni_api.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware


def _build_app() -> FastAPI:
    """Build a minimal app with only RequestIDMiddleware and a probe endpoint."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/probe")
    async def probe() -> dict[str, str | None]:
        bound_request_id = structlog.contextvars.get_contextvars().get("request_id")
        return {"bound_request_id": bound_request_id}

    return app


def test_generates_a_request_id_when_none_supplied() -> None:
    """Without an incoming X-Request-ID header, a fresh UUID4 should be generated."""
    client = TestClient(_build_app())

    response = client.get("/probe")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert uuid.UUID(request_id).version == 4


def test_echoes_a_caller_supplied_request_id() -> None:
    """A caller-supplied X-Request-ID header should be echoed back unchanged."""
    client = TestClient(_build_app())
    supplied_id = "caller-supplied-id-123"

    response = client.get("/probe", headers={REQUEST_ID_HEADER: supplied_id})

    assert response.headers[REQUEST_ID_HEADER] == supplied_id


def test_binds_request_id_to_structlog_context_during_the_request() -> None:
    """The request ID should be bound to structlog's contextvars while handling the request."""
    client = TestClient(_build_app())
    supplied_id = "log-context-id"

    response = client.get("/probe", headers={REQUEST_ID_HEADER: supplied_id})

    assert response.json()["bound_request_id"] == supplied_id
