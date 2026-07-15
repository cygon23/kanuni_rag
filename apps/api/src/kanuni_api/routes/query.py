"""Query route: POST /v1/query, streamed over SSE (§8.4)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from kanuni_api.config import Settings, get_settings
from kanuni_api.dependencies import (
    DbConnection,
    EmbeddingProviderDep,
    LlmProviderDep,
    RerankerProviderDep,
)
from kanuni_api.middleware.auth import require_scope
from kanuni_api.models.api_key import ApiKeyRecord
from kanuni_api.models.query import QueryRequest
from kanuni_api.services.query_service import run_query

router = APIRouter(prefix="/v1", tags=["query"])

_require_query_scope = require_scope("query")


@router.post("/query")
async def post_query(
    request: QueryRequest,
    connection: DbConnection,
    api_key: Annotated[ApiKeyRecord, Depends(_require_query_scope)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedding_provider: EmbeddingProviderDep,
    reranker_provider: RerankerProviderDep,
    llm_provider: LlmProviderDep,
) -> EventSourceResponse:
    """Answer a question, streamed over SSE: `token` events, then one `done` event.

    Args:
        request: The question and optional retrieval overrides.
        connection: Database connection (injected).
        api_key: The authenticated caller's key (requires `query` scope).
        settings: Application settings.
        embedding_provider: Provider used to embed the question.
        reranker_provider: Provider used for cross-encoder reranking.
        llm_provider: Provider used for answer generation.

    Returns:
        An SSE stream. See `QueryResultMetadata` for the final `done`
        event's payload shape.
    """
    events = run_query(
        connection,
        request.question,
        settings=settings,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
        llm_provider=llm_provider,
        api_key_id=api_key.id,
        include_historical=request.include_historical,
    )
    return EventSourceResponse(events)
