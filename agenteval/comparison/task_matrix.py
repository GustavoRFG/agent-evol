"""Per-task cross-agent score matrix for AgentEval Forge comparisons.

This module turns a :class:`ComparisonReport` into a task-level view: one row
per benchmark task, each row carrying every agent's score, pass flags, and
weakness codes for that task.

It is fully agent-agnostic — agents come only from the comparison data, no
provider name is hardcoded. It performs no agent execution, patch application,
or test execution. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agenteval.core.schemas import ComparisonReport, WeaknessCode


class ComparisonMatrixError(ValueError):
    """Raised when a per-task matrix cannot be built from a comparison.

    Subclasses :class:`ValueError` so callers may catch either type.
    """


@dataclass
class TaskScoreRow:
    """One benchmark task's results across every compared agent.

    Each ``*_by_agent`` mapping is keyed by ``agent_name``.
    """

    task_id: str
    scores_by_agent: dict[str, float] = field(default_factory=dict)
    public_pass_by_agent: dict[str, bool] = field(default_factory=dict)
    hidden_pass_by_agent: dict[str, bool] = field(default_factory=dict)
    weaknesses_by_agent: dict[str, list[str]] = field(default_factory=dict)


def build_task_score_matrix(
    comparison: ComparisonReport,
) -> list[TaskScoreRow]:
    """Build a per-task score matrix from a :class:`ComparisonReport`.

    Task order is taken from the first report's results; agent order follows
    ``comparison.agents``. Every report must list exactly the same task ids in
    the same order. Input reports are not mutated.

    Args:
        comparison: The cross-agent comparison to expand into a matrix.

    Returns:
        One :class:`TaskScoreRow` per task, in the first report's task order.
        An empty list when the comparison has no reports.

    Raises:
        ComparisonMatrixError: If two reports disagree on the task id sequence,
            or the comparison names an agent with no matching report.
    """
    reports = comparison.reports
    if not reports:
        return []

    # Task order is defined by the first report.
    task_order = [result.task_id for result in reports[0].results]

    # Every report must cover exactly the same tasks, in the same order.
    for report in reports:
        report_task_ids = [result.task_id for result in report.results]
        if report_task_ids != task_order:
            raise ComparisonMatrixError(
                f"Report for agent '{report.agent_name}' has a different "
                f"task sequence than the first report: expected "
                f"{task_order}, got {report_task_ids}."
            )

    # Per-agent lookup of EvaluationResult by task id.
    results_by_agent: dict[str, dict[str, object]] = {
        report.agent_name: {
            result.task_id: result for result in report.results
        }
        for report in reports
    }

    rows: list[TaskScoreRow] = []
    for task_id in task_order:
        row = TaskScoreRow(task_id=task_id)
        for agent in comparison.agents:
            if agent not in results_by_agent:
                raise ComparisonMatrixError(
                    f"Comparison lists agent '{agent}' but has no matching "
                    f"report."
                )
            result = results_by_agent[agent][task_id]
            row.scores_by_agent[agent] = result.score
            row.public_pass_by_agent[agent] = result.passed_public_tests
            row.hidden_pass_by_agent[agent] = result.passed_hidden_tests
            row.weaknesses_by_agent[agent] = [
                _weakness_code(weakness) for weakness in result.weaknesses
            ]
        rows.append(row)
    return rows


def _weakness_code(weakness: object) -> str:
    """Return the string code for a weakness (enum value or plain string)."""
    if isinstance(weakness, WeaknessCode):
        return weakness.value
    return str(weakness)
