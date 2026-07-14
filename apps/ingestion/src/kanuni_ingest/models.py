"""Pydantic domain models shared across the ingestion pipeline's stages."""

from datetime import date
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    """The kind of regulatory instrument a document is, per PROJECT_SPEC.md §6."""

    CIRCULAR = "circular"
    ACT = "act"
    REGULATION = "regulation"
    NOTICE = "notice"
    GUIDELINE = "guideline"


class DocumentStatus(StrEnum):
    """Whether a document is currently authoritative, per PROJECT_SPEC.md §6."""

    IN_FORCE = "in_force"
    SUPERSEDED = "superseded"
    REPEALED = "repealed"
    UNKNOWN = "unknown"


class PipelineStage(StrEnum):
    """The ingestion pipeline stage a document has most recently completed."""

    FETCHED = "fetched"
    EXTRACTED = "extracted"
    CHUNKED = "chunked"
    EMBEDDED = "embedded"
    INDEXED = "indexed"
    FAILED = "failed"


class ExtractionMethod(StrEnum):
    """How a page's text was obtained."""

    NATIVE = "native"
    OCR = "ocr"


class ExtractedPage(BaseModel):
    """The text extracted from a single PDF page, and how it was obtained."""

    page_number: int = Field(ge=1)
    text: str
    extraction_method: ExtractionMethod
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=100.0)


class ExtractedDocument(BaseModel):
    """The per-page extraction result for one document, prior to chunking."""

    pages: list[ExtractedPage]


class DocumentChunk(BaseModel):
    """A single retrieval chunk produced by the chunking stage."""

    chunk_index: int = Field(ge=0)
    content: str
    section_ref: str | None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    token_count: int = Field(ge=0)
    embedding: list[float] | None = None


class RelatedDocumentReference(BaseModel):
    """A citation to another document found in the extracted text, with its relation."""

    reference_number: str
    relation: Literal["supersedes", "amends", "refers_to"]


class ExtractedDocumentMetadata(BaseModel):
    """Strictly validated metadata extracted from a document's text (regex + LLM).

    Every field is optional: PROJECT_SPEC.md §7 stage 4 requires flagging a
    document for manual review rather than guessing when a field can't be
    determined, so `None` is a legitimate, expected result — never filled
    with a placeholder.
    """

    reference_number: str | None = None
    issuing_body: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    related_documents: list[RelatedDocumentReference] = Field(default_factory=list)


class DocumentRecord(BaseModel):
    """A row from the `documents` table."""

    id: UUID
    source_id: str
    title: str
    doc_type: DocumentType
    jurisdiction: str
    issuing_body: str
    reference_number: str | None
    language: str
    issued_date: date | None
    effective_date: date | None
    status: DocumentStatus
    file_sha256: str
    storage_path: str
    pipeline_status: PipelineStage


class IngestionJobRecord(BaseModel):
    """A row from the `ingestion_jobs` table."""

    id: UUID
    document_id: UUID
    stage: PipelineStage
    attempt_count: int
    error_details: dict[str, object] | None = None
