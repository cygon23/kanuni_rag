"""Answer-quality eval: faithfulness, citation precision/recall, refusal accuracy (§10).

Per PROJECT_SPEC.md §13, evals are the only place real models run. This
script drives the real query path (`kanuni_api.services.query_service.run_query`)
against a running Postgres instance with real embedding/reranker/LLM
providers, then scores each answer with a judge LLM that is deliberately
a *different* (smaller) Groq model than the one that generated the answer
(`Settings.eval_judge_llm_model` vs `Settings.llm_model`) — grading your
own answers with the same model that produced them inflates scores.

Metrics:
  - Refusal accuracy: computed directly from `answered` vs the golden
    item's `must_refuse` flag — no judge needed. Reports false-answer rate
    (answered when it should have refused) and false-refusal rate (refused
    an answerable question).
  - Citation precision: computed directly from the raw streamed answer
    text vs the server's post-validation citation list — no judge needed.
    precision = (chunk ids that survived validation) / (chunk ids the LLM
    attempted to cite at all, valid or hallucinated).
  - Faithfulness + citation recall: judged. The judge is given the
    question, the retrieved chunk texts, the generated answer, and the
    golden item's `ideal_answer_points`, and asked to return JSON scoring
    (a) what fraction of the answer's claims are grounded in the provided
    chunks, and (b) how many of the ideal answer points the answer covers.
    This is inherently approximate (no human-verified chunk-level ground
    truth exists yet) — treated as a directional signal, not a precise
    metric, until Phase 4's DRAFT golden set (see golden/README.md) has
    been through domain-expert review.
"""

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import UUID

import asyncpg

from kanuni_api.config import Settings, get_settings
from kanuni_api.embedding import Bgem3EmbeddingProvider
from kanuni_api.generation.llm_client import FallbackLLMProvider, GroqLLMProvider
from kanuni_api.reranker import Bgereranker
from kanuni_api.services.query_service import run_query
from kanuni_api.services.retrieval_service import retrieve

GOLDEN_DIR = Path(__file__).parent / "golden"
DEFAULT_GOLDEN_PATH = GOLDEN_DIR / "qa.jsonl"
_RAW_CITATION_PATTERN = re.compile(r"\[chunk:([0-9a-fA-F-]{36})\]")

_JUDGE_SYSTEM_PROMPT = """\
You are grading a regulatory Q&A system's answer for a Bank of Tanzania \
compliance eval. You will be given the question, the source text chunks \
the system was allowed to use, the system's answer, and a list of points \
a good answer should ideally cover. Respond with ONLY a JSON object, no \
other text, matching exactly this shape:

{"faithfulness_score": <float 0.0-1.0>, "unsupported_claims": [<string>, ...], \
"ideal_points_covered": <integer>}

faithfulness_score: the fraction of factual claims in the answer that are \
directly supported by the provided chunks (1.0 = every claim is grounded, \
0.0 = none are). unsupported_claims: short quotes of any claim not \
supported by the chunks (empty list if none). ideal_points_covered: how \
many of the listed ideal answer points are substantively present in the \
answer (an integer from 0 to the number of points given).
"""


@dataclass
class GoldenItem:
    """One golden-set question, including the fields answer eval needs."""

    id: str
    question: str
    language: str
    must_refuse: bool
    ideal_answer_points: list[str] = field(default_factory=list)


@dataclass
class ItemResult:
    """Per-item outcome, kept for the aggregate report and for debugging."""

    id: str
    must_refuse: bool
    answered: bool
    confidence: str
    correct_refusal_decision: bool
    citation_precision: float | None = None
    faithfulness_score: float | None = None
    ideal_points_covered: int | None = None
    ideal_points_total: int = 0
    unsupported_claims: list[str] = field(default_factory=list)


@dataclass
class AggregateMetrics:
    """Aggregated answer-eval metrics across the golden set."""

    n_items: int = 0
    false_answer_rate: float = 0.0
    false_refusal_rate: float = 0.0
    avg_citation_precision: float | None = None
    avg_faithfulness_score: float | None = None
    avg_citation_recall: float | None = None


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
                must_refuse=raw["must_refuse"],
                ideal_answer_points=raw.get("ideal_answer_points", []),
            )
        )
    return items


