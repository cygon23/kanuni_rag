"""Ingestion job domain model, for the admin failed-jobs listing endpoint."""

from uuid import UUID

from pydantic import BaseModel

from kanuni_api.models.document import PipelineStage


class IngestionJobSummary(BaseModel):
    """An `ingestion_jobs` row, as exposed by the admin failed-jobs endpoint."""

    id: UUID
    document_id: UUID
    stage: PipelineStage
    attempt_count: int
    error_details: dict[str, object] | None
