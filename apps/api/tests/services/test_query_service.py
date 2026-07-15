"""Tests for the query orchestrator: confidence gate, streaming, citation validation, logging."""

import json
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from api_fakes import FakeEmbeddingProvider, FakeLLMProvider, FakeRerankerProvider

from kanuni_api.config import Settings
from kanuni_api.db import documents_repository, queries_repository
from kanuni_api.models.document import DocumentStatus, DocumentSummary, DocumentType, PipelineStage
from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.services import query_service

_SETTINGS = Settings(
    confidence_refuse_threshold=0.30, confidence_caution_threshold=0.55, active_prompt_version="v1"
)


def _done_data(event: dict[str, Any]) -> Any:
    """Parse a `done` event's `data`, which `run_query` yields as a JSON string.

    `EventSourceResponse`'s default wire encoding calls plain `str()` on a
    dict `data` value (not `json.dumps`), so `run_query` pre-serializes it
    itself — see the docstring on `run_query`. Tests exercise the events
    `run_query` yields directly (never going through actual SSE encoding),
    so they must parse it back out the same way.
    """
    assert isinstance(event["data"], str)
    return json.loads(event["data"])


def _document(document_id: object, **overrides: object) -> DocumentSummary:
    defaults: dict[str, object] = {
        "id": document_id,
        "source_id": "bot",
        "title": "Licensing Regulations",
        "doc_type": DocumentType.REGULATION,
        "jurisdiction": "Tanzania",
        "issuing_body": "Bank of Tanzania",
        "reference_number": "G.N. No. 297",
        "language": "en",
        "issued_date": date(2014, 8, 22),
        "effective_date": None,
        "status": DocumentStatus.IN_FORCE,
        "pipeline_status": PipelineStage.INDEXED,
    }
    defaults.update(overrides)
    return DocumentSummary.model_validate(defaults)


async def _fake_find_storage_path(connection: object, document_id: object) -> str | None:
    return "abc123.pdf"


def _chunk(document_id: object, rerank_score: float) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=uuid4(),
        document_id=document_id,  # type: ignore[arg-type]
        content="Applicants must hold minimum capital.",
        section_ref="s.5",
        page_start=3,
        page_end=3,
        rerank_score=rerank_score,
    )


