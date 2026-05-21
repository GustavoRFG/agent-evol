"""Aggregate :class:`EvaluationResult` objects into a :class:`RunReport`.

This module turns a list of per-task evaluation results into a single
aggregated, JSON-serializable report, and provides helpers to save and load
that report from disk. Standard library only.

No agent is executed here — this layer only summarizes results that already
exist.
"""

from __future__ import annotations

import json
from pathlib import Path

from agenteval.core.schemas import (
    BenchmarkPack,
    EvaluationResult,
    RunReport,
    WeaknessCode,
)


class RunReportError(ValueError):
    """Raised when a run report cannot be parsed, loaded, or reconstructed.

    Subclasses :class:`ValueError` so callers may catch either type.
    """


def build_run_report(
    pack: BenchmarkPack,
    agent_name: str,
    results: list[EvaluationResult],
) -> RunReport:
    """Aggregate per-task results into a :class:`RunReport`.

    Args:
        pack: The benchmark pack the results came from.
        agent_name: Name of the evaluated agent.
        results: Per-task evaluation results, in the order they should appear.

    Returns:
        A :class:`RunReport` with ``total_tasks``, ``mean_score``, a
        ``weakness_tally`` (string keys), and the original results (order
        preserved). ``mean_score`` is ``0.0`` when ``results`` is empty.
    """
    total_tasks = len(results)
    mean_score = (
        sum(result.score for result in results) / total_tasks
        if total_tasks
        else 0.0
    )

    weakness_tally: dict[str, int] = {}
    for result in results:
        for weakness in result.weaknesses:
            key = _weakness_key(weakness)
            weakness_tally[key] = weakness_tally.get(key, 0) + 1

    return RunReport(
        pack_name=pack.name,
        pack_version=pack.version,
        agent_name=agent_name,
        total_tasks=total_tasks,
        mean_score=mean_score,
        weakness_tally=weakness_tally,
        results=list(results),  # copy so the report does not alias the input
    )


def run_report_to_dict(report: RunReport) -> dict:
    """Convert a :class:`RunReport` into a JSON-friendly dict."""
    return {
        "pack_name": report.pack_name,
        "pack_version": report.pack_version,
        "agent_name": report.agent_name,
        "total_tasks": report.total_tasks,
        "mean_score": report.mean_score,
        "weakness_tally": dict(report.weakness_tally),
        "results": [_result_to_dict(result) for result in report.results],
    }


def run_report_from_dict(data: dict) -> RunReport:
    """Reconstruct a :class:`RunReport` from a dict produced by serialization.

    Raises:
        RunReportError: If ``data`` is not a JSON object or a required field is
            missing.
    """
    if not isinstance(data, dict):
        raise RunReportError(
            f"Run report data must be a JSON object, got {type(data).__name__}"
        )

    missing = [
        name
        for name in ("pack_name", "pack_version", "agent_name")
        if name not in data
    ]
    if missing:
        raise RunReportError(
            f"Run report is missing required field(s): {', '.join(missing)}"
        )

    results = [_result_from_dict(item) for item in data.get("results", [])]

    return RunReport(
        pack_name=data["pack_name"],
        pack_version=data["pack_version"],
        agent_name=data["agent_name"],
        total_tasks=data.get("total_tasks", len(results)),
        mean_score=data.get("mean_score", 0.0),
        weakness_tally=dict(data.get("weakness_tally", {})),
        results=results,
    )


def save_run_report(report: RunReport, path: str | Path) -> None:
    """Save a :class:`RunReport` to ``path`` as indented UTF-8 JSON."""
    file_path = Path(path)
    payload = json.dumps(
        run_report_to_dict(report), indent=2, ensure_ascii=False
    )
    file_path.write_text(payload + "\n", encoding="utf-8")


def load_run_report(path: str | Path) -> RunReport:
    """Load a :class:`RunReport` from a JSON file.

    Raises:
        RunReportError: If the file is missing, unreadable, not valid JSON, or
            cannot be reconstructed into a :class:`RunReport`.
    """
    file_path = Path(path)

    if not file_path.is_file():
        raise RunReportError(f"Run report file not found: {file_path}")

    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - rare I/O failure
        raise RunReportError(
            f"Could not read run report {file_path}: {exc}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RunReportError(
            f"Invalid JSON in run report {file_path}: {exc}"
        ) from exc

    return run_report_from_dict(data)


# --- internal helpers ------------------------------------------------------


def _weakness_key(weakness: object) -> str:
    """Return the string key for a weakness (enum name or plain string)."""
    if isinstance(weakness, WeaknessCode):
        return weakness.value
    return str(weakness)


def _result_to_dict(result: EvaluationResult) -> dict:
    """Convert one :class:`EvaluationResult` into a JSON-friendly dict."""
    return {
        "task_id": result.task_id,
        "run_id": result.run_id,
        "score": result.score,
        "passed_public_tests": result.passed_public_tests,
        "passed_hidden_tests": result.passed_hidden_tests,
        "weaknesses": [_weakness_key(w) for w in result.weaknesses],
        "rationale": result.rationale,
    }


def _result_from_dict(data: dict) -> EvaluationResult:
    """Reconstruct one :class:`EvaluationResult` from a dict."""
    if not isinstance(data, dict):
        raise RunReportError(
            f"Each result must be a JSON object, got {type(data).__name__}"
        )

    missing = [name for name in ("task_id", "run_id") if name not in data]
    if missing:
        raise RunReportError(
            f"Result is missing required field(s): {', '.join(missing)}"
        )

    weaknesses: list[WeaknessCode] = []
    for code in data.get("weaknesses", []):
        try:
            weaknesses.append(WeaknessCode(code))
        except ValueError as exc:
            raise RunReportError(f"Unknown weakness code: {code!r}") from exc

    return EvaluationResult(
        task_id=data["task_id"],
        run_id=data["run_id"],
        score=data.get("score", 0.0),
        passed_public_tests=data.get("passed_public_tests", False),
        passed_hidden_tests=data.get("passed_hidden_tests", False),
        weaknesses=weaknesses,
        rationale=data.get("rationale", ""),
    )
