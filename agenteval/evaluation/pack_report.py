"""One-call pack evaluation: assemble a :class:`RunReport` from evidence.

This module is a thin orchestration layer. It chains the existing batch result
builder and run report aggregator so a caller can turn a :class:`BenchmarkPack`
plus per-task evidence into a :class:`RunReport` — and optionally save it — in a
single call. No logic is duplicated; it only composes existing helpers.

It performs **no** agent execution, patch application, or test execution.
Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.core.schemas import BenchmarkPack, RunReport
from agenteval.evaluation.batch_builder import (
    TaskEvidence,
    build_pack_evaluation_results,
)
from agenteval.reports.markdown import save_run_report_markdown
from agenteval.reports.run_report import build_run_report, save_run_report


def evaluate_pack_to_report(
    pack: BenchmarkPack,
    agent_name: str,
    evidence_by_task_id: dict[str, TaskEvidence],
) -> RunReport:
    """Assemble a :class:`RunReport` for a benchmark pack from per-task evidence.

    Results are built with :func:`build_pack_evaluation_results` (one per task,
    in ``pack.tasks`` order; tasks without evidence become unverified
    ``VERIFY`` results) and aggregated with :func:`build_run_report`.

    Args:
        pack: The benchmark pack to evaluate.
        agent_name: Name of the agent the report is attributed to.
        evidence_by_task_id: Map from ``task_id`` to its :class:`TaskEvidence`.

    Returns:
        A :class:`RunReport` aggregating one result per task.

    Raises:
        BatchEvaluationError: If ``evidence_by_task_id`` contains a ``task_id``
            not present in the pack (propagated from the batch builder).
    """
    results = build_pack_evaluation_results(
        pack, agent_name, evidence_by_task_id
    )
    return build_run_report(pack, agent_name, results)


def evaluate_pack_to_json_report(
    pack: BenchmarkPack,
    agent_name: str,
    evidence_by_task_id: dict[str, TaskEvidence],
    path: str | Path,
) -> RunReport:
    """Build a :class:`RunReport` and save it to ``path`` as JSON.

    Returns:
        The :class:`RunReport` that was built and saved.
    """
    report = evaluate_pack_to_report(pack, agent_name, evidence_by_task_id)
    save_run_report(report, path)
    return report


def evaluate_pack_to_markdown_report(
    pack: BenchmarkPack,
    agent_name: str,
    evidence_by_task_id: dict[str, TaskEvidence],
    path: str | Path,
) -> RunReport:
    """Build a :class:`RunReport` and save it to ``path`` as Markdown.

    Returns:
        The :class:`RunReport` that was built and saved.
    """
    report = evaluate_pack_to_report(pack, agent_name, evidence_by_task_id)
    save_run_report_markdown(report, path)
    return report
