"""Parameterized SQL for the `queries` table: query logging for analytics, evals, and cost (§6)."""

from uuid import UUID

import asyncpg


async def log_query(
    connection: asyncpg.Connection,
    *,
    api_key_id: UUID | None,
    question: str,
    retrieved_chunk_ids: list[UUID],
    confidence: float | None,
    answered: bool,
    latency_ms: int,
    token_cost: float | None,
) -> None:
    """Record one query for analytics, evals, and the cost dashboard (§6, §11).

    Args:
        connection: An open database connection.
        api_key_id: The authenticated caller's key id, if any.
        question: The user's question.
        retrieved_chunk_ids: Chunk ids returned by retrieval, in rank order.
        confidence: The raw top rerank score (ADR 0003 — stored raw, tier
            derived at read time), or `None` if nothing was retrieved.
        answered: Whether an answer was generated (`False` for a refusal).
        latency_ms: End-to-end latency for the query.
        token_cost: Estimated cost in USD, or `None` if generation didn't run.
    """
    await connection.execute(
        """
        INSERT INTO queries (
            api_key_id, question, retrieved_chunk_ids, confidence,
            answered, latency_ms, token_cost
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        api_key_id,
        question,
        retrieved_chunk_ids,
        confidence,
        answered,
        latency_ms,
        token_cost,
    )
