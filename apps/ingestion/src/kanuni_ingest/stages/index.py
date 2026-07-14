"""Index stage: writes embedded chunks and advances the document to `indexed`."""

from uuid import UUID

import asyncpg

from kanuni_ingest.db import chunks_repository
from kanuni_ingest.models import DocumentChunk, PipelineStage
from kanuni_ingest.registry import DocumentRegistryProtocol


async def index_document(
    connection: asyncpg.Connection,
    document_id: UUID,
    chunks: list[DocumentChunk],
    *,
    registry: DocumentRegistryProtocol,
) -> None:
    """Write a document's chunks and mark it indexed, atomically.

    Per PROJECT_SPEC.md §7 stage 5, chunks and embeddings are written in one
    transaction per document; a partially indexed document must never be
    visible to retrieval.

    Args:
        connection: An open database connection, used directly for the
            chunk-replacement transaction.
        document_id: The document being indexed.
        chunks: Fully embedded chunks to write.
        registry: Registry used to advance the document's pipeline status.
    """
    await chunks_repository.replace_chunks(connection, document_id, chunks)
    await registry.update_pipeline_status(document_id, PipelineStage.INDEXED)
