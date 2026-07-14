"""Admin document upload: validates, dedupes by SHA-256, stores, and registers a document.

Business logic only — no SQL here (§3 rule); persistence goes through
`db/documents_repository`.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import asyncpg

from kanuni_api.db import documents_repository
from kanuni_api.exceptions import ValidationFailedError
from kanuni_api.models.document import DocumentType
from kanuni_api.storage import DocumentStorage

_PDF_MAGIC_BYTES = b"%PDF-"


@dataclass
class UploadOutcome:
    """The result of processing an admin document upload."""

    document_id: UUID
    created: bool
    """`True` if a new document was registered; `False` if it was a duplicate."""


def _validate_pdf(content: bytes, max_size_bytes: int) -> None:
    """Validate uploaded content is a plausible, size-bounded PDF.

    Args:
        content: The raw uploaded bytes.
        max_size_bytes: The maximum allowed file size.

    Raises:
        ValidationFailedError: If the content fails any check.
    """
    if not content:
        raise ValidationFailedError("Uploaded file is empty.")
    if len(content) > max_size_bytes:
        raise ValidationFailedError(
            f"Uploaded file exceeds the maximum allowed size of {max_size_bytes} bytes."
        )
    if not content.startswith(_PDF_MAGIC_BYTES):
        raise ValidationFailedError("Uploaded file is not a valid PDF.")


async def ingest_upload(
    connection: asyncpg.Connection,
    storage: DocumentStorage,
    *,
    content: bytes,
    max_size_bytes: int,
    source_id: str,
    title: str,
    doc_type: DocumentType,
    jurisdiction: str,
    issuing_body: str,
    language: str,
    reference_number: str | None,
    issued_date: date | None,
) -> UploadOutcome:
    """Validate, dedupe, store, and register one uploaded document.

    Args:
        connection: An open database connection.
        storage: Storage backend the original file is written to.
        content: The raw uploaded file bytes.
        max_size_bytes: The maximum allowed file size.
        source_id: The slug matching an entry in `sources.yaml`.
        title: The document's title.
        doc_type: The kind of regulatory instrument.
        jurisdiction: The issuing jurisdiction.
        issuing_body: The issuing institution.
        language: The document's language code (e.g. `"en"`, `"sw"`).
        reference_number: The document's own reference number, if already known.
        issued_date: The document's issue date, if already known.

    Returns:
        The outcome: the (new or existing) document's id, and whether it
        was newly created.

    Raises:
        ValidationFailedError: If the uploaded content fails validation.
    """
    _validate_pdf(content, max_size_bytes)

    file_sha256 = hashlib.sha256(content).hexdigest()
    existing = await documents_repository.find_by_sha256(connection, file_sha256)
    if existing is not None:
        return UploadOutcome(document_id=existing.id, created=False)

    storage_path = f"{file_sha256}.pdf"
    await storage.write(storage_path, content)

    document_id = await documents_repository.insert_document(
        connection,
        source_id=source_id,
        title=title,
        doc_type=doc_type,
        jurisdiction=jurisdiction,
        issuing_body=issuing_body,
        reference_number=reference_number,
        language=language,
        issued_date=issued_date,
        file_sha256=file_sha256,
        storage_path=storage_path,
    )
    return UploadOutcome(document_id=document_id, created=True)
