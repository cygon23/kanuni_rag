"""Domain exception hierarchy mapped to RFC 7807 problem-details responses by the error handler."""


class KanuniError(Exception):
    """Base class for all domain errors raised by Kanuni services.

    Attributes:
        error_code: Stable, machine-readable identifier for this error type,
            exposed to clients so they can branch on failure kind without
            parsing human-readable text.
        status_code: HTTP status code the global exception handler maps this
            error to.
        detail: Generic, user-safe description of the failure. Must never
            contain stack traces, SQL, or upstream provider payloads.
    """

    error_code: str = "kanuni_error"
    status_code: int = 500
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None) -> None:
        """Initialize the error, optionally overriding the default detail message.

        Args:
            detail: A user-safe message to use instead of the class default.
        """
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class RetrievalError(KanuniError):
    """Raised when dense, sparse, or fused retrieval fails."""

    error_code = "retrieval_error"
    status_code = 502
    detail = "Retrieval from the document index failed."


class GenerationError(KanuniError):
    """Raised when LLM answer generation fails."""

    error_code = "generation_error"
    status_code = 502
    detail = "Answer generation failed."


class IngestionError(KanuniError):
    """Raised when a document ingestion pipeline stage fails."""

    error_code = "ingestion_error"
    status_code = 500
    detail = "Document ingestion failed."


class DocumentNotFoundError(KanuniError):
    """Raised when a requested document does not exist in the registry."""

    error_code = "document_not_found"
    status_code = 404
    detail = "The requested document was not found."


class LowConfidenceError(KanuniError):
    """Raised when retrieval confidence is too low to safely generate an answer."""

    error_code = "low_confidence"
    status_code = 422
    detail = "Retrieval confidence was too low to produce a grounded answer."


class ProviderRateLimitError(KanuniError):
    """Raised when an upstream provider (LLM, embedding, OCR) rate-limits a request."""

    error_code = "provider_rate_limit"
    status_code = 429
    detail = "An upstream provider is rate-limited; please retry shortly."


class ProviderTimeoutError(KanuniError):
    """Raised when an upstream provider (LLM, embedding, OCR) times out."""

    error_code = "provider_timeout"
    status_code = 504
    detail = "An upstream provider timed out."


class ValidationFailedError(KanuniError):
    """Raised when domain-level validation fails outside of Pydantic request parsing."""

    error_code = "validation_failed"
    status_code = 422
    detail = "The request failed validation."


class AuthenticationError(KanuniError):
    """Raised when a request has no API key, or the key is unknown or revoked.

    Not in PROJECT_SPEC.md §4.2's enumerated hierarchy — added because §4.3
    mandates API-key auth and the hierarchy needs a 401 case to map through
    the same RFC 7807 handler. See the Phase 1 handoff summary.
    """

    error_code = "authentication_failed"
    status_code = 401
    detail = "A valid API key is required."


class AuthorizationError(KanuniError):
    """Raised when a valid API key lacks the scope a route requires.

    See :class:`AuthenticationError` for why this extends §4.2's hierarchy.
    """

    error_code = "authorization_failed"
    status_code = 403
    detail = "This API key does not have the required scope."


class RateLimitExceededError(KanuniError):
    """Raised when a caller exceeds their API key's `rate_limit_per_min` (§4.3, §12).

    Not in PROJECT_SPEC.md §4.2's enumerated hierarchy either — same
    situation as :class:`AuthenticationError`: the auth model (§4.3)
    requires per-key rate limiting, so the error hierarchy needs a 429
    case for it.
    """

    error_code = "rate_limit_exceeded"
    status_code = 429
    detail = "Rate limit exceeded for this API key. Please slow down."
