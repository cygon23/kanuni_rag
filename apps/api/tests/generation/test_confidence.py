"""Tests for the three-tier confidence gate (§8.2)."""

import pytest

from kanuni_api.generation.confidence import compute_confidence_tier

_REFUSE = 0.30
_CAUTION = 0.55


@pytest.mark.parametrize(
    ("score", "expected_tier"),
    [
        (None, "refuse"),
        (0.0, "refuse"),
        (0.29, "refuse"),
        (0.30, "low"),
        (0.40, "low"),
        (0.54, "low"),
        (0.55, "ok"),
        (0.90, "ok"),
        (1.0, "ok"),
    ],
)
def test_confidence_tier_boundaries(score: float | None, expected_tier: str) -> None:
    """Boundaries are inclusive on the upper side of refuse/low per §8.2's '<' semantics."""
    tier = compute_confidence_tier(score, refuse_threshold=_REFUSE, caution_threshold=_CAUTION)

    assert tier == expected_tier
