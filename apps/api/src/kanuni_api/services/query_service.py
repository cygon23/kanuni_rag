"""Orchestrates the query path: retrieve -> confidence gate -> generate -> validate -> log (§8)."""

import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from kanuni_api.config import Settings
from kanuni_api.db import documents_repository, queries_repository
from kanuni_api.embedding import EmbeddingProvider
from kanuni_api.generation.citation import validate_citations
from kanuni_api.generation.confidence import compute_confidence_tier
from kanuni_api.generation.llm_client import LLMProvider
from kanuni_api.generation.prompt_loader import build_system_prompt
from kanuni_api.models.document import DocumentSummary
from kanuni_api.models.query import DocumentPointer, QueryResultMetadata, ResolvedCitation
from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.reranker import RerankerProvider
from kanuni_api.services.retrieval_service import retrieve
from kanuni_api.storage import public_url

logger = structlog.get_logger()

# Illustrative per-token pricing for llama-3.3-70b-versatile (USD). Not
# exact billing — a placeholder until real Groq pricing is wired in from
# their published rate card; revisit before citing real cost numbers.
_PROMPT_COST_PER_TOKEN = 0.00000059
_COMPLETION_COST_PER_TOKEN = 0.00000079

_HISTORICAL_DISCLOSURE_KEYWORDS = ("supersed", "repeal", "historical", "no longer in force")


