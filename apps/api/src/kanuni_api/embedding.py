"""Embedding provider abstraction for the query path: never call the real model in tests (§13).

Mirrors `kanuni_ingest.embedding` — the two services share the database,
not code (ADR 0005), so each keeps its own small copy of this interface.
"""

from typing import Protocol

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

logger = structlog.get_logger()

_MAX_ATTEMPTS = 3


class EmbeddingProvider(Protocol):
    """Embeds a user question into the same vector space as indexed chunks."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string.

        Args:
            text: The user's question.

        Returns:
            A 1024-dimensional embedding vector.
        """
        ...


class Bgem3EmbeddingProvider:
    """Embeds queries with `BAAI/bge-m3` via `sentence-transformers` (PROJECT_SPEC.md §2).

    The model is loaded lazily on first use so importing this module never
    requires the (large) model weights to be present.
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
    async def embed_query(self, text: str) -> list[float]:
        """Embed a query with bge-m3.

        Args:
            text: The user's question.

        Returns:
            A 1024-dimensional embedding vector.
        """
        model = self._get_model()
        vector = model.encode([text], normalize_embeddings=True)[0]  # type: ignore[attr-defined]
        result: list[float] = vector.tolist()
        return result
