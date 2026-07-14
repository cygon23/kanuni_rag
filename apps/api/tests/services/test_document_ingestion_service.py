"""Tests for the admin document upload service: validation and SHA-256 dedup."""

from datetime import date
from uuid import uuid4

import pytest

from kanuni_api.db import documents_repository
from kanuni_api.exceptions import ValidationFailedError
from kanuni_api.models.document import DocumentSummary, DocumentType
from kanuni_api.services import document_ingestion_service

_VALID_PDF = b"%PDF-1.4\nreal-looking pdf content\n"


class _FakeStorage:
    def __init__(self) -> None:
        self.writes: list[tuple[str, bytes]] = []

    async def write(self, storage_path: str, content: bytes) -> None:
        self.writes.append((storage_path, content))


async def test_ingest_upload_rejects_empty_file() -> None:
    with pytest.raises(ValidationFailedError):
        await document_ingestion_service.ingest_upload(
            connection=object(),
            storage=_FakeStorage(),
            content=b"",
            max_size_bytes=1000,
            source_id="bot",
            title="T",
            doc_type=DocumentType.REGULATION,
            jurisdiction="Tanzania",
            issuing_body="Bank of Tanzania",
            language="en",
            reference_number=None,
            issued_date=None,
        )


async def test_ingest_upload_rejects_oversized_file() -> None:
    with pytest.raises(ValidationFailedError):
        await document_ingestion_service.ingest_upload(
            connection=object(),
            storage=_FakeStorage(),
            content=_VALID_PDF,
            max_size_bytes=5,
            source_id="bot",
            title="T",
            doc_type=DocumentType.REGULATION,
            jurisdiction="Tanzania",
            issuing_body="Bank of Tanzania",
            language="en",
            reference_number=None,
            issued_date=None,
        )


async def test_ingest_upload_rejects_non_pdf_content() -> None:
    with pytest.raises(ValidationFailedError):
        await document_ingestion_service.ingest_upload(
            connection=object(),
            storage=_FakeStorage(),
            content=b"this is not a pdf",
            max_size_bytes=1000,
            source_id="bot",
            title="T",
            doc_type=DocumentType.REGULATION,
            jurisdiction="Tanzania",
            issuing_body="Bank of Tanzania",
            language="en",
            reference_number=None,
            issued_date=None,
        )


async def test_ingest_upload_stores_and_registers_a_new_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_id = uuid4()

    async def _fake_find_by_sha256(connection: object, file_sha256: str) -> DocumentSummary | None:
        return None

    async def _fake_insert_document(connection: object, **kwargs: object) -> object:
        return new_id

    monkeypatch.setattr(documents_repository, "find_by_sha256", _fake_find_by_sha256)
    monkeypatch.setattr(documents_repository, "insert_document", _fake_insert_document)
    storage = _FakeStorage()

    outcome = await document_ingestion_service.ingest_upload(
        connection=object(),
        storage=storage,
        content=_VALID_PDF,
        max_size_bytes=1000,
        source_id="bot",
        title="T",
        doc_type=DocumentType.REGULATION,
        jurisdiction="Tanzania",
        issuing_body="Bank of Tanzania",
        language="en",
        reference_number=None,
        issued_date=date(2024, 1, 1),
    )

    assert outcome.created is True
    assert outcome.document_id == new_id
    assert len(storage.writes) == 1


async def test_ingest_upload_reports_a_duplicate_without_storing_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_id = uuid4()
    existing = DocumentSummary.model_validate(
        {
            "id": existing_id,
            "source_id": "bot",
            "title": "Existing",
            "doc_type": DocumentType.REGULATION,
            "jurisdiction": "Tanzania",
            "issuing_body": "Bank of Tanzania",
            "reference_number": None,
            "language": "en",
            "issued_date": None,
            "effective_date": None,
            "status": "in_force",
            "pipeline_status": "indexed",
        }
    )

    async def _fake_find_by_sha256(connection: object, file_sha256: str) -> DocumentSummary | None:
        return existing

    monkeypatch.setattr(documents_repository, "find_by_sha256", _fake_find_by_sha256)
    storage = _FakeStorage()

    outcome = await document_ingestion_service.ingest_upload(
        connection=object(),
        storage=storage,
        content=_VALID_PDF,
        max_size_bytes=1000,
        source_id="bot",
        title="T",
        doc_type=DocumentType.REGULATION,
        jurisdiction="Tanzania",
        issuing_body="Bank of Tanzania",
        language="en",
        reference_number=None,
        issued_date=None,
    )

    assert outcome.created is False
    assert outcome.document_id == existing_id
    assert storage.writes == []
