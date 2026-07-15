"""Tests for cross-encoder reranking: score attachment, ordering, and top_k truncation."""

from uuid import uuid4

from api_fakes import FakeRerankerProvider

from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.retrieval.rerank import rerank_candidates


def _chunk(content: str) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content=content,
        section_ref=None,
        page_start=1,
        page_end=1,
    )


async def test_rerank_orders_by_descending_score() -> None:
    """Candidates must come back sorted by rerank_score, not input order."""
    candidates = [_chunk("a"), _chunk("bbb"), _chunk("bb")]
    reranker = FakeRerankerProvider(scores=[0.1, 0.9, 0.5])

    reranked = await rerank_candidates("question", candidates, reranker=reranker, top_k=10)

    assert [chunk.rerank_score for chunk in reranked] == [0.9, 0.5, 0.1]


async def test_rerank_truncates_to_top_k() -> None:
    """Only the top_k highest-scoring candidates should be returned."""
    candidates = [_chunk(str(i)) for i in range(5)]
    reranker = FakeRerankerProvider(scores=[0.1, 0.5, 0.9, 0.2, 0.8])

    reranked = await rerank_candidates("question", candidates, reranker=reranker, top_k=2)

    assert len(reranked) == 2
    assert reranked[0].rerank_score == 0.9
    assert reranked[1].rerank_score == 0.8


async def test_rerank_calls_the_provider_with_question_and_contents() -> None:
    """The reranker must be called once with the question and every candidate's content."""
    candidates = [_chunk("first"), _chunk("second")]
    reranker = FakeRerankerProvider(scores=[0.1, 0.2])

    await rerank_candidates("what is X?", candidates, reranker=reranker, top_k=10)

    assert reranker.calls == [("what is X?", ["first", "second"])]


async def test_rerank_handles_no_candidates() -> None:
    """Reranking an empty candidate list must return empty, without calling the provider."""
    reranker = FakeRerankerProvider()

    reranked = await rerank_candidates("question", [], reranker=reranker, top_k=10)

    assert reranked == []
    assert reranker.calls == []
