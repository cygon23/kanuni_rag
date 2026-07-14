"""Admin routes: document upload and ingestion-job management (scope: ingest:admin)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi.responses import JSONResponse

from kanuni_api.config import Settings, get_settings
from kanuni_api.db import ingestion_jobs_repository
from kanuni_api.dependencies import DbConnection
from kanuni_api.middleware.auth import require_scope
from kanuni_api.models.api_key import ApiKeyRecord
from kanuni_api.models.document import DocumentType
from kanuni_api.models.ingestion_job import IngestionJobSummary
from kanuni_api.services import document_ingestion_service
from kanuni_api.sources import resolve_source
from kanuni_api.storage import LocalFilesystemStorage

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_require_admin_scope = require_scope("ingest:admin")


@router.post("/documents")
async def upload_document(
    connection: DbConnection,
    _api_key: Annotated[ApiKeyRecord, Depends(_require_admin_scope)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile,
    source_id: Annotated[str, Form()],
    title: Annotated[str, Form()],
    doc_type: Annotated[DocumentType, Form()],
    language: Annotated[str, Form()] = "en",
    reference_number: Annotated[str | None, Form()] = None,
    issued_date: Annotated[date | None, Form()] = None,
) -> JSONResponse:
    """Upload a document for ingestion.

    Validates and dedupes by SHA-256; a re-upload of an already-ingested
    file is reported as a no-op rather than a duplicate document (§7 stage 1).

    Args:
        connection: Database connection (injected).
        _api_key: The authenticated caller's key (requires `ingest:admin` scope).
        settings: Application settings (for storage path and max upload size).
        file: The uploaded PDF.
        source_id: The slug matching an entry in `sources.yaml`.
        title: The document's title.
        doc_type: The kind of regulatory instrument.
        language: The document's language code (e.g. `"en"`, `"sw"`).
        reference_number: The document's own reference number, if already known.
        issued_date: The document's issue date, if already known.

    Returns:
        201 with `{"status": "created", "document_id": ...}` for a new
        document, or 200 with `{"status": "skipped", "document_id": ...}`
        for a re-upload of an already-ingested file.
    """
    source = resolve_source(source_id)
    content = await file.read()
    storage = LocalFilesystemStorage(settings.storage_local_path)

    outcome = await document_ingestion_service.ingest_upload(
        connection,
        storage,
        content=content,
        max_size_bytes=settings.max_upload_size_bytes,
        source_id=source_id,
        title=title,
        doc_type=doc_type,
        jurisdiction=source.jurisdiction,
        issuing_body=source.issuing_body,
        language=language,
        reference_number=reference_number,
        issued_date=issued_date,
    )

    if outcome.created:
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"status": "created", "document_id": str(outcome.document_id)},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "skipped", "document_id": str(outcome.document_id)},
    )


@router.get("/ingestion-jobs", response_model=list[IngestionJobSummary])
async def list_failed_ingestion_jobs(
    connection: DbConnection,
    _api_key: Annotated[ApiKeyRecord, Depends(_require_admin_scope)],
) -> list[IngestionJobSummary]:
    """List documents whose ingestion pipeline is currently failed.

    Args:
        connection: Database connection (injected).
        _api_key: The authenticated caller's key (requires `ingest:admin` scope).

    Returns:
        One entry per failed document, most recent failure first.
    """
    return await ingestion_jobs_repository.list_failed(connection)


@router.post("/ingestion-jobs/{document_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_ingestion_job(
    document_id: UUID,
    connection: DbConnection,
    _api_key: Annotated[ApiKeyRecord, Depends(_require_admin_scope)],
) -> dict[str, str]:
    """Reset a failed document so the worker reprocesses it from the start.

    Args:
        document_id: The document to retry.
        connection: Database connection (injected).
        _api_key: The authenticated caller's key (requires `ingest:admin` scope).

    Returns:
        A status acknowledgement.
    """
    await ingestion_jobs_repository.reset_for_retry(connection, document_id)
    return {"status": "queued"}
