"""Global exception handlers mapping domain and unexpected errors to RFC 7807 responses."""

from typing import Any

import sentry_sdk
import structlog
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from kanuni_api.exceptions import KanuniError

logger = structlog.get_logger()

PROBLEM_CONTENT_TYPE = "application/problem+json"


def _problem_response(
    *, status_code: int, error_code: str, title: str, detail: str, instance: str
) -> JSONResponse:
    """Build an RFC 7807 problem-details JSON response.

    Args:
        status_code: HTTP status code for the response.
        error_code: Stable, machine-readable error identifier for clients.
        title: Short human-readable summary of the error type.
        detail: User-safe explanation specific to this occurrence. Must
            never contain stack traces, SQL, or upstream provider payloads.
        instance: URI (request path) identifying the specific occurrence.

    Returns:
        A JSONResponse using the ``application/problem+json`` content type.
    """
    content: dict[str, Any] = {
        "type": f"https://kanuni.dev/errors/{error_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "error_code": error_code,
    }
    return JSONResponse(status_code=status_code, content=content, media_type=PROBLEM_CONTENT_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    """Register the domain, validation, and catch-all exception handlers on an app.

    Args:
        app: The FastAPI application to register handlers on.
    """

    @app.exception_handler(KanuniError)
    async def handle_kanuni_error(request: Request, exc: KanuniError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "request_failed",
            error_code=exc.error_code,
            status_code=exc.status_code,
            request_id=request_id,
            path=request.url.path,
        )
        return _problem_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            title=type(exc).__name__,
            detail=exc.detail,
            instance=request.url.path,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "request_validation_failed",
            request_id=request_id,
            path=request.url.path,
        )
        return _problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code="validation_failed",
            title="ValidationFailedError",
            detail="The request failed validation.",
            instance=request.url.path,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "unhandled_exception",
            request_id=request_id,
            path=request.url.path,
            exc_info=exc,
        )
        # This handler is what keeps the exception from propagating to
        # Sentry's ASGI-level auto-capture, so it must report explicitly.
        sentry_sdk.capture_exception(exc)
        return _problem_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="internal_error",
            title="InternalServerError",
            detail="An unexpected error occurred. Please try again later.",
            instance=request.url.path,
        )
