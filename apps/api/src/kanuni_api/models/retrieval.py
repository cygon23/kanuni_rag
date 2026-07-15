"""Retrieval domain models: scored chunk candidates through the hybrid pipeline."""

from uuid import UUID

from pydantic import BaseModel


class ScoredChunk(BaseModel):
    """A chunk candidate carrying whichever retrieval-stage scores have been computed so far."""

    chunk_id: UUID
    document_id: UUID
    content: str
    section_ref: str | None
    page_start: int
    page_end: int
    dense_score: float | None = None
    sparse_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None
