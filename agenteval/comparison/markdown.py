"""Render a :class:`ComparisonReport` as human-readable Markdown.

This renderer turns a cross-agent comparison into a Markdown document for human
review. It is fully agent-agnostic: every agent comes from ``comparison.agents``
and ``comparison.ranking`` — no provider name is hardcoded. The output is
deterministic. Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.comparison.divergence import top_divergent_tasks
from agenteval.comparison.task_matrix import build_task_score_matrix
from agenteval.core.schemas import ComparisonReport


def render_comparison_report_markdown(comparison: ComparisonReport) -> str:
    """Render a :class:`ComparisonReport` as a Markdown document.

    The document includes a title, pack metadata, a ranking table (rank, agent,
    mean score), a per-agent weakness tally, and an explanatory notes section.

    Ordering is deterministic: the ranking table follows ``comparison.ranking``,
    the weakness section follows ``comparison.agents``, and each agent's
    weakness codes are listed in alphabetical order.

    Args:
        comparison: The cross-agent comparison to render.

    Returns:
        A Markdown string ending with a single trailing newline.
    """
    lines: list[str] = []

    lines.append("# AgentEval Forge — Cross-Agent Comparison")
    lines.append("")
    lines.append(f"- **Benchmark pack:** {comparison.pack_name}")
    lines.append(f"- **Pack version:** {comparison.pack_version}")
    lines.append(f"- **Total tasks:** {comparison.total_tasks}")
    lines.append(f"- **Agents compared:** {len(comparison.agents)}")
    lines.append("")

    lines.extend(_ranking_section(comparison))
    lines.append("")
    lines.extend(_task_matrix_section(comparison))
    lines.append("")
    lines.extend(_divergence_section(comparison))
    lines.append("")
    lines.extend(_weakness_section(comparison))
    lines.append("")
    lines.extend(_notes_section(comparison))

    return "\n".join(lines).rstrip("\n") + "\n"


def save_comparison_report_markdown(
    comparison: ComparisonReport,
    path: str | Path,
) -> None:
    """Render ``comparison`` and write it to ``path`` as UTF-8 Markdown.

    Parent directories are created if they do not already exist.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        render_comparison_report_markdown(comparison), encoding="utf-8"
    )


# --- section builders ------------------------------------------------------


def _ranking_section(comparison: ComparisonReport) -> list[str]:
    lines = ["## Ranking", ""]
    if not comparison.ranking:
        lines.append("_No agents to compare._")
        return lines

    lines.append("| Rank | Agent | Mean score |")
    lines.append("| --- | --- | --- |")
    for rank, agent in enumerate(comparison.ranking, start=1):
        score = comparison.mean_scores_by_agent.get(agent, 0.0)
        lines.append(f"| {rank} | {agent} | {_format_score(score)} |")
    return lines


def _task_matrix_section(comparison: ComparisonReport) -> list[str]:
    """Render the per-task score matrix: one row per task, one column per agent.

    Cells are score-only (fixed ``.4f``) to keep the table readable as the
    agent count grows; per-task pass flags remain available on the underlying
    :class:`~agenteval.comparison.task_matrix.TaskScoreRow` objects.
    """
    lines = ["## Per-task score matrix", ""]
    matrix = build_task_score_matrix(comparison)
    if not matrix or not comparison.agents:
        lines.append("_No tasks to compare._")
        return lines

    lines.append("| Task ID | " + " | ".join(comparison.agents) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in comparison.agents) + " |")
    for row in matrix:
        cells = [
            _format_score(row.scores_by_agent.get(agent, 0.0))
            for agent in comparison.agents
        ]
        lines.append(f"| {row.task_id} | " + " | ".join(cells) + " |")
    return lines


def _divergence_section(comparison: ComparisonReport) -> list[str]:
    """Render the tasks on which agents disagree most, ordered by spread."""
    lines = ["## Tasks where agents most disagree", ""]
    divergences = top_divergent_tasks(comparison)
    if not divergences:
        lines.append("_No tasks to compare._")
        return lines

    lines.append(
        "| Task ID | Score spread | Best agents | Best score "
        "| Worst agents | Worst score |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for divergence in divergences:
        lines.append(
            f"| {divergence.task_id} "
            f"| {_format_score(divergence.score_spread)} "
            f"| {_agent_list(divergence.best_agents)} "
            f"| {_format_score(divergence.best_score)} "
            f"| {_agent_list(divergence.worst_agents)} "
            f"| {_format_score(divergence.worst_score)} |"
        )
    return lines


def _agent_list(agents: list[str]) -> str:
    return ", ".join(agents) if agents else "—"


def _weakness_section(comparison: ComparisonReport) -> list[str]:
    lines = ["## Weakness tally by agent", ""]
    if not comparison.agents:
        lines.append("_No agents to compare._")
        return lines

    for agent in comparison.agents:
        lines.append(f"### {agent}")
        lines.append("")
        tally = comparison.weakness_tally_by_agent.get(agent, {})
        if tally:
            lines.append("| Weakness | Count |")
            lines.append("| --- | --- |")
            for code in sorted(tally):
                lines.append(f"| {code} | {tally[code]} |")
        else:
            lines.append("_No weaknesses recorded._")
        lines.append("")
    return lines


def _notes_section(comparison: ComparisonReport) -> list[str]:
    return [
        "## Notes",
        "",
        (
            "This report compares the listed agents on the **same benchmark "
            f"pack and version** ({comparison.pack_name} v"
            f"{comparison.pack_version}). Mean scores are comparable only "
            f"because every agent was evaluated on the same "
            f"{comparison.total_tasks} task(s). Agents are identified solely "
            "by name; the comparison carries no provider-specific knowledge."
        ),
    ]


def _format_score(score: float) -> str:
    """Format a mean score with fixed precision for deterministic output."""
    return f"{score:.4f}"
