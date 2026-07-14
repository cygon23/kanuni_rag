"""Parameterized SQL for the `documents` table (ingestion worker's own copy — see ADR 0005)."""

from datetime import date
from uuid import UUID

import asyncpg

from kanuni_ingest.models import DocumentRecord, DocumentStatus, DocumentType, PipelineStage

_PENDING_STAGES = (
    PipelineStage.FETCHED.value,
    PipelineStage.EXTRACTED.value,
    PipelineStage.CHUNKED.value,
    PipelineStage.EMBEDDED.value,
)


def _row_to_record(row: asyncpg.Record) -> DocumentRecord:
    return DocumentRecord(
        id=row["id"],
        source_id=row["source_id"],
        title=row["title"],
        doc_type=DocumentType(row["doc_type"]),
        jurisdiction=row["jurisdiction"],
        issuing_body=row["issuing_body"],
        reference_number=row["reference_number"],
        language=row["language"],
        issued_date=row["issued_date"],
        effective_date=row["effective_date"],
        status=DocumentStatus(row["status"]),
        file_sha256=row["file_sha256"],
        storage_path=row["storage_path"],
        pipeline_status=PipelineStage(row["pipeline_status"]),
    )


async def find_by_id(connection: asyncpg.Connection, document_id: UUID) -> DocumentRecord | None:
    """Fetch a document by its id.

    Args:
        connection: An open database connection.
        document_id: The document's id.

    Returns:
        The document, or `None` if no such document exists.
    """
    row = await connection.fetchrow("SELECT * FROM documents WHERE id = $1", document_id)
    return _row_to_record(row) if row is not None else None


async def find_by_sha256(connection: asyncpg.Connection, file_sha256: str) -> DocumentRecord | None:
    """Fetch a document by its file hash, for dedup checks.

    Args:
        connection: An open database connection.
        file_sha256: The SHA-256 hex digest of the original file.

    Returns:
        The document, or `None` if no document with that hash exists.
    """
    row = await connection.fetchrow("SELECT * FROM documents WHERE file_sha256 = $1", file_sha256)
    return _row_to_record(row) if row is not None else None


async def find_by_reference_number(
    connection: asyncpg.Connection, reference_number: str
) -> DocumentRecord | None:
    """Fetch a document by its reference number, for supersession/amendment resolution.

    Args:
        connection: An open database connection.
        reference_number: The normalized reference number to look up.

    Returns:
        The document, or `None` if no document with that reference number
        has been ingested (yet).
    """
    row = await connection.fetchrow(
        "SELECT * FROM documents WHERE reference_number = $1", reference_number
    )
    return _row_to_record(row) if row is not None else None


async def find_pending(connection: asyncpg.Connection) -> list[DocumentRecord]:
    """Fetch every document whose pipeline has not finished (or permanently failed).

    Args:
        connection: An open database connection.

    Returns:
        Documents with `pipeline_status` in `fetched|extracted|chunked|embedded`,
        oldest first — this is what the worker polls (§4.2 resumability).
    """
    rows = await connection.fetch(
        "SELECT * FROM documents WHERE pipeline_status = ANY($1::text[]) ORDER BY ingested_at",
        list(_PENDING_STAGES),
    )
    return [_row_to_record(row) for row in rows]


async def update_pipeline_status(
    connection: asyncpg.Connection, document_id: UUID, pipeline_status: PipelineStage
) -> None:
    """Advance (or fail) a document's pipeline status.

    Args:
        connection: An open database connection.
        document_id: The document to update.
        pipeline_status: The new pipeline status.
    """
    await connection.execute(
        "UPDATE documents SET pipeline_status = $2, updated_at = now() WHERE id = $1",
        document_id,
        pipeline_status.value,
    )


async def update_status(
    connection: asyncpg.Connection, document_id: UUID, status: DocumentStatus
) -> None:
    """Update a document's in-force/superseded/repealed status.

    Args:
        connection: An open database connection.
        document_id: The document to update.
        status: The new status.
    """
    await connection.execute(
        "UPDATE documents SET status = $2, updated_at = now() WHERE id = $1",
        document_id,
        status.value,
    )


async def fill_missing_metadata(
    connection: asyncpg.Connection,
    document_id: UUID,
    *,
    reference_number: str | None,
    issuing_body: str | None,
    issued_date: date | None,
    effective_date: date | None,
) -> None:
    """Fill any of `reference_number`/`issuing_body`/`issued_date`/`effective_date` left unset.

    Values already present (e.g. supplied by an admin at upload time) take
    precedence over pipeline-extracted ones and are never overwritten.

    Args:
        connection: An open database connection.
        document_id: The document to update.
        reference_number: Extracted reference number, if any.
        issuing_body: Extracted issuing body, if any.
        issued_date: Extracted issue date, if any.
        effective_date: Extracted effective date, if any.
    """
    await connection.execute(
        """
        UPDATE documents
        SET reference_number = COALESCE(documents.reference_number, $2),
            issuing_body = COALESCE(documents.issuing_body, $3),
            issued_date = COALESCE(documents.issued_date, $4),
            effective_date = COALESCE(documents.effective_date, $5),
            updated_at = now()
        WHERE id = $1
        """,
        document_id,
        reference_number,
        issuing_body,
        issued_date,
        effective_date,
    )
