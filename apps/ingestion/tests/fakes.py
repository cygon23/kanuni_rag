"""Test doubles for the ingestion pipeline's provider interfaces (§13: never use the real ones)."""

from datetime import date
from uuid import UUID, uuid4

from PIL import Image

from kanuni_ingest.exceptions import MetadataValidationError
from kanuni_ingest.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    ExtractedDocumentMetadata,
    PipelineStage,
)


class FakeOCREngine:
    """Returns canned OCR output instead of running Tesseract."""

    def __init__(self, text: str = "fake ocr text", confidence: float = 90.0) -> None:
        self.text = text
        self.confidence = confidence
        self.calls: list[str] = []

    async def recognize(self, image: Image.Image, languages: str) -> tuple[str, float]:
        self.calls.append(languages)
        return self.text, self.confidence


class FakeEmbeddingProvider:
    """Returns deterministic fixed-size vectors instead of running bge-m3."""

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions
        self.embedded_texts: list[str] = []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        return [[float(len(text) % 7)] * self.dimensions for text in texts]


class FakeMetadataExtractionProvider:
    """Returns a canned (or per-call-configured) metadata extraction result."""

    def __init__(self, result: ExtractedDocumentMetadata | None = None) -> None:
        self._result = result or ExtractedDocumentMetadata()
        self.calls: list[str] = []
        self.raise_validation_error = False

    async def extract(self, text: str) -> ExtractedDocumentMetadata:
        self.calls.append(text)
        if self.raise_validation_error:
            raise MetadataValidationError("fake validation failure")
        return self._result


class FakeDocumentStorage:
    """Stores document bytes in memory instead of on disk."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    async def write(self, storage_path: str, content: bytes) -> None:
        self._files[storage_path] = content

    async def read(self, storage_path: str) -> bytes:
        return self._files[storage_path]

    def seed(self, storage_path: str, content: bytes) -> None:
        """Preload content, as if a prior fetch stage had already stored it."""
        self._files[storage_path] = content


def make_document_record(
    *,
    document_id: UUID | None = None,
    reference_number: str | None = None,
    status: DocumentStatus = DocumentStatus.UNKNOWN,
    pipeline_status: PipelineStage = PipelineStage.FETCHED,
    storage_path: str = "fake.pdf",
    file_sha256: str = "0" * 64,
) -> DocumentRecord:
    """Build a `DocumentRecord` for tests without touching a database."""
    return DocumentRecord(
        id=document_id or uuid4(),
        source_id="bot",
        title="Fake Document",
        doc_type=DocumentType.REGULATION,
        jurisdiction="Tanzania",
        issuing_body="Bank of Tanzania",
        reference_number=reference_number,
        language="en",
        issued_date=date(2024, 1, 1),
        effective_date=None,
        status=status,
        file_sha256=file_sha256,
        storage_path=storage_path,
        pipeline_status=pipeline_status,
    )


class FakeDocumentRegistry:
    """An in-memory stand-in for `DocumentRegistry`, keyed by document id and reference number."""

    def __init__(self, documents: list[DocumentRecord] | None = None) -> None:
        self._by_id: dict[UUID, DocumentRecord] = {doc.id: doc for doc in (documents or [])}
        self.status_updates: list[tuple[UUID, DocumentStatus]] = []
        self.pipeline_status_updates: list[tuple[UUID, PipelineStage]] = []
        self.relations_created: list[tuple[UUID, UUID, str]] = []
        self.filled_metadata: list[UUID] = []

    async def find_pending_documents(self) -> list[DocumentRecord]:
        pending_stages = {
            PipelineStage.FETCHED,
            PipelineStage.EXTRACTED,
            PipelineStage.CHUNKED,
            PipelineStage.EMBEDDED,
        }
        return [doc for doc in self._by_id.values() if doc.pipeline_status in pending_stages]

    async def find_by_id(self, document_id: UUID) -> DocumentRecord | None:
        return self._by_id.get(document_id)

    async def find_by_reference_number(self, reference_number: str) -> DocumentRecord | None:
        for document in self._by_id.values():
            if document.reference_number == reference_number:
                return document
        return None

    async def update_pipeline_status(self, document_id: UUID, stage: PipelineStage) -> None:
        self.pipeline_status_updates.append((document_id, stage))
        document = self._by_id[document_id]
        self._by_id[document_id] = document.model_copy(update={"pipeline_status": stage})

    async def update_status(self, document_id: UUID, status: DocumentStatus) -> None:
        self.status_updates.append((document_id, status))
        document = self._by_id[document_id]
        self._by_id[document_id] = document.model_copy(update={"status": status})

    async def fill_missing_metadata(
        self,
        document_id: UUID,
        *,
        reference_number: str | None,
        issuing_body: str | None,
        issued_date: date | None,
        effective_date: date | None,
    ) -> None:
        self.filled_metadata.append(document_id)
        document = self._by_id[document_id]
        self._by_id[document_id] = document.model_copy(
            update={
                "reference_number": document.reference_number or reference_number,
                "issuing_body": document.issuing_body or issuing_body,
            }
        )

    async def create_relation(
        self, *, from_document_id: UUID, to_document_id: UUID, relation: str
    ) -> None:
        self.relations_created.append((from_document_id, to_document_id, relation))
