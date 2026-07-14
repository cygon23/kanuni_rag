"""Exception hierarchy for the ingestion service, mirroring kanuni_api's domain errors.

apps/ingestion has no code dependency on apps/api (PROJECT_SPEC.md §5: the
two services share the database, not code — see ADR 0005), so this is a
small, independent hierarchy rather than an import of
``kanuni_api.exceptions``.
"""


class IngestionError(Exception):
    """Base class for errors raised while running an ingestion pipeline stage."""


class StageFailedError(IngestionError):
    """Raised when a pipeline stage fails and the document must not be partially indexed."""


class MetadataValidationError(IngestionError):
    """Raised when extracted document metadata fails strict Pydantic validation.

    Per PROJECT_SPEC.md §7 stage 4, a validation failure must flag the
    document for manual review rather than guessing at the missing fields.
    """


class ProviderTimeoutError(IngestionError):
    """Raised when an external provider (OCR, embedding, metadata LLM) times out."""


class ProviderRateLimitError(IngestionError):
    """Raised when an external provider (OCR, embedding, metadata LLM) is rate-limited."""
