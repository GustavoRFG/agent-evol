"""One-call verified comparison + claim analysis Markdown for demos.

The Week 6 capstone wires the verified :class:`ComparisonReport` and the
:class:`ClaimAnalysisReport` together by hand, including the small but
load-bearing detail of filtering out unattempted-task placeholder results
before claim analysis. This module makes that wiring a single call so demo
code, examples, and interview walk-throughs do not have to re-derive it.

It performs **no** real agent execution and **no** network calls. Patch
application and pytest execution happen only via the existing Week 6
verified-comparison helper. Standard library only.

Boundary recap: this layer does not change scoring, comparison ranking, or
:class:`EvaluationResult.weaknesses`. Claim analysis is informational —
that's stated in the rendered Markdown so demo viewers see it inline.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.claim_report import (
    ClaimAnalysisReport,
    ClaimReportError,
    build_claim_analysis_report_from_artifacts_and_results,
    render_claim_analysis_report_markdown,
)
from agenteval.agent_runs.verified_comparison import (
    VerifiedAgentRunComparisonError,
    build_verified_comparison_report_from_agent_artifacts,
)
from agenteval.comparison.markdown import render_comparison_report_markdown
from agenteval.core.schemas import (
    BenchmarkPack,
    ComparisonReport,
    EvaluationResult,
)
from agenteval.fixtures import TaskFixtureLayout

_CLAIM_RELIABILITY_NOTE = (
    "_Claim reliability is informational only — it does not change "
    "EvaluationResult scores or ComparisonReport ranking by default._"
)


class VerifiedMarkdownError(ValueError):
    """Raised when integrated verified-comparison + claim Markdown cannot be built."""


def extract_attempted_results_for_claim_analysis(
    comparison: ComparisonReport,
    artifacts: list[AgentRunArtifact],
) -> list[EvaluationResult]:
    """Flatten ``comparison`` results, keeping only those with a real artifact.

    The Week 5/6 verified-reporting pipeline fills unattempted pack tasks
    with placeholder :class:`EvaluationResult` objects whose ``run_id``
    follows the ``"<agent>:<task>:placeholder"`` convention. Those run_ids
    do not match any :class:`AgentRunArtifact`, so feeding them straight
    into :func:`build_claim_analysis_report_from_artifacts_and_results`
    raises ``"no artifact found for run_id=…"``. This helper applies the
    correct filter once.

    Order is preserved: outer iteration follows ``comparison.reports`` (the
    per-agent ordering chosen by the verified-comparison builder), inner
    iteration follows each report's ``results`` (pack-task order).

    Raises:
        VerifiedMarkdownError: For wrong argument types.
    """
    if not isinstance(comparison, ComparisonReport):
        raise VerifiedMarkdownError(
            f"comparison must be a ComparisonReport, got {type(comparison).__name__}"
        )
    if not isinstance(artifacts, list):
        raise VerifiedMarkdownError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    artifact_run_ids: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, AgentRunArtifact):
            raise VerifiedMarkdownError(
                f"artifacts[{index}] must be an AgentRunArtifact, "
                f"got {type(artifact).__name__}"
            )
        artifact_run_ids.add(artifact.run_id)

    return [
        result
        for report in comparison.reports
        for result in report.results
        if result.run_id in artifact_run_ids
    ]


def build_verified_comparison_and_claim_report(
    pack: BenchmarkPack,
    artifacts: list[AgentRunArtifact],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> tuple[ComparisonReport, ClaimAnalysisReport]:
    """Build the verified :class:`ComparisonReport` and the matching :class:`ClaimAnalysisReport`.

    Internally:

    1. Calls Week 6 Day 4's verified-comparison builder.
    2. Filters the comparison's flattened results to those with a matching
       artifact ``run_id`` via
       :func:`extract_attempted_results_for_claim_analysis`.
    3. Feeds artifacts + filtered results into the Week 6 Day 6
       :class:`ClaimAnalysisReport` builder.

    Inputs are not mutated. No files are written.

    Raises:
        VerifiedMarkdownError: For wrong argument types or any failure
            propagated from the verified-comparison or claim-analysis
            layers (the original exception is preserved as ``__cause__``).
    """
    if not isinstance(artifacts, list):
        raise VerifiedMarkdownError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    try:
        comparison = build_verified_comparison_report_from_agent_artifacts(
            pack,
            artifacts,
            layouts_by_task_id,
            workspace_root=workspace_root,
            timeout_seconds=timeout_seconds,
            continue_on_error=continue_on_error,
        )
    except VerifiedAgentRunComparisonError as exc:
        raise VerifiedMarkdownError(
            f"failed to build verified ComparisonReport: {exc}"
        ) from exc

    attempted_results = extract_attempted_results_for_claim_analysis(
        comparison, artifacts
    )

    try:
        claim_report = build_claim_analysis_report_from_artifacts_and_results(
            artifacts, attempted_results
        )
    except ClaimReportError as exc:
        raise VerifiedMarkdownError(
            f"failed to build ClaimAnalysisReport: {exc}"
        ) from exc

    return comparison, claim_report


def render_verified_comparison_with_claims_markdown(
    comparison: ComparisonReport,
    claim_report: ClaimAnalysisReport,
) -> str:
    """Concatenate verified comparison and claim analysis Markdown sections.

    The output has the comparison Markdown first (so the verified ranking is
    the most visible thing), then the claim analysis, then a one-line note
    that claim reliability is informational.

    Raises:
        VerifiedMarkdownError: For wrong argument types.
    """
    if not isinstance(comparison, ComparisonReport):
        raise VerifiedMarkdownError(
            f"comparison must be a ComparisonReport, got {type(comparison).__name__}"
        )
    if not isinstance(claim_report, ClaimAnalysisReport):
        raise VerifiedMarkdownError(
            "claim_report must be a ClaimAnalysisReport, "
            f"got {type(claim_report).__name__}"
        )

    comparison_md = render_comparison_report_markdown(comparison)
    claim_md = render_claim_analysis_report_markdown(claim_report)
    return (
        comparison_md.rstrip()
        + "\n\n---\n\n"
        + claim_md.rstrip()
        + "\n\n"
        + _CLAIM_RELIABILITY_NOTE
        + "\n"
    )


def build_and_render_verified_comparison_with_claims_markdown(
    pack: BenchmarkPack,
    artifacts: list[AgentRunArtifact],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> str:
    """One-call demo helper: external artifacts -> combined Markdown.

    Thin composition over :func:`build_verified_comparison_and_claim_report`
    + :func:`render_verified_comparison_with_claims_markdown`. No file I/O.
    """
    comparison, claim_report = build_verified_comparison_and_claim_report(
        pack,
        artifacts,
        layouts_by_task_id,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
        continue_on_error=continue_on_error,
    )
    return render_verified_comparison_with_claims_markdown(
        comparison, claim_report
    )


__all__ = [
    "VerifiedMarkdownError",
    "build_and_render_verified_comparison_with_claims_markdown",
    "build_verified_comparison_and_claim_report",
    "extract_attempted_results_for_claim_analysis",
    "render_verified_comparison_with_claims_markdown",
]
