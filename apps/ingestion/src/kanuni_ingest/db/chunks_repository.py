"""Parameterized SQL for the `chunks` table."""

from uuid import UUID

import asyncpg

from kanuni_ingest.models import DocumentChunk


def _format_vector(embedding: list[float]) -> str:
    """Render an embedding as a pgvector text literal.

    Args:
        embedding: The embedding vector.

    Returns:
        A string like `"[0.1,0.2,0.3]"`, suitable for an explicit `::vector`
        cast in SQL — avoids requiring a dedicated asyncpg type codec for a
        single, simple write path.
    """
    return "[" + ",".join(repr(value) for value in embedding) + "]"


async def replace_chunks(
    connection: asyncpg.Connection, document_id: UUID, chunks: list[DocumentChunk]
) -> None:
    """Atomically replace a document's chunks, per PROJECT_SPEC.md §7 stage 5.

    Deleting existing chunks before inserting the new set makes this safe
    to retry: re-running the embed/index stage for a document that already
    has chunks never produces duplicates (§4.2, §13's resumability test).

    Args:
        connection: An open database connection.
        document_id: The document whose chunks are being written.
        chunks: The fully embedded chunks to write, in order.

    Raises:
        ValueError: If any chunk has no embedding — indexing must not run
            before the embed stage has populated every chunk.
    """
    if any(chunk.embedding is None for chunk in chunks):
        raise ValueError("Cannot index chunks that have not been embedded")

    async with connection.transaction():
        await connection.execute("DELETE FROM chunks WHERE document_id = $1", document_id)
        for chunk in chunks:
            assert chunk.embedding is not None  # narrowed by the check above
            await connection.execute(
                """
                INSERT INTO chunks (
                    document_id, section_ref, page_start, page_end,
                    content, embedding, token_count, chunk_index
                )
                VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8)
                """,
                document_id,
                chunk.section_ref,
                chunk.page_start,
                chunk.page_end,
                chunk.content,
                _format_vector(chunk.embedding),
                chunk.token_count,
                chunk.chunk_index,
            )


async def count_chunks(connection: asyncpg.Connection, document_id: UUID) -> int:
    """Count how many chunks a document currently has.

    Args:
        connection: An open database connection.
        document_id: The document to count chunks for.

    Returns:
        The chunk count.
    """
    count = await connection.fetchval(
        "SELECT count(*) FROM chunks WHERE document_id = $1", document_id
    )
    return int(count)
