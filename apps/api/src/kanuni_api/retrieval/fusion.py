"""Reciprocal Rank Fusion: merges dense and sparse candidate rankings (§8.1)."""

from uuid import UUID

from kanuni_api.models.retrieval import ScoredChunk


def reciprocal_rank_fusion(
    dense_results: list[ScoredChunk],
    sparse_results: list[ScoredChunk],
    *,
    k: int,
    top_k: int,
) -> list[ScoredChunk]:
    """Fuse dense and sparse rankings via Reciprocal Rank Fusion.

    Args:
        dense_results: Dense candidates, ordered by descending dense_score.
        sparse_results: Sparse candidates, ordered by descending sparse_score.
        k: The RRF constant (§8.1 default 60) — dampens the influence of low ranks.
        top_k: Maximum number of fused candidates to return (§8.1 default 20).

    Returns:
        Candidates ordered by descending fused RRF score, deduplicated by
        chunk id; a chunk appearing in both lists carries both its
        dense_score and sparse_score.
    """
    rrf_scores: dict[UUID, float] = {}
    merged: dict[UUID, ScoredChunk] = {}

    for rank, chunk in enumerate(dense_results, start=1):
        rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        merged[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(sparse_results, start=1):
        rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        if chunk.chunk_id in merged:
            merged[chunk.chunk_id] = merged[chunk.chunk_id].model_copy(
                update={"sparse_score": chunk.sparse_score}
            )
        else:
            merged[chunk.chunk_id] = chunk

    ranked_ids = sorted(rrf_scores, key=lambda chunk_id: rrf_scores[chunk_id], reverse=True)
    return [
        merged[chunk_id].model_copy(update={"fused_score": rrf_scores[chunk_id]})
        for chunk_id in ranked_ids[:top_k]
    ]
