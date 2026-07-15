"""Dense retrieval: top-k nearest chunks by cosine similarity over pgvector."""

import asyncpg

from kanuni_api.models.retrieval import ScoredChunk


def _format_vector(embedding: list[float]) -> str:
    """Render an embedding as a pgvector text literal for an explicit `::vector` cast."""
    return "[" + ",".join(repr(value) for value in embedding) + "]"


async def dense_search(
    connection: asyncpg.Connection,
    query_embedding: list[float],
    *,
    top_k: int,
    include_historical: bool,
) -> list[ScoredChunk]:
    """Find the top-k chunks nearest the query embedding by cosine similarity.

    Uses the HNSW index (`vector_cosine_ops`, migration 0001) via the `<=>`
    cosine-distance operator; similarity is `1 - distance`.

    Args:
        connection: An open database connection.
        query_embedding: The embedded user question.
        top_k: Maximum number of candidates to return (§8.1 default 30).
        include_historical: If False, only `in_force` documents are considered.

    Returns:
        Candidates ordered by descending similarity, each with `dense_score` set.
    """
    rows = await connection.fetch(
        """
        SELECT c.id, c.document_id, c.content, c.section_ref, c.page_start, c.page_end,
               1 - (c.embedding <=> $1::vector) AS dense_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE ($2::boolean OR d.status = 'in_force')
        ORDER BY c.embedding <=> $1::vector
        LIMIT $3
        """,
        _format_vector(query_embedding),
        include_historical,
        top_k,
    )
    return [
        ScoredChunk(
            chunk_id=row["id"],
            document_id=row["document_id"],
            content=row["content"],
            section_ref=row["section_ref"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            dense_score=row["dense_score"],
        )
        for row in rows
    ]
