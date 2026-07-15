"""Orchestrates ingestion pipeline stages end-to-end, resumable from the last completed stage.

Stage granularity matches `documents.pipeline_status` / `ingestion_jobs.stage`
exactly (`fetched|extracted|chunked|embedded|indexed|failed` — migration
`0001`): `chunked` covers PROJECT_SPEC.md §7's stage 3 (structure & chunk)
*and* stage 4 (metadata & versioning), since there is no separate enum
value for the latter; `embedded`/`indexed` split stage 5 (embed & index)
into its two halves.
"""

from uuid import UUID

import asyncpg
import sentry_sdk
import structlog

from kanuni_ingest.db import ingestion_jobs_repository
from kanuni_ingest.embedding import EmbeddingProvider
from kanuni_ingest.metadata_extraction import MetadataExtractionProvider
from kanuni_ingest.models import PipelineStage
from kanuni_ingest.registry import DocumentRegistryProtocol
from kanuni_ingest.stages import chunk as chunk_stage
from kanuni_ingest.stages import embed as embed_stage
from kanuni_ingest.stages import extract as extract_stage
from kanuni_ingest.stages import index as index_stage
from kanuni_ingest.stages.ocr import OCREngine
from kanuni_ingest.storage import DocumentStorage
from kanuni_ingest.versioning import apply_metadata_and_versioning

logger = structlog.get_logger()


async def _record_success(
    connection: asyncpg.Connection,
    registry: DocumentRegistryProtocol,
    document_id: UUID,
    stage: PipelineStage,
) -> None:
    attempt = await ingestion_jobs_repository.next_attempt_count(connection, document_id, stage)
    await ingestion_jobs_repository.record_stage_result(
        connection, document_id, stage, attempt_count=attempt
    )
    await registry.update_pipeline_status(document_id, stage)


async def _record_failure(
    connection: asyncpg.Connection,
    registry: DocumentRegistryProtocol,
    document_id: UUID,
    exc: Exception,
) -> None:
    # A per-document stage failure never re-raises (the worker loop must
    # keep processing the rest of the batch — §7's failure policy), so
    # without an explicit capture here Sentry would never see it.
    sentry_sdk.capture_exception(exc)
    attempt = await ingestion_jobs_repository.next_attempt_count(
        connection, document_id, PipelineStage.FAILED
    )
    await ingestion_jobs_repository.record_stage_result(
        connection,
        document_id,
        PipelineStage.FAILED,
        attempt_count=attempt,
        error_details={"error": str(exc), "error_type": type(exc).__name__},
    )
    await registry.update_pipeline_status(document_id, PipelineStage.FAILED)


class PipelineRunner:
    """Runs extract -> chunk+metadata/versioning -> embed -> index for one document."""

    def __init__(
        self,
        *,
        storage: DocumentStorage,
        ocr_engine: OCREngine,
        ocr_languages: str,
        embedding_provider: EmbeddingProvider,
        metadata_provider: MetadataExtractionProvider,
        chunk_target_tokens: int,
        chunk_overlap_tokens: int,
    ) -> None:
        """Configure the pipeline with its providers.

        Args:
            storage: Backend used to read the original document bytes.
            ocr_engine: OCR engine for pages without a native text layer.
            ocr_languages: Tesseract language codes, e.g. `"eng+swa"`.
            embedding_provider: Provider used to embed chunk content.
            metadata_provider: Provider used for the metadata LLM call.
            chunk_target_tokens: Target chunk size in approximate tokens.
            chunk_overlap_tokens: Approximate token overlap between chunks.
        """
        self._storage = storage
        self._ocr_engine = ocr_engine
        self._ocr_languages = ocr_languages
        self._embedding_provider = embedding_provider
        self._metadata_provider = metadata_provider
        self._chunk_target_tokens = chunk_target_tokens
        self._chunk_overlap_tokens = chunk_overlap_tokens

    async def run(
        self,
        connection: asyncpg.Connection,
        registry: DocumentRegistryProtocol,
        document_id: UUID,
    ) -> None:
        """Process one document through every remaining pipeline stage.

        A stage failure marks the document `failed` and stops the pipeline
        for this run — per §7's failure policy, the document is never
        partially searchable. Each successful stage transition is recorded
        immediately, so a subsequent call resumes cleanly (§4.2): stages
        already reflected in `documents.pipeline_status` are simply
        recomputed from the (already-fetched) source bytes, and the final
        chunk write is idempotent (see `chunks_repository.replace_chunks`).

        Args:
            connection: An open database connection, held for the duration
                of processing this document — used directly for the
                job-recording and chunk-write repository calls.
            registry: Registry wrapping the same connection, used for
                document-level lookups and updates. Passed in (rather than
                constructed here) so tests can inject an in-memory fake.
            document_id: The document to process.
        """
        document = await registry.find_by_id(document_id)
        if document is None:
            logger.warning("document_not_found", document_id=str(document_id))
            return
        if document.pipeline_status == PipelineStage.INDEXED:
            logger.info("document_already_indexed", document_id=str(document_id))
            return

        try:
            pdf_bytes = await self._storage.read(document.storage_path)

            extracted = await extract_stage.extract_document(
                pdf_bytes, ocr_engine=self._ocr_engine, ocr_languages=self._ocr_languages
            )
            await _record_success(connection, registry, document_id, PipelineStage.EXTRACTED)

            full_text = "\n\n".join(page.text for page in extracted.pages)
            await apply_metadata_and_versioning(
                document_id,
                full_text,
                registry=registry,
                metadata_provider=self._metadata_provider,
            )

            chunks = chunk_stage.chunk_document(
                pdf_bytes,
                extracted,
                target_tokens=self._chunk_target_tokens,
                overlap_tokens=self._chunk_overlap_tokens,
                language=document.language,
            )
            await _record_success(connection, registry, document_id, PipelineStage.CHUNKED)

            embedded_chunks = await embed_stage.embed_chunks(
                chunks, embedding_provider=self._embedding_provider
            )
            await _record_success(connection, registry, document_id, PipelineStage.EMBEDDED)

            await index_stage.index_document(
                connection, document_id, embedded_chunks, registry=registry
            )
            await _record_success(connection, registry, document_id, PipelineStage.INDEXED)

        except Exception as exc:
            logger.error("pipeline_stage_failed", document_id=str(document_id), error=str(exc))
            await _record_failure(connection, registry, document_id, exc)
