"""FastAPI application factory: wires middleware, exception handlers, and routes only."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from kanuni_api.config import get_settings
from kanuni_api.db.pool import create_pool
from kanuni_api.embedding import Bgem3EmbeddingProvider
from kanuni_api.generation.llm_client import FallbackLLMProvider, GroqLLMProvider
from kanuni_api.middleware.error_handler import register_exception_handlers
from kanuni_api.middleware.request_id import RequestIDMiddleware
from kanuni_api.reranker import Bgereranker
from kanuni_api.routes import admin, documents, health, query
from kanuni_api.storage import SupabaseStorage
from kanuni_api.telemetry.logging import configure_logging
from kanuni_api.telemetry.sentry import configure_sentry


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database pool and model providers at startup; close the pool at shutdown.

    Args:
        app: The FastAPI application, used to stash state on `app.state`.

    Yields:
        Control back to FastAPI while the app is running.
    """
    settings = get_settings()
    app.state.db_pool = await create_pool(settings.database_url)
    # Both providers load their (large) model weights lazily on first use,
    # not here — constructing them at startup is cheap.
    app.state.embedding_provider = Bgem3EmbeddingProvider(settings.embedding_model)
    app.state.reranker_provider = Bgereranker(settings.reranker_model)
    # No second concrete LLMProvider implementation exists yet (§2's
    # "fallback slot" — fallback is None until one is added), so this is a
    # transparent passthrough to Groq for now.
    app.state.llm_provider = FallbackLLMProvider(
        GroqLLMProvider(api_key=settings.groq_api_key, model=settings.llm_model)
    )
    app.state.storage = SupabaseStorage(
        base_url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key,
        bucket=settings.storage_bucket,
    )
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
    configure_sentry(
        dsn=settings.sentry_dsn, environment=settings.environment, release=settings.release_sha
    )

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
    app.include_router(query.router)

    return app


app = create_app()
