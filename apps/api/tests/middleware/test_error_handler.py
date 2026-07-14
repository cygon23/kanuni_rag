"""Tests mapping domain, validation, and unexpected errors to RFC 7807 responses."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kanuni_api.exceptions import DocumentNotFoundError
from kanuni_api.middleware.error_handler import PROBLEM_CONTENT_TYPE, register_exception_handlers


def _build_app() -> FastAPI:
    """Build a minimal app with only the global exception handlers and probe endpoints."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/documents/{document_id}")
    async def get_document(document_id: str) -> dict[str, str]:
        raise DocumentNotFoundError()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("something exploded with a secret stack trace")

    @app.get("/validated")
    async def validated(count: int) -> dict[str, int]:
        return {"count": count}

    return app


def test_domain_error_maps_to_rfc7807_problem_response() -> None:
    """A KanuniError subclass should map to its declared status code and error_code."""
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/documents/abc")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["error_code"] == "document_not_found"
    assert body["status"] == 404
    assert body["instance"] == "/documents/abc"


def test_unexpected_exception_maps_to_500_and_hides_internal_detail() -> None:
    """An unhandled exception should become a generic 500 with no leaked internals."""
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "internal_error"
    assert "secret stack trace" not in response.text
    assert "RuntimeError" not in response.text


def test_request_validation_error_maps_to_422_with_stable_error_code() -> None:
    """A FastAPI request validation failure should map to 422 with error_code validation_failed."""
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/validated", params={"count": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_failed"
