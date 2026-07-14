"""Document domain models: mirrors kanuni_ingest's copies (ADR 0005 — no shared code)."""

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


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


class DocumentSummary(BaseModel):
    """A `documents` row, as exposed by the registry-browsing endpoints."""

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
    pipeline_status: PipelineStage
