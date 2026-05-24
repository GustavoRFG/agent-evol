"""Verified cross-agent :class:`ComparisonReport` generation from artifacts.

This is the verified counterpart of the Week 5 Day 7 capstone. Week 5 produced
a :class:`ComparisonReport` whose every result was unverified (score 0,
``VERIFY`` weakness for every task). Week 6 Day 4 produces a
:class:`ComparisonReport` over *verified* :class:`RunReport` objects — each
agent's attempted tasks are checked by applying the diff in an isolated
fixture copy and running public + hidden tests, so the ranking can be real.

It performs **no** real agent execution and **no** network calls; the original
fixture is never patched. Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.discovery import load_agent_run_artifacts_from_dir
from agenteval.agent_runs.verified_reporting import (
    VerifiedAgentRunReportingError,
    build_verified_run_reports_from_agent_artifacts,
)
from agenteval.comparison.comparison_report import build_comparison_report
from agenteval.comparison.markdown import render_comparison_report_markdown
from agenteval.core.schemas import BenchmarkPack, ComparisonReport
from agenteval.fixtures import TaskFixtureLayout


class VerifiedAgentRunComparisonError(ValueError):
    """Raised when building a verified :class:`ComparisonReport` fails."""


def build_verified_comparison_report_from_agent_artifacts(
    pack: BenchmarkPack,
    artifacts: list[AgentRunArtifact],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> ComparisonReport:
    """Verify external artifacts and aggregate them into a :class:`ComparisonReport`.

    Composes :func:`build_verified_run_reports_from_agent_artifacts` (Week 6
    Day 3) with :func:`build_comparison_report` (Week 3). Agent ordering is
    inherited from the verified-reporting batch helper (alphabetical by
    ``agent_name``).

    Args:
        pack: Benchmark pack to compare against.
        artifacts: External artifacts across one or more agents.
        layouts_by_task_id: Resolved fixture layouts for the pack's tasks.
        workspace_root: Parent directory under which each agent's verification
            workspace is created.
        timeout_seconds: Subprocess timeout forwarded to verification.
        continue_on_error: Forwarded to verification: ``True`` converts
            per-run failures into unverified results; ``False`` raises.

    Raises:
        VerifiedAgentRunComparisonError: If ``pack`` / ``artifacts`` have the
            wrong type, if no verified reports could be produced, or if
            verified-reporting / comparison construction itself fails.
    """
    if not isinstance(pack, BenchmarkPack):
        raise VerifiedAgentRunComparisonError(
            f"pack must be a BenchmarkPack, got {type(pack).__name__}"
        )
    if not isinstance(artifacts, list):
        raise VerifiedAgentRunComparisonError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    try:
        reports = build_verified_run_reports_from_agent_artifacts(
            pack,
            artifacts,
            layouts_by_task_id,
            workspace_root=workspace_root,
            timeout_seconds=timeout_seconds,
            continue_on_error=continue_on_error,
        )
    except VerifiedAgentRunReportingError as exc:
        raise VerifiedAgentRunComparisonError(
            f"failed to build verified RunReports: {exc}"
        ) from exc

    if not reports:
        raise VerifiedAgentRunComparisonError(
            "no verified RunReports could be built — at least one artifact "
            "is required"
        )

    try:
        return build_comparison_report(reports)
    except Exception as exc:
        raise VerifiedAgentRunComparisonError(
            f"failed to build ComparisonReport from verified RunReports: {exc}"
        ) from exc


def build_verified_comparison_report_from_agent_artifact_dir(
    pack: BenchmarkPack,
    root: str | Path,
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    skip_invalid: bool = False,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> ComparisonReport:
    """Load artifacts under ``root`` and build a verified :class:`ComparisonReport`.

    Thin convenience over :func:`load_agent_run_artifacts_from_dir` +
    :func:`build_verified_comparison_report_from_agent_artifacts`. Still no
    real agent execution.
    """
    artifacts = load_agent_run_artifacts_from_dir(
        root, skip_invalid=skip_invalid
    )
    return build_verified_comparison_report_from_agent_artifacts(
        pack,
        artifacts,
        layouts_by_task_id,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
        continue_on_error=continue_on_error,
    )


def render_verified_comparison_markdown_from_agent_artifacts(
    pack: BenchmarkPack,
    artifacts: list[AgentRunArtifact],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> str:
    """Render the verified :class:`ComparisonReport` as Markdown (no file I/O)."""
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack,
        artifacts,
        layouts_by_task_id,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
        continue_on_error=continue_on_error,
    )
    return render_comparison_report_markdown(comparison)


__all__ = [
    "VerifiedAgentRunComparisonError",
    "build_verified_comparison_report_from_agent_artifact_dir",
    "build_verified_comparison_report_from_agent_artifacts",
    "render_verified_comparison_markdown_from_agent_artifacts",
]
