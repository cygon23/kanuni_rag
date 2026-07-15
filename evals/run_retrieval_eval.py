"""Computes recall@5, recall@20, MRR, and nDCG@10 for dense/sparse/hybrid/hybrid+rerank.

Per PROJECT_SPEC.md §13, evals are the only place real embedding/reranker
models run. Ground truth is document-level (a retrieved chunk counts as
relevant if it belongs to the golden item's expected document) — golden
items don't pin exact chunk ids, since those are only assigned at
ingestion time. nDCG@10 uses an approximated ideal ranking (every position
up to k assumed relevant) rather than tracking the exact relevant-chunk
count per query — documented here as a deliberate simplification; a more
exact implementation may be warranted once golden items carry per-chunk
relevance judgments.

Defaults to golden/fixture_qa.jsonl (the small Phase 2 smoke set, 12
items). Pass --golden golden/qa.jsonl to run the full 60+-item DRAFT
dataset from Phase 4 (see golden/qa.jsonl's header comment on its draft
status) against ingested fixtures.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import UUID

import asyncpg

from kanuni_api.config import get_settings
from kanuni_api.embedding import Bgem3EmbeddingProvider
from kanuni_api.models.retrieval import ScoredChunk
from kanuni_api.reranker import Bgereranker
from kanuni_api.retrieval import dense, fusion, rerank, sparse

FIXTURES_DIR = Path(__file__).parent.parent / "apps" / "ingestion" / "tests" / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"
DEFAULT_GOLDEN_PATH = GOLDEN_DIR / "fixture_qa.jsonl"
_EVAL_RERANK_TOP_K = 20  # keep every fused candidate ranked, so recall@20 is meaningful


@dataclass
class GoldenItem:
    """One fixture-golden-set question."""

    id: str
    question: str
    language: str
    relevant_document_filename: str | None
    must_refuse: bool


@dataclass
class ModeMetrics:
    """Aggregated retrieval metrics for one retrieval mode."""

    recall_at_5: float = 0.0
    recall_at_20: float = 0.0
    mrr: float = 0.0
    ndcg_at_10: float = 0.0
    refusal_item_top_scores: list[float] = field(default_factory=list)


def _load_golden_items(golden_path: Path) -> list[GoldenItem]:
    items = []
    for line in golden_path.read_text().splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        items.append(
            GoldenItem(
                id=raw["id"],
                question=raw["question"],
                language=raw["language"],
                relevant_document_filename=raw["relevant_document_filename"],
                must_refuse=raw["must_refuse"],
            )
        )
    return items


async def _resolve_document_id(connection: asyncpg.Connection, filename: str) -> UUID | None:
    file_sha256 = hashlib.sha256((FIXTURES_DIR / filename).read_bytes()).hexdigest()
    document_id = await connection.fetchval(
        "SELECT id FROM documents WHERE file_sha256 = $1", file_sha256
    )
    return cast(UUID | None, document_id)


def _recall_at_k(results: list[ScoredChunk], expected_document_id: UUID, k: int) -> float:
    return 1.0 if any(chunk.document_id == expected_document_id for chunk in results[:k]) else 0.0


def _reciprocal_rank(results: list[ScoredChunk], expected_document_id: UUID) -> float:
    for rank, chunk in enumerate(results, start=1):
        if chunk.document_id == expected_document_id:
            return 1.0 / rank
    return 0.0


def _ndcg_at_10(results: list[ScoredChunk], expected_document_id: UUID) -> float:
    k = min(10, len(results))
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk in enumerate(results[:k], start=1)
        if chunk.document_id == expected_document_id
    )
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, k + 1))
    return dcg / idcg if idcg > 0 else 0.0


async def _run_mode(
    label: str,
    items: list[GoldenItem],
    results_by_item: dict[str, list[ScoredChunk]],
    connection: asyncpg.Connection,
) -> ModeMetrics:
    metrics = ModeMetrics()
    scored_items = [item for item in items if not item.must_refuse]
    if not scored_items:
        return metrics

    for item in items:
        results = results_by_item[item.id]
        if item.must_refuse:
            top_score = results[0].rerank_score or results[0].fused_score or 0.0 if results else 0.0
            metrics.refusal_item_top_scores.append(top_score)
            continue
        expected_id = await _resolve_document_id(connection, item.relevant_document_filename)  # type: ignore[arg-type]
        if expected_id is None:
            print(f"  [{label}] WARNING: {item.id} — expected document not ingested, skipping")
            continue
        metrics.recall_at_5 += _recall_at_k(results, expected_id, 5)
        metrics.recall_at_20 += _recall_at_k(results, expected_id, 20)
        metrics.mrr += _reciprocal_rank(results, expected_id)
        metrics.ndcg_at_10 += _ndcg_at_10(results, expected_id)

    n = len(scored_items)
    metrics.recall_at_5 /= n
    metrics.recall_at_20 /= n
    metrics.mrr /= n
    metrics.ndcg_at_10 /= n
    return metrics


def _print_table(all_metrics: dict[str, ModeMetrics]) -> None:
    header = f"{'mode':<16} {'recall@5':>10} {'recall@20':>10} {'MRR':>8} {'nDCG@10':>8}"
    print(header)
    print("-" * len(header))
    for label, metrics in all_metrics.items():
        print(
            f"{label:<16} {metrics.recall_at_5:>10.3f} {metrics.recall_at_20:>10.3f} "
            f"{metrics.mrr:>8.3f} {metrics.ndcg_at_10:>8.3f}"
        )
    print()
    for label, metrics in all_metrics.items():
        if metrics.refusal_item_top_scores:
            average = sum(metrics.refusal_item_top_scores) / len(metrics.refusal_item_top_scores)
            print(f"{label}: average top score on must-refuse items = {average:.3f}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden",
        type=Path,
        default=DEFAULT_GOLDEN_PATH,
        help=(
            "Path to a JSONL golden set (defaults to the small fixture_qa.jsonl smoke set; "
            "pass golden/qa.jsonl for the full 60+-item DRAFT dataset)."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write metrics as JSON, for report.py to consume.",
    )
    return parser.parse_args()


def _metrics_to_json(all_metrics: dict[str, ModeMetrics]) -> dict[str, object]:
    return {
        label: {
            "recall_at_5": metrics.recall_at_5,
            "recall_at_20": metrics.recall_at_20,
            "mrr": metrics.mrr,
            "ndcg_at_10": metrics.ndcg_at_10,
            "refusal_item_avg_top_score": (
                sum(metrics.refusal_item_top_scores) / len(metrics.refusal_item_top_scores)
                if metrics.refusal_item_top_scores
                else None
            ),
        }
        for label, metrics in all_metrics.items()
    }


async def main() -> None:
    """Run the dense/sparse/hybrid/hybrid+rerank comparison on a golden set."""
    args = _parse_args()
    settings = get_settings()
    database_url = os.environ.get("KANUNI_DATABASE_URL", settings.database_url)
    items = _load_golden_items(args.golden)
    print(f"Loaded {len(items)} golden items from {args.golden}")

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    if pool is None:
        raise RuntimeError("failed to connect to the database")

    embedding_provider = Bgem3EmbeddingProvider(settings.embedding_model)
    reranker_provider = Bgereranker(settings.reranker_model)

    dense_results: dict[str, list[ScoredChunk]] = {}
    sparse_results: dict[str, list[ScoredChunk]] = {}
    hybrid_results: dict[str, list[ScoredChunk]] = {}
    hybrid_rerank_results: dict[str, list[ScoredChunk]] = {}

    async with pool.acquire() as connection:
        for item in items:
            print(f"Retrieving for {item.id}: {item.question[:60]!r}")
            query_embedding = await embedding_provider.embed_query(item.question)

            item_dense = await dense.dense_search(
                connection, query_embedding, top_k=settings.dense_top_k, include_historical=False
            )
            item_sparse = await sparse.sparse_search(
                connection, item.question, top_k=settings.sparse_top_k, include_historical=False
            )
            item_fused = fusion.reciprocal_rank_fusion(
                item_dense, item_sparse, k=settings.rrf_k, top_k=settings.fusion_top_k
            )
            item_reranked = await rerank.rerank_candidates(
                item.question, item_fused, reranker=reranker_provider, top_k=_EVAL_RERANK_TOP_K
            )

            dense_results[item.id] = item_dense
            sparse_results[item.id] = item_sparse
            hybrid_results[item.id] = item_fused
            hybrid_rerank_results[item.id] = item_reranked

        all_metrics = {
            "dense-only": await _run_mode("dense-only", items, dense_results, connection),
            "sparse-only": await _run_mode("sparse-only", items, sparse_results, connection),
            "hybrid": await _run_mode("hybrid", items, hybrid_results, connection),
            "hybrid+rerank": await _run_mode(
                "hybrid+rerank", items, hybrid_rerank_results, connection
            ),
        }

    await pool.close()

    print()
    _print_table(all_metrics)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(_metrics_to_json(all_metrics), indent=2))
        print(f"\nWrote JSON results to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
