"""FastAPI dependency providers: database connection pool and model providers."""

from collections.abc import AsyncIterator
from typing import Annotated

import asyncpg
from fastapi import Depends, Request

from kanuni_api.embedding import EmbeddingProvider
from kanuni_api.generation.llm_client import LLMProvider
from kanuni_api.reranker import RerankerProvider
from kanuni_api.storage import DocumentStorage


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Return the app-wide connection pool created at startup.

    Args:
        request: The current request, used to reach `app.state`.

    Returns:
        The connection pool.
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    return pool


async def get_db_connection(
    pool: Annotated[asyncpg.Pool, Depends(get_db_pool)],
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection from the pool for the duration of one request.

    Args:
        pool: The app-wide connection pool.

    Yields:
        A connection, released back to the pool when the request completes.
    """
    async with pool.acquire() as connection:
        yield connection


DbConnection = Annotated[asyncpg.Connection, Depends(get_db_connection)]


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    """Return the app-wide embedding provider created at startup.

    Args:
        request: The current request, used to reach `app.state`.

    Returns:
        The embedding provider. The underlying model is loaded lazily on
        first use, not at startup — importing/constructing this dependency
        never downloads model weights by itself.
    """
    provider: EmbeddingProvider = request.app.state.embedding_provider
    return provider


def get_reranker_provider(request: Request) -> RerankerProvider:
    """Return the app-wide reranker provider created at startup.

    Args:
        request: The current request, used to reach `app.state`.

    Returns:
        The reranker provider (lazy-loaded, as with the embedding provider).
    """
    provider: RerankerProvider = request.app.state.reranker_provider
    return provider


def get_llm_provider(request: Request) -> LLMProvider:
    """Return the app-wide LLM provider created at startup.

    Args:
        request: The current request, used to reach `app.state`.

    Returns:
        The LLM provider (a `FallbackLLMProvider` wrapping Groq, per §2's
        "fallback slot" — a no-op wrapper if no fallback is configured).
    """
    provider: LLMProvider = request.app.state.llm_provider
    return provider


def get_storage(request: Request) -> DocumentStorage:
    """Return the app-wide document storage backend created at startup.

    Args:
        request: The current request, used to reach `app.state`.

    Returns:
        The storage backend (a `SupabaseStorage` in production; tests
        override this dependency directly rather than hitting real
        Supabase Storage over the network, per §13).
    """
    storage: DocumentStorage = request.app.state.storage
    return storage


EmbeddingProviderDep = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]
RerankerProviderDep = Annotated[RerankerProvider, Depends(get_reranker_provider)]
LlmProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]
StorageDep = Annotated[DocumentStorage, Depends(get_storage)]
