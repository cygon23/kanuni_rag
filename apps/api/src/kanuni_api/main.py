"""FastAPI application factory: wires middleware, exception handlers, and routes only."""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from kanuni_api.config import get_settings
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.middleware.request_id import RequestIDMiddleware
from kanuni_api.routes import health
from kanuni_api.telemetry.logging import configure_logging


def create_app() -> FastAPI:
    """Construct and configure the Kanuni FastAPI application.

    Returns:
        A fully configured FastAPI app: logging is initialized, middleware
        (CORS, request-id) and global exception handlers are registered,
        and all routers are mounted.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Kanuni API", version="0.1.0")

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)

    return app


app = create_app()
