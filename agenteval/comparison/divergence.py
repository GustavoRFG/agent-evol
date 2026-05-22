"""Per-task divergence analysis for AgentEval Forge comparisons.

This module measures how much agents *disagree* on each benchmark task: the
best and worst score, the spread between them, and which agents achieved each
extreme. It builds directly on the per-task score matrix.

It is fully agent-agnostic — agents come only from the comparison data, no
provider name is hardcoded. It performs no agent execution, patch application,
or test execution. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agenteval.comparison.task_matrix import build_task_score_matrix
from agenteval.core.schemas import ComparisonReport


@dataclass
class TaskDivergence:
    """How much agents diverged on a single benchmark task.

    ``best_agents`` and ``worst_agents`` list every agent tied for the extreme
    score, in ``comparison.agents`` order.
    """

    task_id: str
    best_score: float
    worst_score: float
    score_spread: float
    best_agents: list[str] = field(default_factory=list)
    worst_agents: list[str] = field(default_factory=list)


def build_task_divergence_report(
    comparison: ComparisonReport,
) -> list[TaskDivergence]:
    """Build per-task divergence rows from a :class:`ComparisonReport`.

    For each task in the score matrix this computes the best and worst score,
    the spread between them, and the agents tied at each extreme. Task order
    follows the matrix; agent lists follow ``comparison.agents``. A task with
    no agent scores yields zeroed scores and empty agent lists.

    Input reports and matrix rows are not mutated.

    Args:
        comparison: The cross-agent comparison to analyze.

    Returns:
        One :class:`TaskDivergence` per task, in matrix task order.

    Raises:
        ComparisonMatrixError: Propagated from :func:`build_task_score_matrix`
            if the reports disagree on the task sequence.
    """
    divergences: list[TaskDivergence] = []

    for row in build_task_score_matrix(comparison):
        scores = row.scores_by_agent
        if not scores:
            divergences.append(
                TaskDivergence(
                    task_id=row.task_id,
                    best_score=0.0,
                    worst_score=0.0,
                    score_spread=0.0,
                )
            )
            continue

        best_score = max(scores.values())
        worst_score = min(scores.values())
        best_agents = [
            agent
            for agent in comparison.agents
            if agent in scores and scores[agent] == best_score
        ]
        worst_agents = [
            agent
            for agent in comparison.agents
            if agent in scores and scores[agent] == worst_score
        ]
        divergences.append(
            TaskDivergence(
                task_id=row.task_id,
                best_score=best_score,
                worst_score=worst_score,
                score_spread=best_score - worst_score,
                best_agents=best_agents,
                worst_agents=worst_agents,
            )
        )

    return divergences


def top_divergent_tasks(
    comparison: ComparisonReport,
    limit: int | None = None,
) -> list[TaskDivergence]:
    """Return divergence rows ordered by how much agents disagree.

    Rows are sorted by ``score_spread`` descending, breaking ties by ``task_id``
    alphabetically so the order is deterministic.

    Args:
        comparison: The cross-agent comparison to analyze.
        limit: Maximum number of rows to return; ``None`` returns all rows.

    Returns:
        The most divergent tasks first, at most ``limit`` rows.

    Raises:
        ValueError: If ``limit`` is negative.
    """
    if limit is not None and limit < 0:
        raise ValueError(f"limit must not be negative, got {limit}.")

    divergences = build_task_divergence_report(comparison)
    divergences.sort(key=lambda d: (-d.score_spread, d.task_id))

    if limit is None:
        return divergences
    return divergences[:limit]
