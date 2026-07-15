"""Orchestrates the hybrid retrieval pipeline: embed -> dense+sparse -> fuse -> rerank (§8.1)."""

import asyncio

import asyncpg

from kanuni_api.config import Settings
from kanuni_api.embedding import EmbeddingProvider
from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.reranker import RerankerProvider
from kanuni_api.retrieval import dense, fusion, rerank, sparse


async def retrieve(
    connection: asyncpg.Connection,
    question: str,
    *,
    settings: Settings,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    include_historical: bool = False,
) -> list[ScoredChunk]:
    """Run the full hybrid retrieval pipeline for one question.

    Args:
        connection: An open database connection.
        question: The user's question.
        settings: Application settings, providing every retrieval threshold.
        embedding_provider: Provider used to embed the question.
        reranker_provider: Provider used for cross-encoder reranking.
        include_historical: If True, superseded/repealed documents are
            included in dense and sparse candidates (§6 versioning rule).

    Returns:
        Up to `settings.rerank_top_k` chunks, ordered by descending rerank_score.
    """
    query_embedding = await embedding_provider.embed_query(question)

    dense_results, sparse_results = await asyncio.gather(
        dense.dense_search(
            connection,
            query_embedding,
            top_k=settings.dense_top_k,
            include_historical=include_historical,
        ),
        sparse.sparse_search(
            connection,
            question,
            top_k=settings.sparse_top_k,
            include_historical=include_historical,
        ),
    )

    fused = fusion.reciprocal_rank_fusion(
        dense_results, sparse_results, k=settings.rrf_k, top_k=settings.fusion_top_k
    )

    return await rerank.rerank_candidates(
        question, fused, reranker=reranker_provider, top_k=settings.rerank_top_k
    )
