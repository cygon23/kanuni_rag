"""Embedding provider abstraction: never call a real embedding model in tests (§13)."""

import asyncio
from typing import Protocol

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

logger = structlog.get_logger()

_MAX_ATTEMPTS = 3


class EmbeddingProvider(Protocol):
    """Embeds text into dense vectors for pgvector storage and dense retrieval."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: The texts to embed, in order.

        Returns:
            One embedding vector per input text, in the same order.
        """
        ...


class Bgem3EmbeddingProvider:
    """Embeds text with `BAAI/bge-m3` via `sentence-transformers` (PROJECT_SPEC.md §2).

    The model is loaded lazily on first use so importing this module never
    requires the (large) model weights to be present — only actually
    embedding does.
    """

    def __init__(self, model_name: str) -> None:
        """Configure the provider without loading the model yet.

        Args:
            model_name: The `sentence-transformers` model identifier, e.g.
                `"BAAI/bge-m3"`.
        """
        self._model_name = model_name
        self._model: object | None = None

    def _get_model(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading_embedding_model", model_name=self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @retry(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts with bge-m3.

        Args:
            texts: The texts to embed, in order.

        Returns:
            One 1024-dimensional embedding vector per input text.
        """
        return await asyncio.to_thread(self._encode, texts)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        # Runs off the event loop (see embed_batch) — synchronous, and on
        # first call downloads the model; the apps/api copy of this same
        # class had this bug for real (blocked every concurrent request
        # on a single-process server) — fixed here too even though the
        # worker only ever runs one document at a time today, since the
        # underlying mistake (blocking the loop from inside `async def`)
        # is the same regardless of what else happens to be running.
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
        return [vector.tolist() for vector in embeddings]
