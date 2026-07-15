"""Tests for Reciprocal Rank Fusion: score math, dedup, and merged fields."""

from uuid import uuid4

from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.retrieval.fusion import reciprocal_rank_fusion


def _chunk(**overrides: object) -> ScoredChunk:
    defaults: dict[str, object] = {
        "chunk_id": uuid4(),
        "document_id": uuid4(),
        "content": "some content",
        "section_ref": None,
        "page_start": 1,
        "page_end": 1,
    }
    defaults.update(overrides)
    return ScoredChunk.model_validate(defaults)


def test_fusion_ranks_a_chunk_present_in_both_lists_highest() -> None:
    """A chunk ranked well in both lists should score higher than one only in one list."""
    shared_id = uuid4()
    shared_dense = _chunk(chunk_id=shared_id, dense_score=0.9)
    shared_sparse = shared_dense.model_copy(update={"sparse_score": 0.5, "dense_score": None})
    dense_only = _chunk(dense_score=0.8)

    fused = reciprocal_rank_fusion(
        dense_results=[shared_dense, dense_only],
        sparse_results=[shared_sparse],
        k=60,
        top_k=10,
    )

    assert fused[0].chunk_id == shared_id
    assert fused[0].dense_score == 0.9
    assert fused[0].sparse_score == 0.5


def test_fusion_computes_the_rrf_formula_exactly() -> None:
    """fused_score must equal the literal RRF sum of 1/(k+rank) across lists."""
    chunk_a = _chunk()
    chunk_b = _chunk()

    fused = reciprocal_rank_fusion(
        dense_results=[chunk_a, chunk_b], sparse_results=[chunk_b, chunk_a], k=60, top_k=10
    )

    scores = {chunk.chunk_id: chunk.fused_score for chunk in fused}
    expected = 1 / 61 + 1 / 62  # each chunk is rank 1 in one list, rank 2 in the other
    assert scores[chunk_a.chunk_id] == expected
    assert scores[chunk_b.chunk_id] == expected


def test_fusion_respects_top_k() -> None:
    """Only the top_k highest-scoring fused candidates should be returned."""
    chunks = [_chunk(dense_score=1.0 - i * 0.01) for i in range(5)]

    fused = reciprocal_rank_fusion(dense_results=chunks, sparse_results=[], k=60, top_k=2)

    assert len(fused) == 2
    assert fused[0].chunk_id == chunks[0].chunk_id
    assert fused[1].chunk_id == chunks[1].chunk_id


def test_fusion_handles_empty_inputs() -> None:
    """Two empty candidate lists should fuse to an empty result, not raise."""
    fused = reciprocal_rank_fusion(dense_results=[], sparse_results=[], k=60, top_k=10)

    assert fused == []
