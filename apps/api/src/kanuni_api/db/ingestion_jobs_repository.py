"""Parameterized SQL for the `ingestion_jobs` table (API's own copy — see ADR 0005)."""

import json
from uuid import UUID

import asyncpg

from kanuni_api.models.document import PipelineStage
from kanuni_api.models.ingestion_job import IngestionJobSummary


async def list_failed(connection: asyncpg.Connection) -> list[IngestionJobSummary]:
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
        IngestionJobSummary(
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


async def reset_for_retry(connection: asyncpg.Connection, document_id: UUID) -> None:
    """Reset a failed document to `fetched` so the worker reprocesses it.

    Args:
        connection: An open database connection.
        document_id: The document to reset.
    """
    await connection.execute(
        "UPDATE documents SET pipeline_status = 'fetched', updated_at = now() WHERE id = $1",
        document_id,
    )
