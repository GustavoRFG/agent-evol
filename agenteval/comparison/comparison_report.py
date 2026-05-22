"""Aggregate multiple :class:`RunReport` objects into a :class:`ComparisonReport`.

This module compares run reports produced on the **same benchmark pack and
version**, ranking agents by mean score and collecting their weakness tallies.

It is fully agent-agnostic: agents are identified only by ``report.agent_name``,
and no provider name is hardcoded anywhere. It performs no agent execution,
patch application, or test execution. Standard library only.
"""

from __future__ import annotations

from agenteval.core.schemas import ComparisonReport, RunReport


class ComparisonReportError(ValueError):
    """Raised when a set of run reports cannot be compared.

    Subclasses :class:`ValueError` so callers may catch either type.
    """


def build_comparison_report(reports: list[RunReport]) -> ComparisonReport:
    """Build a cross-agent :class:`ComparisonReport` from run reports.

    All reports must come from the same benchmark pack: identical
    ``pack_name``, ``pack_version``, and ``total_tasks``. Each report must
    describe a distinct agent (unique ``agent_name``).

    Agents and reports keep their input order. ``ranking`` orders agents by
    mean score descending, breaking ties alphabetically by ``agent_name`` so
    the result is deterministic. Input reports are not mutated.

    Args:
        reports: Run reports to compare; must be non-empty.

    Returns:
        A :class:`ComparisonReport`.

    Raises:
        ComparisonReportError: If ``reports`` is empty, the reports disagree on
            ``pack_name``/``pack_version``/``total_tasks``, or two reports
            share an ``agent_name``.
    """
    if not reports:
        raise ComparisonReportError(
            "build_comparison_report requires at least one RunReport."
        )

    pack_name = reports[0].pack_name
    pack_version = reports[0].pack_version
    total_tasks = reports[0].total_tasks

    for report in reports:
        if report.pack_name != pack_name:
            raise ComparisonReportError(
                f"All reports must share the same pack_name; found "
                f"'{pack_name}' and '{report.pack_name}'."
            )
        if report.pack_version != pack_version:
            raise ComparisonReportError(
                f"All reports must share the same pack_version; found "
                f"'{pack_version}' and '{report.pack_version}'."
            )
        if report.total_tasks != total_tasks:
            raise ComparisonReportError(
                f"All reports must share the same total_tasks; found "
                f"{total_tasks} and {report.total_tasks}."
            )

    agents: list[str] = []
    mean_scores_by_agent: dict[str, float] = {}
    weakness_tally_by_agent: dict[str, dict[str, int]] = {}

    for report in reports:
        agent = report.agent_name
        if agent in mean_scores_by_agent:
            raise ComparisonReportError(
                f"Duplicate agent_name across reports: '{agent}'."
            )
        agents.append(agent)
        mean_scores_by_agent[agent] = report.mean_score
        # Copy the tally so the comparison never aliases an input report.
        weakness_tally_by_agent[agent] = dict(report.weakness_tally)

    # Rank by mean score descending; tie-break alphabetically by agent name.
    ranking = sorted(
        agents,
        key=lambda agent: (-mean_scores_by_agent[agent], agent),
    )

    return ComparisonReport(
        pack_name=pack_name,
        pack_version=pack_version,
        agents=agents,
        total_tasks=total_tasks,
        mean_scores_by_agent=mean_scores_by_agent,
        ranking=ranking,
        weakness_tally_by_agent=weakness_tally_by_agent,
        reports=list(reports),
    )
