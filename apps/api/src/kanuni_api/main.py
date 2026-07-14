"""FastAPI application factory: wires middleware, exception handlers, and routes only."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from kanuni_api.config import get_settings
from kanuni_api.db.pool import create_pool
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.middleware.request_id import RequestIDMiddleware
from kanuni_api.routes import admin, documents, health
from kanuni_api.telemetry.logging import configure_logging


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database connection pool at startup and close it at shutdown.

    Args:
        app: The FastAPI application, used to stash the pool on `app.state`.

    Yields:
        Control back to FastAPI while the app is running.
    """
    settings = get_settings()
    app.state.db_pool = await create_pool(settings.database_url)
    try:
        yield
    finally:
        await app.state.db_pool.close()


def create_app() -> FastAPI:
    """Construct and configure the Kanuni FastAPI application.

    Returns:
        A fully configured FastAPI app: logging is initialized, middleware
        (CORS, request-id) and global exception handlers are registered,
        and all routers are mounted.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Kanuni API", version="0.1.0", lifespan=_lifespan)

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
    app.include_router(documents.router)
    app.include_router(admin.router)

    return app


app = create_app()