@pytest.fixture(autouse=True)
def _stub_query_log(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    logged: list[dict[str, object]] = []

    async def _fake_log_query(connection: object, **kwargs: object) -> None:
        logged.append(kwargs)

    monkeypatch.setattr(queries_repository, "log_query", _fake_log_query)
    return logged


async def test_refuses_when_nothing_is_retrieved(monkeypatch: pytest.MonkeyPatch) -> None:
    """No retrieved chunks must produce an immediate refusal — no LLM call."""

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[ScoredChunk]:
        return []

    monkeypatch.setattr(query_service, "retrieve", _fake_retrieve)
    llm = FakeLLMProvider()

    events = [
        event
        async for event in query_service.run_query(
            connection=object(),
            question="What is the minimum capital?",
            settings=_SETTINGS,
            embedding_provider=FakeEmbeddingProvider(),
            reranker_provider=FakeRerankerProvider(),
            llm_provider=llm,
            api_key_id=None,
        )
    ]

    assert len(events) == 1
    assert _done_data(events[0])["confidence"] == "refuse"
    assert _done_data(events[0])["answered"] is False
    assert llm.calls == []


async def test_refuses_when_top_score_is_below_refuse_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A low top rerank_score must refuse without calling the LLM (§8.2)."""
    document_id = uuid4()
    chunk = _chunk(document_id, rerank_score=0.1)

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[ScoredChunk]:
        return [chunk]

    async def _fake_find_by_id(connection: object, requested_id: object) -> DocumentSummary:
        return _document(requested_id)

    monkeypatch.setattr(query_service, "retrieve", _fake_retrieve)
    monkeypatch.setattr(documents_repository, "find_by_id", _fake_find_by_id)
    llm = FakeLLMProvider()

    events = [
        event
        async for event in query_service.run_query(
            connection=object(),
            question="What is the minimum capital?",
            settings=_SETTINGS,
            embedding_provider=FakeEmbeddingProvider(),
            reranker_provider=FakeRerankerProvider(),
            llm_provider=llm,
            api_key_id=None,
        )
    ]

    refusal_data = _done_data(events[-1])
    assert refusal_data["confidence"] == "refuse"
    assert refusal_data["pointers"][0]["document_id"] == str(document_id)
    assert llm.calls == []


async def test_answers_and_streams_tokens_when_confidence_is_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confident retrieval must stream tokens and end with a citations-bearing done event."""
    document_id = uuid4()
    chunk = _chunk(document_id, rerank_score=0.9)

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[ScoredChunk]:
        return [chunk]

    async def _fake_find_by_id(connection: object, requested_id: object) -> DocumentSummary:
        return _document(requested_id)

    monkeypatch.setattr(query_service, "retrieve", _fake_retrieve)
    monkeypatch.setattr(documents_repository, "find_by_id", _fake_find_by_id)
    monkeypatch.setattr(documents_repository, "find_storage_path", _fake_find_storage_path)
    llm = FakeLLMProvider(text_deltas=["Banks need capital. ", f"[chunk:{chunk.chunk_id}]"])

    events = [
        event
        async for event in query_service.run_query(
            connection=object(),
            question="What is the minimum capital?",
            settings=_SETTINGS,
            embedding_provider=FakeEmbeddingProvider(),
            reranker_provider=FakeRerankerProvider(),
            llm_provider=llm,
            api_key_id=None,
        )
    ]

    token_events = [event for event in events if event["event"] == "token"]
    done_event = events[-1]
    assert done_event["event"] == "done"
    assert "".join(str(event["data"]) for event in token_events) == (
        f"Banks need capital. [chunk:{chunk.chunk_id}]"
    )
    done_data = _done_data(done_event)
    assert done_data["confidence"] == "ok"
    assert done_data["answered"] is True
    assert done_data["citations"][0]["chunk_id"] == str(chunk.chunk_id)
    assert done_data["prompt_tokens"] == 100


async def test_zero_valid_citations_converts_answer_to_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An LLM answer that cites nothing real must be converted to a refusal (§8.3)."""
    document_id = uuid4()
    chunk = _chunk(document_id, rerank_score=0.9)

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[ScoredChunk]:
        return [chunk]

    async def _fake_find_by_id(connection: object, requested_id: object) -> DocumentSummary:
        return _document(requested_id)

    monkeypatch.setattr(query_service, "retrieve", _fake_retrieve)
    monkeypatch.setattr(documents_repository, "find_by_id", _fake_find_by_id)
    monkeypatch.setattr(documents_repository, "find_storage_path", _fake_find_storage_path)
    llm = FakeLLMProvider(text_deltas=[f"Made up. [chunk:{uuid4()}]"])

    events = [
        event
        async for event in query_service.run_query(
            connection=object(),
            question="What is the minimum capital?",
            settings=_SETTINGS,
            embedding_provider=FakeEmbeddingProvider(),
            reranker_provider=FakeRerankerProvider(),
            llm_provider=llm,
            api_key_id=None,
        )
    ]

    zero_citation_data = _done_data(events[-1])
    assert zero_citation_data["confidence"] == "refuse"
    assert zero_citation_data["answered"] is False


async def test_answered_query_is_logged(
    monkeypatch: pytest.MonkeyPatch, _stub_query_log: list[dict[str, object]]
) -> None:
    """A successfully answered query must be logged with answered=True and a token cost."""
    document_id = uuid4()
    chunk = _chunk(document_id, rerank_score=0.9)

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[ScoredChunk]:
        return [chunk]

    async def _fake_find_by_id(connection: object, requested_id: object) -> DocumentSummary:
        return _document(requested_id)

    monkeypatch.setattr(query_service, "retrieve", _fake_retrieve)
    monkeypatch.setattr(documents_repository, "find_by_id", _fake_find_by_id)
    monkeypatch.setattr(documents_repository, "find_storage_path", _fake_find_storage_path)
    llm = FakeLLMProvider(text_deltas=[f"Answer. [chunk:{chunk.chunk_id}]"])

    async for _ in query_service.run_query(
        connection=object(),
        question="q",
        settings=_SETTINGS,
        embedding_provider=FakeEmbeddingProvider(),
        reranker_provider=FakeRerankerProvider(),
        llm_provider=llm,
        api_key_id=None,
    ):
        pass

    assert len(_stub_query_log) == 1
    assert _stub_query_log[0]["answered"] is True
    assert _stub_query_log[0]["token_cost"] is not None