def _extract_cited_chunk_ids(raw_answer_text: str) -> set[UUID]:
    cited = set()
    for match in _RAW_CITATION_PATTERN.finditer(raw_answer_text):
        try:
            cited.add(UUID(match.group(1)))
        except ValueError:
            continue
    return cited


def _parse_judge_response(text: str) -> dict[str, object] | None:
    try:
        parsed: dict[str, object] = json.loads(text)
        return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return None
    try:
        result: dict[str, object] = json.loads(match.group(0))
        return result
    except json.JSONDecodeError:
        return None


async def _judge_answer(
    judge_provider: GroqLLMProvider,
    question: str,
    chunk_texts: list[str],
    answer_text: str,
    ideal_answer_points: list[str],
) -> tuple[float | None, int | None, list[str]]:
    """Return (faithfulness_score, ideal_points_covered, unsupported_claims)."""
    chunks_block = "\n\n".join(f"[chunk {i}] {text}" for i, text in enumerate(chunk_texts))
    points_block = "\n".join(f"- {point}" for point in ideal_answer_points) or "(none listed)"
    user_prompt = (
        f"Question: {question}\n\nSource chunks:\n{chunks_block}\n\n"
        f"System's answer:\n{answer_text}\n\nIdeal answer points:\n{points_block}"
    )

    raw = ""
    async for chunk in judge_provider.generate(
        system_prompt=_JUDGE_SYSTEM_PROMPT, user_prompt=user_prompt
    ):
        raw += chunk.text_delta

    parsed = _parse_judge_response(raw)
    if parsed is None:
        return None, None, []
    score = parsed.get("faithfulness_score")
    covered = parsed.get("ideal_points_covered")
    claims = parsed.get("unsupported_claims")
    return (
        float(score) if isinstance(score, int | float) else None,
        int(covered) if isinstance(covered, int) else None,
        list(claims) if isinstance(claims, list) else [],
    )


async def _run_one_item(
    connection: asyncpg.Connection,
    item: GoldenItem,
    *,
    settings: Settings,
    embedding_provider: Bgem3EmbeddingProvider,
    reranker_provider: Bgereranker,
    answer_llm_provider: FallbackLLMProvider,
    judge_provider: GroqLLMProvider,
) -> ItemResult:
    raw_answer_text = ""
    metadata: dict[str, object] = {}
    async for event in run_query(
        connection,
        item.question,
        settings=settings,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
        llm_provider=answer_llm_provider,
        api_key_id=None,
    ):
        if event["event"] == "token":
            raw_answer_text += event["data"]
        else:
            metadata = event["data"]

    answered = bool(metadata.get("answered", False))
    confidence = str(metadata.get("confidence", "refuse"))
    correct_decision = answered != item.must_refuse

    result = ItemResult(
        id=item.id,
        must_refuse=item.must_refuse,
        answered=answered,
        confidence=confidence,
        correct_refusal_decision=correct_decision,
        ideal_points_total=len(item.ideal_answer_points),
    )

    if not answered:
        return result

    citations = cast(list[dict[str, object]], metadata.get("citations", []))
    valid_chunk_ids = {UUID(str(c["chunk_id"])) for c in citations}
    all_cited_ids = _extract_cited_chunk_ids(raw_answer_text)
    if all_cited_ids:
        result.citation_precision = len(valid_chunk_ids & all_cited_ids) / len(all_cited_ids)

    if item.ideal_answer_points and not item.must_refuse:
        # A second, independent retrieve() call — run_query only returns
        # resolved citation *metadata* (title, section_ref, status), not
        # chunk text, and it doesn't expose the ScoredChunk list it used
        # internally. Retrieval is deterministic given the same question
        # and DB state, so this reproduces the same candidates purely to
        # recover .content for the chunks that were actually cited, at the
        # cost of one extra dense+sparse+rerank round trip per item.
        scored_chunks = await retrieve(
            connection,
            item.question,
            settings=settings,
            embedding_provider=embedding_provider,
            reranker_provider=reranker_provider,
        )
        chunk_texts = [c.content for c in scored_chunks if c.chunk_id in valid_chunk_ids]
        score, covered, unsupported = await _judge_answer(
            judge_provider,
            item.question,
            chunk_texts,
            raw_answer_text,
            item.ideal_answer_points,
        )
        result.faithfulness_score = score
        result.ideal_points_covered = covered
        result.unsupported_claims = unsupported

    return result


