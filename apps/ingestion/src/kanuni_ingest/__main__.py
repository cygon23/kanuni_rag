"""Ingestion worker process entry point: `python -m kanuni_ingest`.

Polls for documents whose pipeline hasn't finished (Postgres-backed job
queue per PROJECT_SPEC.md §2, ADR-worthy tradeoff vs. a dedicated queue —
see the Phase 1 handoff summary) and runs them through
:class:`kanuni_ingest.pipeline.PipelineRunner`.
"""

import asyncio

import structlog

from kanuni_ingest.config import get_settings
from kanuni_ingest.db.pool import create_pool
from kanuni_ingest.embedding import Bgem3EmbeddingProvider
from kanuni_ingest.metadata_extraction import GroqMetadataExtractionProvider
from kanuni_ingest.pipeline import PipelineRunner
from kanuni_ingest.registry import DocumentRegistry
from kanuni_ingest.stages.ocr import TesseractOCREngine
from kanuni_ingest.storage import SupabaseStorage
from kanuni_ingest.telemetry.sentry import configure_sentry

logger = structlog.get_logger()


async def run_forever() -> None:
    """Start the ingestion worker process: poll for pending documents and process them."""
    settings = get_settings()
    configure_sentry(dsn=settings.sentry_dsn, release=settings.release_sha)
    pool = await create_pool(settings.database_url)
    runner = PipelineRunner(
        storage=SupabaseStorage(
            base_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            bucket=settings.storage_bucket,
        ),
        ocr_engine=TesseractOCREngine(),
        ocr_languages=settings.ocr_languages,
        embedding_provider=Bgem3EmbeddingProvider(settings.embedding_model),
        metadata_provider=GroqMetadataExtractionProvider(
            api_key=settings.groq_api_key, model=settings.metadata_llm_model
        ),
        chunk_target_tokens=settings.chunk_target_tokens,
        chunk_overlap_tokens=settings.chunk_overlap_tokens,
    )

    logger.info("kanuni_ingest_worker_started")
    try:
        while True:
            async with pool.acquire() as connection:
                pending = await DocumentRegistry(connection).find_pending_documents()
                for document in pending:
                    async with pool.acquire() as processing_connection:
                        processing_registry = DocumentRegistry(processing_connection)
                        await runner.run(processing_connection, processing_registry, document.id)
            await asyncio.sleep(settings.worker_poll_interval_seconds)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_forever())
