"""Parameterized SQL for the `documents` table (API's own copy — see ADR 0005)."""

from datetime import date
from typing import cast
from uuid import UUID

import asyncpg

from kanuni_api.models.document import (
    DocumentStatus,
    DocumentSummary,
    DocumentType,
    PipelineStage,
)


def _row_to_summary(row: asyncpg.Record) -> DocumentSummary:
    return DocumentSummary(
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
        pipeline_status=PipelineStage(row["pipeline_status"]),
    )


async def find_by_sha256(
    connection: asyncpg.Connection, file_sha256: str
) -> DocumentSummary | None:
    """Fetch a document by its file hash, for dedup checks on upload.

    Args:
        connection: An open database connection.
        file_sha256: The SHA-256 hex digest of the original file.

    Returns:
        The document, or `None` if no document with that hash exists.
    """
    row = await connection.fetchrow("SELECT * FROM documents WHERE file_sha256 = $1", file_sha256)
    return _row_to_summary(row) if row is not None else None


async def find_by_id(connection: asyncpg.Connection, document_id: UUID) -> DocumentSummary | None:
    """Fetch a document by its id.

    Args:
        connection: An open database connection.
        document_id: The document's id.

    Returns:
        The document, or `None` if no such document exists.
    """
    row = await connection.fetchrow("SELECT * FROM documents WHERE id = $1", document_id)
    return _row_to_summary(row) if row is not None else None


async def list_documents(
    connection: asyncpg.Connection,
    *,
    status: DocumentStatus | None,
    doc_type: DocumentType | None,
    limit: int,
    offset: int,
) -> list[DocumentSummary]:
    """List documents, optionally filtered by status and/or type.

    Args:
        connection: An open database connection.
        status: If given, only documents with this status are returned.
        doc_type: If given, only documents of this type are returned.
        limit: Maximum number of rows to return.
        offset: Number of rows to skip, for pagination.

    Returns:
        Matching documents, most recently ingested first.
    """
    rows = await connection.fetch(
        """
        SELECT * FROM documents
        WHERE ($1::text IS NULL OR status = $1)
          AND ($2::text IS NULL OR doc_type = $2)
        ORDER BY ingested_at DESC
        LIMIT $3 OFFSET $4
        """,
        status.value if status else None,
        doc_type.value if doc_type else None,
        limit,
        offset,
    )
    return [_row_to_summary(row) for row in rows]


async def insert_document(
    connection: asyncpg.Connection,
    *,
    source_id: str,
    title: str,
    doc_type: DocumentType,
    jurisdiction: str,
    issuing_body: str,
    reference_number: str | None,
    language: str,
    issued_date: date | None,
    file_sha256: str,
    storage_path: str,
) -> UUID:
    """Insert a newly fetched/uploaded document, in its initial pipeline state.

    Args:
        connection: An open database connection.
        source_id: The slug matching an entry in `sources.yaml`.
        title: The document's title.
        doc_type: The kind of regulatory instrument.
        jurisdiction: The issuing jurisdiction.
        issuing_body: The issuing institution.
        reference_number: The document's own reference number, if known at upload time.
        language: The document's language code (e.g. `"en"`, `"sw"`).
        issued_date: The document's issue date, if known at upload time.
        file_sha256: The SHA-256 hex digest of the original file.
        storage_path: Where the original file was stored.

    Returns:
        The new document's id.
    """
    document_id = await connection.fetchval(
        """
        INSERT INTO documents (
            source_id, title, doc_type, jurisdiction, issuing_body,
            reference_number, language, issued_date, status,
            file_sha256, storage_path, pipeline_status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'unknown', $9, $10, 'fetched')
        RETURNING id
        """,
        source_id,
        title,
        doc_type.value,
        jurisdiction,
        issuing_body,
        reference_number,
        language,
        issued_date,
        file_sha256,
        storage_path,
    )
    return cast(UUID, document_id)
