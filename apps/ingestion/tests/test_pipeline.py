"""Tests for PipelineRunner orchestration: stage order, short-circuiting, and failure recording.

Job-recording and chunk-write repository calls are monkeypatched (they're
plain SQL functions tested implicitly by the integration suite against a
real Postgres); this suite tests the orchestration logic itself — stage
sequencing, the already-indexed short-circuit, and failure handling — with
an in-memory `FakeDocumentRegistry` and no real database connection.
"""

from uuid import UUID, uuid4

import pytest
from fakes import (
    FakeDocumentRegistry,
    FakeDocumentStorage,
    FakeEmbeddingProvider,
    FakeMetadataExtractionProvider,
    FakeOCREngine,
    make_document_record,
)

from kanuni_ingest.db import chunks_repository, ingestion_jobs_repository
from kanuni_ingest.models import PipelineStage
from kanuni_ingest.pipeline import PipelineRunner


@pytest.fixture(autouse=True)
def _stub_repository_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the real SQL-executing repository calls with no-op stand-ins."""

    async def _fake_next_attempt_count(
        connection: object, document_id: UUID, stage: PipelineStage
    ) -> int:
        return 1

    async def _fake_record_stage_result(
        connection: object,
        document_id: UUID,
        stage: PipelineStage,
        *,
        attempt_count: int,
        error_details: dict[str, object] | None = None,
    ) -> UUID:
        return uuid4()

    async def _fake_replace_chunks(connection: object, document_id: UUID, chunks: list) -> None:  # type: ignore[type-arg]
        return None

    monkeypatch.setattr(ingestion_jobs_repository, "next_attempt_count", _fake_next_attempt_count)
    monkeypatch.setattr(ingestion_jobs_repository, "record_stage_result", _fake_record_stage_result)
    monkeypatch.setattr(chunks_repository, "replace_chunks", _fake_replace_chunks)


def _make_runner(
    *,
    metadata_provider: FakeMetadataExtractionProvider | None = None,
) -> tuple[PipelineRunner, FakeDocumentStorage, FakeEmbeddingProvider]:
    storage = FakeDocumentStorage()
    embedding_provider = FakeEmbeddingProvider()
    runner = PipelineRunner(
        storage=storage,
        ocr_engine=FakeOCREngine(),
        ocr_languages="eng",
        embedding_provider=embedding_provider,
        metadata_provider=metadata_provider or FakeMetadataExtractionProvider(),
        chunk_target_tokens=450,
        chunk_overlap_tokens=60,
    )
    return runner, storage, embedding_provider


@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "1. A minimal regulation clause for pipeline testing.")
    pdf_bytes: bytes = document.tobytes()
    document.close()
    return pdf_bytes


async def test_run_processes_a_document_through_every_stage(minimal_pdf_bytes: bytes) -> None:
    """A fetched document should end up indexed, with every intermediate stage recorded."""
    document = make_document_record(pipeline_status=PipelineStage.FETCHED)
    registry = FakeDocumentRegistry([document])
    runner, storage, embedding_provider = _make_runner()
    storage.seed(document.storage_path, minimal_pdf_bytes)

    await runner.run(connection=object(), registry=registry, document_id=document.id)

    assert (document.id, PipelineStage.EXTRACTED) in registry.pipeline_status_updates
    assert (document.id, PipelineStage.CHUNKED) in registry.pipeline_status_updates
    assert (document.id, PipelineStage.EMBEDDED) in registry.pipeline_status_updates
    assert (document.id, PipelineStage.INDEXED) in registry.pipeline_status_updates
    assert embedding_provider.embedded_texts


async def test_run_skips_a_document_already_indexed() -> None:
    """An already-indexed document must not be reprocessed (idempotent no-op)."""
    document = make_document_record(pipeline_status=PipelineStage.INDEXED)
    registry = FakeDocumentRegistry([document])
    runner, storage, embedding_provider = _make_runner()

    await runner.run(connection=object(), registry=registry, document_id=document.id)

    assert registry.pipeline_status_updates == []
    assert embedding_provider.embedded_texts == []


async def test_run_marks_document_failed_when_a_stage_raises(minimal_pdf_bytes: bytes) -> None:
    """A metadata-extraction validation failure must stop the pipeline and mark it failed."""
    document = make_document_record(pipeline_status=PipelineStage.FETCHED)
    registry = FakeDocumentRegistry([document])
    failing_provider = FakeMetadataExtractionProvider()
    failing_provider.raise_validation_error = True
    runner, storage, _ = _make_runner(metadata_provider=failing_provider)
    storage.seed(document.storage_path, minimal_pdf_bytes)

    await runner.run(connection=object(), registry=registry, document_id=document.id)

    assert (document.id, PipelineStage.FAILED) in registry.pipeline_status_updates
    assert (document.id, PipelineStage.CHUNKED) not in registry.pipeline_status_updates
    assert (document.id, PipelineStage.INDEXED) not in registry.pipeline_status_updates


async def test_run_is_a_no_op_for_an_unknown_document() -> None:
    """A document id that doesn't exist must be logged and skipped, not raise."""
    registry = FakeDocumentRegistry([])
    runner, _, embedding_provider = _make_runner()

    await runner.run(connection=object(), registry=registry, document_id=uuid4())

    assert embedding_provider.embedded_texts == []
