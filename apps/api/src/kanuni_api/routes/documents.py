"""Document registry browsing: GET /v1/documents, GET /v1/documents/{id}."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from kanuni_api.db import documents_repository
from kanuni_api.dependencies import DbConnection
from kanuni_api.exceptions import DocumentNotFoundError
from kanuni_api.middleware.auth import require_scope
from kanuni_api.models.api_key import ApiKeyRecord
from kanuni_api.models.document import DocumentStatus, DocumentSummary, DocumentType

router = APIRouter(tags=["documents"])

_require_query_scope = require_scope("query")


@router.get("/v1/documents", response_model=list[DocumentSummary])
async def list_documents(
    connection: DbConnection,
    _api_key: Annotated[ApiKeyRecord, Depends(_require_query_scope)],
    status: DocumentStatus | None = None,
    doc_type: DocumentType | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentSummary]:
    """List documents in the registry, optionally filtered.

    Args:
        connection: Database connection (injected).
        _api_key: The authenticated caller's key (requires `query` scope).
        status: If given, only documents with this status are returned.
        doc_type: If given, only documents of this type are returned.
        limit: Maximum number of results.
        offset: Number of results to skip, for pagination.

    Returns:
        Matching documents, most recently ingested first.
    """
    return await documents_repository.list_documents(
        connection, status=status, doc_type=doc_type, limit=limit, offset=offset
    )


@router.get("/v1/documents/{document_id}", response_model=DocumentSummary)
async def get_document(
    document_id: UUID,
    connection: DbConnection,
    _api_key: Annotated[ApiKeyRecord, Depends(_require_query_scope)],
) -> DocumentSummary:
    """Fetch a single document by id.

    Args:
        document_id: The document's id.
        connection: Database connection (injected).
        _api_key: The authenticated caller's key (requires `query` scope).

    Returns:
        The document.

    Raises:
        DocumentNotFoundError: If no document with that id exists.
    """
    document = await documents_repository.find_by_id(connection, document_id)
    if document is None:
        raise DocumentNotFoundError()
    return document
