"""Pairwise (head-to-head) comparison between two agents in a comparison.

This module answers the AI-Code-Ranking style question directly: given a
:class:`ComparisonReport`, take **Agent A vs Agent B** and explain which one is
better — by mean score, by weakness profile, and task by task.

It is fully agent-agnostic: both agents are supplied by name and must already
appear in ``comparison.agents``; no provider name is hardcoded anywhere. It
performs no agent execution, patch application, or test execution, and never
mutates the input comparison. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from agenteval.comparison.task_matrix import build_task_score_matrix
from agenteval.core.schemas import ComparisonReport


class PairwiseComparisonError(ValueError):
    """Raised when two agents cannot be compared head-to-head.

    Subclasses :class:`ValueError` so callers may catch either type.
    """


@dataclass
class PairwiseComparison:
    """A head-to-head comparison of two agents within a comparison report.

    ``score_delta`` is ``mean_score_a - mean_score_b``; ``winner`` is the name
    of the higher-scoring agent, or ``"tie"`` when the mean scores are equal.
    Each ``*_delta`` mapping is expressed as *Agent A's value minus Agent B's*,
    so a positive number favours ``agent_a``.
    """

    agent_a: str
    agent_b: str
    winner: str
    mean_score_a: float
    mean_score_b: float
    score_delta: float
    weaknesses_a: dict[str, int] = field(default_factory=dict)
    weaknesses_b: dict[str, int] = field(default_factory=dict)
    weakness_delta: dict[str, int] = field(default_factory=dict)
    task_score_delta_by_task: dict[str, float] = field(default_factory=dict)
    rationale: str = ""


def compare_agents_pairwise(
    comparison: ComparisonReport,
    agent_a: str,
    agent_b: str,
) -> PairwiseComparison:
    """Compare two agents head-to-head inside a :class:`ComparisonReport`.

    Both agents must appear in ``comparison.agents`` and must be distinct. All
    figures are read straight from the comparison: mean scores from
    ``mean_scores_by_agent``, weakness counts from ``weakness_tally_by_agent``,
    and per-task scores from :func:`build_task_score_matrix`. The input
    comparison is never mutated.

    Args:
        comparison: The cross-agent comparison to draw both agents from.
        agent_a: Name of the first agent (the "A" side of every delta).
        agent_b: Name of the second agent (the "B" side of every delta).

    Returns:
        A :class:`PairwiseComparison` describing the head-to-head result.

    Raises:
        PairwiseComparisonError: If either agent is missing from
            ``comparison.agents``, or if ``agent_a`` equals ``agent_b``.
        ComparisonMatrixError: Propagated from :func:`build_task_score_matrix`
            if the underlying reports disagree on the task sequence.
    """
    if agent_a not in comparison.agents:
        raise PairwiseComparisonError(
            f"Agent '{agent_a}' is not in this comparison; "
            f"known agents: {comparison.agents}."
        )
    if agent_b not in comparison.agents:
        raise PairwiseComparisonError(
            f"Agent '{agent_b}' is not in this comparison; "
            f"known agents: {comparison.agents}."
        )
    if agent_a == agent_b:
        raise PairwiseComparisonError(
            f"Cannot compare agent '{agent_a}' against itself; "
            f"agent_a and agent_b must be different."
        )

    mean_score_a = comparison.mean_scores_by_agent.get(agent_a, 0.0)
    mean_score_b = comparison.mean_scores_by_agent.get(agent_b, 0.0)
    score_delta = mean_score_a - mean_score_b

    if mean_score_a > mean_score_b:
        winner = agent_a
    elif mean_score_b > mean_score_a:
        winner = agent_b
    else:
        winner = "tie"

    # Copy the tallies so the result never aliases the input comparison.
    weaknesses_a = dict(comparison.weakness_tally_by_agent.get(agent_a, {}))
    weaknesses_b = dict(comparison.weakness_tally_by_agent.get(agent_b, {}))

    # Every weakness key present for either agent, deterministically ordered.
    weakness_keys = sorted(set(weaknesses_a) | set(weaknesses_b))
    weakness_delta = {
        key: weaknesses_a.get(key, 0) - weaknesses_b.get(key, 0)
        for key in weakness_keys
    }

    # Per-task score gap, in the score matrix's task order.
    task_score_delta_by_task: dict[str, float] = {}
    for row in build_task_score_matrix(comparison):
        score_a = row.scores_by_agent.get(agent_a, 0.0)
        score_b = row.scores_by_agent.get(agent_b, 0.0)
        task_score_delta_by_task[row.task_id] = score_a - score_b

    rationale = _build_rationale(
        agent_a, agent_b, winner, mean_score_a, score_delta, comparison
    )

    return PairwiseComparison(
        agent_a=agent_a,
        agent_b=agent_b,
        winner=winner,
        mean_score_a=mean_score_a,
        mean_score_b=mean_score_b,
        score_delta=score_delta,
        weaknesses_a=weaknesses_a,
        weaknesses_b=weaknesses_b,
        weakness_delta=weakness_delta,
        task_score_delta_by_task=task_score_delta_by_task,
        rationale=rationale,
    )


def compare_all_agent_pairs(
    comparison: ComparisonReport,
) -> list[PairwiseComparison]:
    """Compare every unique pair of agents in a :class:`ComparisonReport`.

    Pairs follow ``comparison.agents`` order: for agents ``A, B, C`` the result
    is ``A vs B``, ``A vs C``, ``B vs C``. The order is deterministic and each
    unordered pair appears exactly once.

    Args:
        comparison: The cross-agent comparison to expand into pairs.

    Returns:
        One :class:`PairwiseComparison` per unordered agent pair; an empty list
        when the comparison has fewer than two agents.

    Raises:
        ComparisonMatrixError: Propagated from :func:`compare_agents_pairwise`
            if the underlying reports disagree on the task sequence.
    """
    return [
        compare_agents_pairwise(comparison, agent_a, agent_b)
        for agent_a, agent_b in combinations(comparison.agents, 2)
    ]


def _build_rationale(
    agent_a: str,
    agent_b: str,
    winner: str,
    mean_score_a: float,
    score_delta: float,
    comparison: ComparisonReport,
) -> str:
    """Return a short, deterministic explanation of the head-to-head winner."""
    if winner == "tie":
        return (
            f"{agent_a} and {agent_b} tie with an equal mean score of "
            f"{mean_score_a:.4f} across {comparison.total_tasks} task(s)."
        )
    leader, trailer = (
        (agent_a, agent_b) if winner == agent_a else (agent_b, agent_a)
    )
    return (
        f"{leader} outperforms {trailer} by {abs(score_delta):.4f} mean "
        f"score across {comparison.total_tasks} task(s)."
    )
