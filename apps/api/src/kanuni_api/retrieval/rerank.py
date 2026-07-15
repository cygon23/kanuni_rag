"""Cross-encoder reranking: scores fused candidates against the question directly (§8.1)."""

from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.reranker import RerankerProvider


async def rerank_candidates(
    question: str,
    candidates: list[ScoredChunk],
    *,
    reranker: RerankerProvider,
    top_k: int,
) -> list[ScoredChunk]:
    """Rerank fused candidates with a cross-encoder and keep the top-k.

    Args:
        question: The user's question.
        candidates: Fused candidates to rerank.
        reranker: Cross-encoder provider.
        top_k: Maximum number of reranked results to return (§8.1 default 6).

    Returns:
        Candidates ordered by descending rerank_score, truncated to top_k.
    """
    if not candidates:
        return []
    scores = await reranker.score(question, [candidate.content for candidate in candidates])
    scored = [
        candidate.model_copy(update={"rerank_score": score})
        for candidate, score in zip(candidates, scores, strict=True)
    ]
    scored.sort(key=lambda candidate: candidate.rerank_score or float("-inf"), reverse=True)
    return scored[:top_k]
