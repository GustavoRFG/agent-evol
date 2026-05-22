"""Render a :class:`RunReport` as a human-readable Markdown report.

This module turns an aggregated :class:`RunReport` into Markdown for human
review. It performs no agent execution, patch analysis, or test execution — it
only formats data that already exists. The output is deterministic. Standard
library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.core.schemas import EvaluationResult, RunReport, WeaknessCode


def render_run_report_markdown(report: RunReport) -> str:
    """Render a :class:`RunReport` as a Markdown document.

    The document includes a title, the report metadata (pack name and version,
    agent name, total tasks, mean score), a weakness tally, a per-task results
    table, and a per-task rationale section. The output is deterministic:
    weakness tally rows are sorted, per-task rows follow ``report.results``
    order, and numbers use fixed formatting.

    Args:
        report: The aggregated run report to render.

    Returns:
        A Markdown string ending with a single trailing newline.
    """
    lines: list[str] = []

    lines.append("# AgentEval Forge — Run Report")
    lines.append("")
    lines.append(f"- **Benchmark pack:** {report.pack_name}")
    lines.append(f"- **Pack version:** {report.pack_version}")
    lines.append(f"- **Agent:** {report.agent_name}")
    lines.append(f"- **Total tasks:** {report.total_tasks}")
    lines.append(f"- **Mean score:** {_format_score(report.mean_score)}")
    lines.append("")

    lines.extend(_weakness_tally_section(report))
    lines.append("")
    lines.extend(_results_table_section(report))
    lines.append("")
    lines.extend(_patch_evidence_section(report))
    lines.append("")
    lines.extend(_rationale_section(report))

    return "\n".join(lines).rstrip("\n") + "\n"


def save_run_report_markdown(report: RunReport, path: str | Path) -> None:
    """Render ``report`` and write it to ``path`` as a UTF-8 Markdown file.

    Parent directories are created if they do not already exist.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        render_run_report_markdown(report), encoding="utf-8"
    )


# --- section builders ------------------------------------------------------


def _weakness_tally_section(report: RunReport) -> list[str]:
    lines = ["## Weakness tally", ""]
    if report.weakness_tally:
        lines.append("| Weakness | Count |")
        lines.append("| --- | --- |")
        for code in sorted(report.weakness_tally):
            lines.append(f"| {code} | {report.weakness_tally[code]} |")
    else:
        lines.append("_No weaknesses recorded._")
    return lines


def _results_table_section(report: RunReport) -> list[str]:
    lines = ["## Per-task results", ""]
    if not report.results:
        lines.append("_No tasks were evaluated._")
        return lines

    lines.append(
        "| Task ID | Run ID | Score | Public tests | Hidden tests "
        "| Weaknesses |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for result in report.results:
        lines.append(
            f"| {result.task_id} "
            f"| {result.run_id} "
            f"| {_format_score(result.score)} "
            f"| {_pass_fail(result.passed_public_tests)} "
            f"| {_pass_fail(result.passed_hidden_tests)} "
            f"| {_weaknesses_cell(result)} |"
        )
    return lines


def _patch_evidence_section(report: RunReport) -> list[str]:
    lines = ["## Patch evidence", ""]
    if not report.results:
        lines.append("_No tasks were evaluated._")
        return lines

    for result in report.results:
        lines.append(f"### {result.task_id}")
        lines.append("")
        lines.extend(_patch_evidence_for_result(result))
        lines.append("")
    return lines


def _patch_evidence_for_result(result: EvaluationResult) -> list[str]:
    """Render the patch evidence lines for a single task result."""
    patch = result.patch_summary
    if patch is None:
        return ["_No patch evidence recorded._"]

    if not (patch.changed_files or patch.added_files or patch.deleted_files):
        return [
            "_Patch evidence recorded, but no changed/added/deleted files "
            "were detected._"
        ]

    return [
        f"- **Changed files:** {_file_list(patch.changed_files)}",
        f"- **Added files:** {_file_list(patch.added_files)}",
        f"- **Deleted files:** {_file_list(patch.deleted_files)}",
    ]


def _file_list(files: list[str]) -> str:
    return ", ".join(files) if files else "—"


def _rationale_section(report: RunReport) -> list[str]:
    lines = ["## Per-task rationale", ""]
    if not report.results:
        lines.append("_No tasks were evaluated._")
        return lines

    for result in report.results:
        lines.append(f"### {result.task_id}")
        lines.append("")
        lines.append(f"- **Run ID:** {result.run_id}")
        lines.append("")
        lines.append(result.rationale.strip() or "_No rationale provided._")
        lines.append("")
    return lines


# --- formatting helpers ----------------------------------------------------


def _format_score(score: float) -> str:
    """Format a score with fixed precision for deterministic output."""
    return f"{score:.4f}"


def _pass_fail(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _weakness_label(weakness: object) -> str:
    """Return the display label for a weakness (enum value or plain string)."""
    if isinstance(weakness, WeaknessCode):
        return weakness.value
    return str(weakness)


def _weaknesses_cell(result: EvaluationResult) -> str:
    if not result.weaknesses:
        return "—"
    return ", ".join(_weakness_label(w) for w in result.weaknesses)
