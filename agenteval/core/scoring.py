"""Scoring helpers for AgentEval Forge.

The scoring model here is intentionally simple for the first milestone: it
rewards passed tests and applies a flat penalty per recorded weakness. Scores
are always clamped to the inclusive range [0.0, 1.0].
"""

from __future__ import annotations

from collections.abc import Iterable

MIN_SCORE: float = 0.0
MAX_SCORE: float = 1.0

# Default contribution of each test bucket and the penalty per weakness.
DEFAULT_PUBLIC_WEIGHT: float = 0.5
DEFAULT_HIDDEN_WEIGHT: float = 0.5
DEFAULT_WEAKNESS_PENALTY: float = 0.1


def clamp_score(score: float) -> float:
    """Clamp ``score`` to the inclusive range [MIN_SCORE, MAX_SCORE]."""
    return max(MIN_SCORE, min(MAX_SCORE, score))


def compute_basic_score(
    passed_public_tests: bool,
    passed_hidden_tests: bool,
    weaknesses: Iterable[object] = (),
    *,
    public_weight: float = DEFAULT_PUBLIC_WEIGHT,
    hidden_weight: float = DEFAULT_HIDDEN_WEIGHT,
    weakness_penalty: float = DEFAULT_WEAKNESS_PENALTY,
) -> float:
    """Compute a simple [0.0, 1.0] score for an agent run.

    Passing the public and hidden test buckets each adds their weight. Every
    recorded weakness subtracts ``weakness_penalty``. The result is clamped.

    Args:
        passed_public_tests: Whether the public test suite passed.
        passed_hidden_tests: Whether the hidden test suite passed.
        weaknesses: An iterable of recorded weaknesses (only the count is used).
        public_weight: Score contribution for passing public tests.
        hidden_weight: Score contribution for passing hidden tests.
        weakness_penalty: Score deducted per recorded weakness.

    Returns:
        A score clamped to [0.0, 1.0].
    """
    score = 0.0
    if passed_public_tests:
        score += public_weight
    if passed_hidden_tests:
        score += hidden_weight

    score -= weakness_penalty * sum(1 for _ in weaknesses)
    return clamp_score(score)
