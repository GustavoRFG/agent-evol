"""JSON persistence for :class:`ComparisonReport` objects.

This module serializes and deserializes cross-agent comparison reports,
mirroring the :class:`RunReport` persistence style in
:mod:`agenteval.reports.run_report`. Nested run reports are delegated to the
existing ``run_report_to_dict`` / ``run_report_from_dict`` helpers so the two
layers stay consistent.

It is fully agent-agnostic: agent names come only from the
:class:`ComparisonReport` data and no provider is hardcoded. It performs no
agent execution, patch application, or test execution. Standard library only.
"""

from __future__ import annotations

import json
from pathlib import Path

from agenteval.core.schemas import ComparisonReport
from agenteval.reports import (
    RunReportError,
    run_report_from_dict,
    run_report_to_dict,
)


class ComparisonPersistenceError(ValueError):
    """Raised when a comparison report cannot be saved, loaded, or rebuilt.

    Subclasses :class:`ValueError` so callers may catch either type.
    """


def comparison_report_to_dict(comparison: ComparisonReport) -> dict:
    """Convert a :class:`ComparisonReport` into a JSON-friendly dict.

    The input comparison is not mutated; every nested container is copied.
    Nested run reports are serialized with the shared ``run_report_to_dict``
    helper so the format matches standalone run-report persistence.

    Args:
        comparison: The comparison report to serialize.

    Returns:
        A dict containing only JSON-friendly types.
    """
    return {
        "pack_name": comparison.pack_name,
        "pack_version": comparison.pack_version,
        "agents": list(comparison.agents),
        "total_tasks": comparison.total_tasks,
        "mean_scores_by_agent": dict(comparison.mean_scores_by_agent),
        "ranking": list(comparison.ranking),
        "weakness_tally_by_agent": {
            agent: dict(tally)
            for agent, tally in comparison.weakness_tally_by_agent.items()
        },
        "reports": [
            run_report_to_dict(report) for report in comparison.reports
        ],
    }


def comparison_report_from_dict(data: dict) -> ComparisonReport:
    """Reconstruct a :class:`ComparisonReport` from a serialized dict.

    Agents, ranking, mean scores, weakness tallies, and report order are all
    preserved. Optional fields fall back to safe defaults when missing.

    Args:
        data: A dict produced by :func:`comparison_report_to_dict`.

    Returns:
        A :class:`ComparisonReport`.

    Raises:
        ComparisonPersistenceError: If ``data`` is not a JSON object, a
            required field is missing, or a nested report is invalid.
    """
    if not isinstance(data, dict):
        raise ComparisonPersistenceError(
            f"Comparison report data must be a JSON object, got "
            f"{type(data).__name__}"
        )

    missing = [
        name for name in ("pack_name", "pack_version") if name not in data
    ]
    if missing:
        raise ComparisonPersistenceError(
            f"Comparison report is missing required field(s): "
            f"{', '.join(missing)}"
        )

    reports_data = data.get("reports", [])
    if not isinstance(reports_data, list):
        raise ComparisonPersistenceError(
            f"Comparison report 'reports' must be a list, got "
            f"{type(reports_data).__name__}"
        )

    reports = []
    for index, item in enumerate(reports_data):
        try:
            reports.append(run_report_from_dict(item))
        except RunReportError as exc:
            raise ComparisonPersistenceError(
                f"Comparison report has an invalid nested report at index "
                f"{index}: {exc}"
            ) from exc

    total_tasks = data.get("total_tasks")
    if total_tasks is None:
        # Fall back to the shared task count of the first report when the
        # field is absent; an empty comparison has zero tasks.
        total_tasks = reports[0].total_tasks if reports else 0

    return ComparisonReport(
        pack_name=data["pack_name"],
        pack_version=data["pack_version"],
        agents=list(data.get("agents", [])),
        total_tasks=total_tasks,
        mean_scores_by_agent=dict(data.get("mean_scores_by_agent", {})),
        ranking=list(data.get("ranking", [])),
        weakness_tally_by_agent={
            agent: dict(tally)
            for agent, tally in data.get(
                "weakness_tally_by_agent", {}
            ).items()
        },
        reports=reports,
    )


def save_comparison_report(
    comparison: ComparisonReport, path: str | Path
) -> None:
    """Save a :class:`ComparisonReport` to ``path`` as indented UTF-8 JSON.

    Parent directories are created if they do not already exist.

    Args:
        comparison: The comparison report to save.
        path: Destination file path.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        comparison_report_to_dict(comparison), indent=2, ensure_ascii=False
    )
    file_path.write_text(payload + "\n", encoding="utf-8")


def load_comparison_report(path: str | Path) -> ComparisonReport:
    """Load a :class:`ComparisonReport` from a JSON file.

    Args:
        path: Path to a file produced by :func:`save_comparison_report`.

    Returns:
        The reconstructed :class:`ComparisonReport`.

    Raises:
        ComparisonPersistenceError: If the file is missing, unreadable, not
            valid JSON, or cannot be reconstructed into a
            :class:`ComparisonReport`.
    """
    file_path = Path(path)

    if not file_path.is_file():
        raise ComparisonPersistenceError(
            f"Comparison report file not found: {file_path}"
        )

    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - rare I/O failure
        raise ComparisonPersistenceError(
            f"Could not read comparison report {file_path}: {exc}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ComparisonPersistenceError(
            f"Invalid JSON in comparison report {file_path}: {exc}"
        ) from exc

    return comparison_report_from_dict(data)
