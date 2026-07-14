"""Parameterized SQL for the `ingestion_jobs` table: per-stage attempt records."""

import json
from typing import cast
from uuid import UUID

import asyncpg

from kanuni_ingest.models import IngestionJobRecord, PipelineStage


async def next_attempt_count(
    connection: asyncpg.Connection, document_id: UUID, stage: PipelineStage
) -> int:
    """Compute the attempt number for a document's next try at a given stage.

    Args:
        connection: An open database connection.
        document_id: The document being processed.
        stage: The stage about to be attempted.

    Returns:
        1 for a first attempt, incrementing on each subsequent retry of the
        same stage for the same document.
    """
    previous_max = await connection.fetchval(
        "SELECT max(attempt_count) FROM ingestion_jobs WHERE document_id = $1 AND stage = $2",
        document_id,
        stage.value,
    )
    return int(previous_max) + 1 if previous_max is not None else 1


async def record_stage_result(
    connection: asyncpg.Connection,
    document_id: UUID,
    stage: PipelineStage,
    *,
    attempt_count: int,
    error_details: dict[str, object] | None = None,
) -> UUID:
    """Record the outcome of one pipeline stage attempt.

    Args:
        connection: An open database connection.
        document_id: The document being processed.
        stage: The stage that was attempted (`PipelineStage.FAILED` if it failed).
        attempt_count: The attempt number, from :func:`next_attempt_count`.
        error_details: Structured error details, present only on failure.

    Returns:
        The id of the newly recorded job row.
    """
    job_id = await connection.fetchval(
        """
        INSERT INTO ingestion_jobs (document_id, stage, attempt_count, error_details, completed_at)
        VALUES ($1, $2, $3, $4::jsonb, now())
        RETURNING id
        """,
        document_id,
        stage.value,
        attempt_count,
        json.dumps(error_details) if error_details is not None else None,
    )
    return cast(UUID, job_id)


async def list_failed(connection: asyncpg.Connection) -> list[IngestionJobRecord]:
    """List the most recent failed attempt for every document that has one.

    Args:
        connection: An open database connection.

    Returns:
        One record per failed document, most recent failure first.
    """
    rows = await connection.fetch(
        """
        SELECT DISTINCT ON (document_id) id, document_id, stage, attempt_count, error_details
        FROM ingestion_jobs
        WHERE stage = 'failed'
        ORDER BY document_id, started_at DESC
        """
    )
    return [
        IngestionJobRecord(
            id=row["id"],
            document_id=row["document_id"],
            stage=PipelineStage(row["stage"]),
            attempt_count=row["attempt_count"],
            error_details=(
                json.loads(row["error_details"]) if row["error_details"] is not None else None
            ),
        )
        for row in rows
    ]
