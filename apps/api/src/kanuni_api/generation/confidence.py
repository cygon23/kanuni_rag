"""Confidence gate: three-tier decision from the top rerank score (§8.2)."""

from typing import Literal

ConfidenceTier = Literal["refuse", "low", "ok"]


def compute_confidence_tier(
    top_rerank_score: float | None,
    *,
    refuse_threshold: float,
    caution_threshold: float,
) -> ConfidenceTier:
    """Classify retrieval confidence into a three-tier gate.

    Args:
        top_rerank_score: The highest rerank_score among retrieved chunks,
            or `None` if nothing was retrieved at all.
        refuse_threshold: Below this, refuse rather than generate
            (§8.2 default 0.30).
        caution_threshold: Below this (but at/above `refuse_threshold`),
            answer with a caution banner (§8.2 default 0.55).

    Returns:
        `"refuse"`, `"low"`, or `"ok"`.
    """
    if top_rerank_score is None or top_rerank_score < refuse_threshold:
        return "refuse"
    if top_rerank_score < caution_threshold:
        return "low"
    return "ok"
