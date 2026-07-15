"""Query domain models: request/response shapes for POST /v1/query (§8.4)."""

from uuid import UUID

from pydantic import BaseModel, Field

from kanuni_api.models.document import DocumentStatus


class QueryRequest(BaseModel):
    """The request body for `POST /v1/query`."""

    question: str = Field(min_length=1, max_length=2000)
    include_historical: bool = False
    top_k: int | None = None


class ResolvedCitation(BaseModel):
    """One citation resolved to full document/chunk metadata (§8.3).

    Includes the chunk's own text (`content`) so the frontend's citation
    side panel (§9: "showing the exact chunk text, document metadata, page
    numbers") can render it without a second round trip.
    """

    chunk_id: UUID
    document_id: UUID
    document_title: str
    reference_number: str | None
    section_ref: str | None
    page_start: int
    page_end: int
    status: DocumentStatus
    content: str
    # The document's public Supabase Storage URL (§9: "a link to the
    # source PDF page") — None only if the document has no stored file,
    # which shouldn't happen for a document that made it to indexed/cited.
    source_url: str | None = None


class DocumentPointer(BaseModel):
    """A nearest-document pointer shown alongside a refusal (§8.2)."""

    document_id: UUID
    title: str
    reference_number: str | None


class QueryResultMetadata(BaseModel):
    """The final SSE event's payload for a query, answered or refused."""

    confidence: str
    answered: bool
    citations: list[ResolvedCitation] = Field(default_factory=list)
    pointers: list[DocumentPointer] = Field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    citation_density: float | None = None
    latency_ms: int
