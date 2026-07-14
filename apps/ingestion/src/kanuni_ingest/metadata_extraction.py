"""LLM-backed metadata extraction: validates and supplements regex-extracted candidates.

PROJECT_SPEC.md §7 stage 4 calls for "a single cheap LLM extraction call
with a strict Pydantic-validated JSON schema; on validation failure → flag
for manual review, do not guess." §13 forbids any test from calling a real
LLM — every test uses a fake implementing :class:`MetadataExtractionProvider`.
"""

from typing import Protocol

import httpx
import structlog
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from kanuni_ingest.exceptions import (
    MetadataValidationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from kanuni_ingest.models import ExtractedDocumentMetadata

logger = structlog.get_logger()

_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_INPUT_CHARS = 8000

_SYSTEM_PROMPT = (
    "You extract structured metadata from Tanzanian financial regulatory documents. "
    "Respond with a single JSON object matching this schema exactly: "
    '{"reference_number": string|null, "issuing_body": string|null, '
    '"issued_date": "YYYY-MM-DD"|null, "effective_date": "YYYY-MM-DD"|null, '
    '"related_documents": [{"reference_number": string, "relation": '
    '"supersedes"|"amends"|"refers_to"}]}. '
    "If a field cannot be determined from the text, use null. Never guess."
)


class MetadataExtractionProvider(Protocol):
    """Extracts and validates structured document metadata from raw text."""

    async def extract(self, text: str) -> ExtractedDocumentMetadata:
        """Extract metadata from a document's text.

        Args:
            text: The document's extracted text (native or OCR).

        Returns:
            Strictly validated metadata.

        Raises:
            MetadataValidationError: If the provider's output fails schema validation.
        """
        ...


class GroqMetadataExtractionProvider:
    """Extracts metadata via a single Groq chat-completion call in JSON mode."""

    def __init__(self, *, api_key: str, model: str) -> None:
        """Configure the provider.

        Args:
            api_key: Groq API key.
            model: Groq model identifier, e.g. `"llama-3.1-8b-instant"` — a
                deliberately cheap model, per §7 stage 4.
        """
        self._api_key = api_key
        self._model = model

    @retry(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    async def extract(self, text: str) -> ExtractedDocumentMetadata:
        """Call Groq to extract and validate document metadata.

        Args:
            text: The document's extracted text.

        Returns:
            Strictly validated metadata.

        Raises:
            ProviderTimeoutError: If the request times out after all retries.
            ProviderRateLimitError: If Groq rate-limits the request.
            MetadataValidationError: If Groq's response fails schema validation.
        """
        truncated_text = text[:_MAX_INPUT_CHARS]
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": truncated_text},
                        ],
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Groq metadata extraction timed out") from exc

        if response.status_code == 429:
            raise ProviderRateLimitError("Groq metadata extraction was rate-limited")
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        try:
            return ExtractedDocumentMetadata.model_validate_json(content)
        except ValidationError as exc:
            raise MetadataValidationError(
                "Groq's metadata extraction response failed schema validation"
            ) from exc