def _aggregate(results: list[ItemResult]) -> AggregateMetrics:
    n = len(results)
    false_answers = sum(1 for r in results if r.must_refuse and r.answered)
    n_must_refuse = sum(1 for r in results if r.must_refuse)
    false_refusals = sum(1 for r in results if not r.must_refuse and not r.answered)
    n_answerable = sum(1 for r in results if not r.must_refuse)

    precisions = [r.citation_precision for r in results if r.citation_precision is not None]
    faithfulness = [r.faithfulness_score for r in results if r.faithfulness_score is not None]
    recalls = [
        r.ideal_points_covered / r.ideal_points_total
        for r in results
        if r.ideal_points_covered is not None and r.ideal_points_total > 0
    ]

    return AggregateMetrics(
        n_items=n,
        false_answer_rate=(false_answers / n_must_refuse) if n_must_refuse else 0.0,
        false_refusal_rate=(false_refusals / n_answerable) if n_answerable else 0.0,
        avg_citation_precision=(sum(precisions) / len(precisions)) if precisions else None,
        avg_faithfulness_score=(sum(faithfulness) / len(faithfulness)) if faithfulness else None,
        avg_citation_recall=(sum(recalls) / len(recalls)) if recalls else None,
    )


def _print_summary(metrics: AggregateMetrics) -> None:
    print(f"\nItems evaluated: {metrics.n_items}")
    print(f"False-answer rate (answered a must-refuse item): {metrics.false_answer_rate:.3f}")
    print(f"False-refusal rate (refused an answerable item):  {metrics.false_refusal_rate:.3f}")
    if metrics.avg_citation_precision is not None:
        print(f"Average citation precision: {metrics.avg_citation_precision:.3f}")
    if metrics.avg_faithfulness_score is not None:
        print(f"Average faithfulness score (judge): {metrics.avg_faithfulness_score:.3f}")
    if metrics.avg_citation_recall is not None:
        print(f"Average ideal-point coverage (judge): {metrics.avg_citation_recall:.3f}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden",
        type=Path,
        default=DEFAULT_GOLDEN_PATH,
        help="Path to a JSONL golden set with ideal_answer_points (defaults to golden/qa.jsonl).",
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="Optional path to write results as JSON."
    )
    return parser.parse_args()


async def main() -> None:
    """Run the full answer-quality eval against a live Postgres + Groq."""
    args = _parse_args()
    settings = get_settings()
    database_url = os.environ.get("KANUNI_DATABASE_URL", settings.database_url)
    items = _load_golden_items(args.golden)
    print(f"Loaded {len(items)} golden items from {args.golden}")

    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. This eval calls a real Groq model for answer generation "
            "and a second, different Groq model as judge — see docs/NEEDS.md."
        )

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    if pool is None:
        raise RuntimeError("failed to connect to the database")

    embedding_provider = Bgem3EmbeddingProvider(settings.embedding_model)
    reranker_provider = Bgereranker(settings.reranker_model)
    answer_llm_provider = FallbackLLMProvider(
        GroqLLMProvider(api_key=settings.groq_api_key, model=settings.llm_model)
    )
    judge_provider = GroqLLMProvider(
        api_key=settings.groq_api_key, model=settings.eval_judge_llm_model
    )

    results = []
    async with pool.acquire() as connection:
        for item in items:
            print(f"Evaluating {item.id}: {item.question[:60]!r}")
            results.append(
                await _run_one_item(
                    connection,
                    item,
                    settings=settings,
                    embedding_provider=embedding_provider,
                    reranker_provider=reranker_provider,
                    answer_llm_provider=answer_llm_provider,
                    judge_provider=judge_provider,
                )
            )

    await pool.close()

    metrics = _aggregate(results)
    _print_summary(metrics)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "aggregate": vars(metrics),
                    "items": [vars(r) for r in results],
                },
                indent=2,
                default=str,
            )
        )
        print(f"\nWrote JSON results to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
