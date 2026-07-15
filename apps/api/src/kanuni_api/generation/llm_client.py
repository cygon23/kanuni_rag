"""LLM provider abstraction: Groq implementation + fallback slot (PROJECT_SPEC.md §2, §8.3).

Never hardcode a provider in business logic — `services/query_service.py`
depends only on the `LLMProvider` protocol. §13: no test may call a real
LLM; every test uses a fake implementing this protocol.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

from kanuni_api.exceptions import GenerationError, ProviderRateLimitError, ProviderTimeoutError

logger = structlog.get_logger()

_REQUEST_TIMEOUT_SECONDS = 60.0


@dataclass
class GenerationChunk:
    """One piece of a streamed generation: either a text delta or final usage totals."""

    text_delta: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMProvider(Protocol):
    """Streams a chat completion for a system/user prompt pair."""

    def generate(self, *, system_prompt: str, user_prompt: str) -> AsyncIterator[GenerationChunk]:
        """Stream a completion.

        Args:
            system_prompt: The system instructions (from a versioned prompt file).
            user_prompt: The user-facing content (question + tagged chunks).

        Yields:
            `GenerationChunk`s: text deltas as they arrive, and a final
            chunk carrying token usage once the provider reports it.
        """
        ...


class GroqLLMProvider:
    """Streams completions from Groq's OpenAI-compatible chat completions endpoint."""

    def __init__(self, *, api_key: str, model: str) -> None:
        """Configure the provider.

        Args:
            api_key: Groq API key.
            model: Groq model identifier, e.g. `"llama-3.3-70b-versatile"`.
        """
        self._api_key = api_key
        self._model = model

    async def generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[GenerationChunk]:
        """Stream a completion from Groq.

        Args:
            system_prompt: The system instructions.
            user_prompt: The user-facing content.

        Yields:
            Text-delta chunks, followed by a final usage chunk.

        Raises:
            ProviderTimeoutError: If the request times out.
            ProviderRateLimitError: If Groq rate-limits the request.
            GenerationError: For any other non-2xx response.
        """
        payload = {
            "model": self._model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            async with (
                httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client,
                client.stream(
                    "POST",
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                ) as response,
            ):
                if response.status_code == 429:
                    raise ProviderRateLimitError("Groq generation was rate-limited")
                if response.status_code >= 400:
                    body = await response.aread()
                    logger.error("groq_generation_failed", status_code=response.status_code)
                    raise GenerationError() from RuntimeError(
                        f"Groq returned HTTP {response.status_code}: {body[:200]!r}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload_text = line.removeprefix("data: ").strip()
                    if payload_text == "[DONE]":
                        break
                    event = json.loads(payload_text)

                    usage = event.get("usage")
                    if usage:
                        yield GenerationChunk(
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                        )
                        continue

                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield GenerationChunk(text_delta=delta)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Groq generation timed out") from exc


class FallbackLLMProvider:
    """Wraps a primary provider with an optional fallback (§2's "fallback slot").

    If no fallback is configured, behaves exactly like the primary
    provider — this exists so `services/query_service.py` never has to
    know whether a fallback is configured.

    Known limitation: if the primary provider fails *after* already
    streaming some text (rather than on the initial connection), falling
    back would restart from an empty response, mixing partial primary
    output with a full fallback response. Acceptable for v1 since Groq
    reports rate-limit/timeout failures before the first token in the
    overwhelming majority of cases; revisit if that stops holding.
    """

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None) -> None:
        """Configure the primary and (optional) fallback provider.

        Args:
            primary: The provider to try first.
            fallback: A provider to try if the primary times out or is
                rate-limited. `None` means no fallback is configured.
        """
        self._primary = primary
        self._fallback = fallback

    async def generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[GenerationChunk]:
        """Stream from the primary provider, falling back on timeout/rate-limit.

        Args:
            system_prompt: The system instructions.
            user_prompt: The user-facing content.

        Yields:
            Text-delta and usage chunks from whichever provider served the request.

        Raises:
            ProviderTimeoutError: If the primary fails and no fallback is configured.
            ProviderRateLimitError: If the primary fails and no fallback is configured.
        """
        try:
            async for chunk in self._primary.generate(
                system_prompt=system_prompt, user_prompt=user_prompt
            ):
                yield chunk
            return
        except (ProviderTimeoutError, ProviderRateLimitError):
            if self._fallback is None:
                raise
            logger.warning("llm_provider_falling_back")

        async for chunk in self._fallback.generate(
            system_prompt=system_prompt, user_prompt=user_prompt
        ):
            yield chunk
