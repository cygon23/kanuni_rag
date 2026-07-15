"""Cross-encoder reranker abstraction: never call the real model in tests (§13)."""

from typing import Protocol

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

logger = structlog.get_logger()

_MAX_ATTEMPTS = 3


class RerankerProvider(Protocol):
    """Scores (question, candidate text) pairs for cross-encoder reranking."""

    async def score(self, question: str, candidates: list[str]) -> list[float]:
        """Score each candidate's relevance to the question.

        Args:
            question: The user's question.
            candidates: Candidate chunk contents, in order.

        Returns:
            One relevance score per candidate, in the same order. Higher is
            more relevant; scores are not necessarily bounded to [0, 1].
        """
        ...


class Bgereranker:
    """Reranks with `BAAI/bge-reranker-v2-m3` via `sentence-transformers.CrossEncoder`.

    The model is loaded lazily on first use so importing this module never
    requires the (large) model weights to be present.
    """

    def __init__(self, model_name: str) -> None:
        """Configure the provider without loading the model yet.

        Args:
            model_name: The cross-encoder model identifier, e.g.
                `"BAAI/bge-reranker-v2-m3"`.
        """
        self._model_name = model_name
        self._model: object | None = None

    def _get_model(self) -> object:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("loading_reranker_model", model_name=self._model_name)
            self._model = CrossEncoder(self._model_name)
        return self._model

    @retry(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    async def score(self, question: str, candidates: list[str]) -> list[float]:
        """Score each candidate's relevance to the question.

        Args:
            question: The user's question.
            candidates: Candidate chunk contents, in order.

        Returns:
            One relevance score per candidate, in the same order.
        """
        if not candidates:
            return []
        model = self._get_model()
        pairs = [(question, candidate) for candidate in candidates]
        scores = model.predict(pairs)  # type: ignore[attr-defined]
        result: list[float] = [float(score) for score in scores]
        return result