async def run_query(
    connection: asyncpg.Connection,
    question: str,
    *,
    settings: Settings,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    llm_provider: LLMProvider,
    api_key_id: UUID | None,
    include_historical: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Run the full query path, yielding SSE-shaped events as they're ready.

    Args:
        connection: An open database connection.
        question: The user's question.
        settings: Application settings (thresholds, prompt version).
        embedding_provider: Provider used to embed the question.
        reranker_provider: Provider used for cross-encoder reranking.
        llm_provider: Provider used for answer generation.
        api_key_id: The authenticated caller's key id, for query logging.
        include_historical: If True, include superseded/repealed documents.

    Yields:
        `{"event": "token", "data": <str>}` for each streamed text delta,
        followed by exactly one `{"event": "done", "data": <str>}` whose
        `data` is `QueryResultMetadata` serialized as a JSON string —
        `EventSourceResponse`'s default `ServerSentEvent` encodes a dict
        `data` value via plain `str()`, not `json.dumps` (only
        `JSONServerSentEvent` does that), so `data` must already be a
        string here or the wire format is invalid JSON (Python repr, e.g.
        single-quoted keys and `True`/`None`).
    """
    start_time = time.monotonic()
    scored_chunks = await retrieve(
        connection,
        question,
        settings=settings,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
        include_historical=include_historical,
    )

    top_score = scored_chunks[0].rerank_score if scored_chunks else None
    confidence = compute_confidence_tier(
        top_score,
        refuse_threshold=settings.confidence_refuse_threshold,
        caution_threshold=settings.confidence_caution_threshold,
    )

    if confidence == "refuse":
        async for event in _refuse(
            connection, question, scored_chunks, top_score, start_time, api_key_id
        ):
            yield event
        return

    documents_by_id = await _load_documents(connection, scored_chunks)
    source_urls_by_document_id = await _load_source_urls(connection, settings, scored_chunks)
    system_prompt = build_system_prompt(
        settings.active_prompt_version, scored_chunks, documents_by_id
    )

    answer_text = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    async for chunk in llm_provider.generate(system_prompt=system_prompt, user_prompt=question):
        if chunk.text_delta:
            answer_text += chunk.text_delta
            yield {"event": "token", "data": chunk.text_delta}
        if chunk.prompt_tokens is not None:
            prompt_tokens = chunk.prompt_tokens
            completion_tokens = chunk.completion_tokens

    valid_chunk_ids = {chunk.chunk_id for chunk in scored_chunks}
    validated = validate_citations(answer_text, valid_chunk_ids)

    if not validated.has_valid_citations:
        logger.warning("answer_had_zero_valid_citations_converted_to_refusal")
        async for event in _refuse(
            connection, question, scored_chunks, top_score, start_time, api_key_id
        ):
            yield event
        return

    citations = [
        ResolvedCitation(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_title=documents_by_id[chunk.document_id].title,
            reference_number=documents_by_id[chunk.document_id].reference_number,
            section_ref=chunk.section_ref,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            status=documents_by_id[chunk.document_id].status,
            content=chunk.content,
            source_url=source_urls_by_document_id.get(chunk.document_id),
        )
        for chunk in scored_chunks
        if chunk.chunk_id in validated.valid_chunk_ids
    ]
    _flag_undisclosed_historical_citations(validated.text, citations)

    latency_ms = _elapsed_ms(start_time)
    token_cost = _estimate_cost(prompt_tokens, completion_tokens)
    metadata = QueryResultMetadata(
        confidence=confidence,
        answered=True,
        citations=citations,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        citation_density=validated.citation_density,
        latency_ms=latency_ms,
    )
    await queries_repository.log_query(
        connection,
        api_key_id=api_key_id,
        question=question,
        retrieved_chunk_ids=[chunk.chunk_id for chunk in scored_chunks],
        confidence=top_score,
        answered=True,
        latency_ms=latency_ms,
        token_cost=token_cost,
    )
    yield {"event": "done", "data": metadata.model_dump_json()}


async def _refuse(
    connection: asyncpg.Connection,
    question: str,
    scored_chunks: list[ScoredChunk],
    top_score: float | None,
    start_time: float,
    api_key_id: UUID | None,
) -> AsyncIterator[dict[str, Any]]:
    """Build and log a structured refusal, per §8.2 — never generates an answer."""
    pointers = await _nearest_document_pointers(connection, scored_chunks)
    latency_ms = _elapsed_ms(start_time)
    metadata = QueryResultMetadata(
        confidence="refuse", answered=False, pointers=pointers, latency_ms=latency_ms
    )
    await queries_repository.log_query(
        connection,
        api_key_id=api_key_id,
        question=question,
        retrieved_chunk_ids=[chunk.chunk_id for chunk in scored_chunks],
        confidence=top_score,
        answered=False,
        latency_ms=latency_ms,
        token_cost=None,
    )
    yield {"event": "done", "data": metadata.model_dump_json()}


def _elapsed_ms(start_time: float) -> int:
    return int((time.monotonic() - start_time) * 1000)


async def _load_documents(
    connection: asyncpg.Connection, chunks: list[ScoredChunk]
) -> dict[UUID, DocumentSummary]:
    documents: dict[UUID, DocumentSummary] = {}
    for document_id in {chunk.document_id for chunk in chunks}:
        document = await documents_repository.find_by_id(connection, document_id)
        if document is not None:
            documents[document_id] = document
    return documents


async def _load_source_urls(
    connection: asyncpg.Connection, settings: Settings, chunks: list[ScoredChunk]
) -> dict[UUID, str]:
    """Build each cited document's public Supabase Storage URL, for the citation side panel.

    Args:
        connection: An open database connection.
        settings: Application settings (Supabase project URL and bucket).
        chunks: The chunks whose documents need a source URL.

    Returns:
        A mapping of document id to public PDF URL. A document with no
        stored file (shouldn't happen for an indexed document, but
        `find_storage_path` can still return `None`) is simply omitted —
        `ResolvedCitation.source_url` is optional for exactly this case.
    """
    source_urls: dict[UUID, str] = {}
    for document_id in {chunk.document_id for chunk in chunks}:
        storage_path = await documents_repository.find_storage_path(connection, document_id)
        if storage_path is not None:
            source_urls[document_id] = public_url(
                base_url=settings.supabase_url,
                bucket=settings.storage_bucket,
                storage_path=storage_path,
            )
    return source_urls


async def _nearest_document_pointers(
    connection: asyncpg.Connection, scored_chunks: list[ScoredChunk]
) -> list[DocumentPointer]:
    """Build up to 3 nearest-document pointers for a refusal response (§8.2)."""
    documents_by_id = await _load_documents(connection, scored_chunks)
    seen: set[UUID] = set()
    pointers: list[DocumentPointer] = []
    for chunk in scored_chunks:
        if chunk.document_id in seen:
            continue
        document = documents_by_id.get(chunk.document_id)
        if document is None:
            continue
        seen.add(chunk.document_id)
        pointers.append(
            DocumentPointer(
                document_id=document.id,
                title=document.title,
                reference_number=document.reference_number,
            )
        )
        if len(pointers) == 3:
            break
    return pointers


def _flag_undisclosed_historical_citations(
    answer_text: str, citations: list[ResolvedCitation]
) -> None:
    """Log (never block) when a non-`in_force` citation isn't disclosed in the answer text."""
    lowered = answer_text.lower()
    for citation in citations:
        if citation.status.value == "in_force":
            continue
        if not any(keyword in lowered for keyword in _HISTORICAL_DISCLOSURE_KEYWORDS):
            logger.warning(
                "possible_undisclosed_historical_citation",
                chunk_id=str(citation.chunk_id),
                document_status=citation.status.value,
            )


def _estimate_cost(prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    if prompt_tokens is None or completion_tokens is None:
        return None
    return prompt_tokens * _PROMPT_COST_PER_TOKEN + completion_tokens * _COMPLETION_COST_PER_TOKEN
