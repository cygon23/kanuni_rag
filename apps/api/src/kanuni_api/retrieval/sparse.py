"""Sparse retrieval: top-k chunks by Postgres full-text search rank."""

import asyncpg

from kanuni_api.models.retrieval import ScoredChunk


async def sparse_search(
    connection: asyncpg.Connection,
    query_text: str,
    *,
    top_k: int,
    include_historical: bool,
) -> list[ScoredChunk]:
    """Find the top-k chunks matching the query via full-text search.

    Args:
        connection: An open database connection.
        query_text: The raw user question.
        top_k: Maximum number of candidates to return (§8.1 default 30).
        include_historical: If False, only `in_force` documents are considered.

    Returns:
        Candidates ordered by descending `ts_rank_cd`, each with `sparse_score` set.

    Note:
        The query is always parsed with the `english` text-search
        configuration. Chunks indexed under `simple` (Swahili — ADR 0004)
        still match on literal, unstemmed terms, but stemmed English-style
        matching doesn't apply to them; dense retrieval (bge-m3, genuinely
        multilingual) compensates for this in the fused result. Revisit if
        eval data (§10) shows this is insufficient for Swahili queries.
    """
    rows = await connection.fetch(
        """
        SELECT c.id, c.document_id, c.content, c.section_ref, c.page_start, c.page_end,
               ts_rank_cd(c.content_tsv, websearch_to_tsquery('english', $1)) AS sparse_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE ($3::boolean OR d.status = 'in_force')
          AND c.content_tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY sparse_score DESC
        LIMIT $2
        """,
        query_text,
        top_k,
        include_historical,
    )
    return [
        ScoredChunk(
            chunk_id=row["id"],
            document_id=row["document_id"],
            content=row["content"],
            section_ref=row["section_ref"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            sparse_score=row["sparse_score"],
        )
        for row in rows
    ]
