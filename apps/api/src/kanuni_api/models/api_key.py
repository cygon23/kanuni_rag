"""API key domain model, for authentication and scope checks."""

from uuid import UUID

from pydantic import BaseModel


class ApiKeyRecord(BaseModel):
    """An `api_keys` row, as resolved during authentication."""

    id: UUID
    name: str
    scopes: list[str]
    rate_limit_per_min: int
