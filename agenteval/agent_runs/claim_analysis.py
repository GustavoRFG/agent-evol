"""Compare external agent claims with verified evaluation outcomes.

External artifacts may carry ``claimed_public_tests_passed`` /
``claimed_hidden_tests_passed`` — what the agent *says* happened. This module
compares those claims with the verified outcomes produced by AgentEval Forge
(:class:`EvaluationResult`), so callers can surface overclaiming, false
success, and quiet mismatches.

It performs **no** agent execution, **no** patch application, and **no** test
execution; it only inspects already-built artifacts and results. Standard
library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.core.schemas import EvaluationResult


class ClaimAnalysisError(ValueError):
    """Raised when claim-vs-verified analysis cannot be performed."""


@dataclass
class ClaimVerificationSummary:
    """One agent's claim versus AgentEval Forge's verified outcome for one task.

    Per-bucket match fields are tri-state:

    * ``True``  — the agent made an explicit claim and it matches the verified
      outcome;
    * ``False`` — the agent made an explicit claim and it disagrees with the
      verified outcome;
    * ``None``  — the agent made no claim for that bucket, so there is
      nothing to compare.
    """

    agent_name: str
    task_id: str
    run_id: str
    claimed_public_tests_passed: bool | None
    claimed_hidden_tests_passed: bool | None
    verified_public_tests_passed: bool
    verified_hidden_tests_passed: bool
    public_claim_matches: bool | None
    hidden_claim_matches: bool | None
    has_any_claim: bool
    has_mismatch: bool
    mismatch_labels: list[str] = field(default_factory=list)
    rationale: str = ""


def _match_state(claim: bool | None, verified: bool) -> bool | None:
    if claim is None:
        return None
    return claim is verified


def _rationale(
    *,
    has_any_claim: bool,
    public_match: bool | None,
    hidden_match: bool | None,
    mismatch_labels: list[str],
) -> str:
    if not has_any_claim:
        return (
            "No claims were provided by the agent; nothing to compare against "
            "verified outcomes."
        )
    if not mismatch_labels:
        return "All agent claims match verified outcomes."
    parts = []
    if public_match is False:
        parts.append("public claim differs from verified outcome")
    if hidden_match is False:
        parts.append("hidden claim differs from verified outcome")
    return "Agent claims differ from verified outcomes: " + "; ".join(parts) + "."


def build_claim_verification_summary(
    artifact: AgentRunArtifact,
    result: EvaluationResult,
) -> ClaimVerificationSummary:
    """Compare one artifact's claims with one verified :class:`EvaluationResult`.

    Inputs are inspected only — neither is mutated.

    Raises:
        ClaimAnalysisError: For non-matching ``task_id`` / ``run_id``, or for
            inputs of the wrong type.
    """
    if not isinstance(artifact, AgentRunArtifact):
        raise ClaimAnalysisError(
            f"artifact must be an AgentRunArtifact, got {type(artifact).__name__}"
        )
    if not isinstance(result, EvaluationResult):
        raise ClaimAnalysisError(
            f"result must be an EvaluationResult, got {type(result).__name__}"
        )
    if artifact.task_id != result.task_id:
        raise ClaimAnalysisError(
            f"task_id mismatch: artifact.task_id={artifact.task_id!r} "
            f"but result.task_id={result.task_id!r} "
            f"(run_id={artifact.run_id!r})"
        )
    if artifact.run_id != result.run_id:
        raise ClaimAnalysisError(
            f"run_id mismatch: artifact.run_id={artifact.run_id!r} "
            f"but result.run_id={result.run_id!r}"
        )

    claimed_public = artifact.claimed_public_tests_passed
    claimed_hidden = artifact.claimed_hidden_tests_passed
    verified_public = result.passed_public_tests
    verified_hidden = result.passed_hidden_tests

    public_match = _match_state(claimed_public, verified_public)
    hidden_match = _match_state(claimed_hidden, verified_hidden)

    mismatch_labels: list[str] = []
    if public_match is False:
        mismatch_labels.append("public")
    if hidden_match is False:
        mismatch_labels.append("hidden")

    has_any_claim = claimed_public is not None or claimed_hidden is not None
    has_mismatch = bool(mismatch_labels)

    return ClaimVerificationSummary(
        agent_name=artifact.agent_name,
        task_id=artifact.task_id,
        run_id=artifact.run_id,
        claimed_public_tests_passed=claimed_public,
        claimed_hidden_tests_passed=claimed_hidden,
        verified_public_tests_passed=verified_public,
        verified_hidden_tests_passed=verified_hidden,
        public_claim_matches=public_match,
        hidden_claim_matches=hidden_match,
        has_any_claim=has_any_claim,
        has_mismatch=has_mismatch,
        mismatch_labels=mismatch_labels,
        rationale=_rationale(
            has_any_claim=has_any_claim,
            public_match=public_match,
            hidden_match=hidden_match,
            mismatch_labels=mismatch_labels,
        ),
    )


def build_claim_verification_summaries(
    artifacts_by_run_id: dict[str, AgentRunArtifact],
    results: list[EvaluationResult],
) -> list[ClaimVerificationSummary]:
    """Build one :class:`ClaimVerificationSummary` per :class:`EvaluationResult`.

    The input ``results`` order is preserved on output. Each result is paired
    with the artifact whose ``run_id`` matches ``result.run_id``.

    Raises:
        ClaimAnalysisError: For invalid argument types or when no artifact
            exists for a given result's ``run_id``.
    """
    if not isinstance(artifacts_by_run_id, dict):
        raise ClaimAnalysisError(
            "artifacts_by_run_id must be a dict, "
            f"got {type(artifacts_by_run_id).__name__}"
        )
    if not isinstance(results, list):
        raise ClaimAnalysisError(
            f"results must be a list, got {type(results).__name__}"
        )

    summaries: list[ClaimVerificationSummary] = []
    for index, result in enumerate(results):
        if not isinstance(result, EvaluationResult):
            raise ClaimAnalysisError(
                f"results[{index}] must be an EvaluationResult, "
                f"got {type(result).__name__}"
            )
        artifact = artifacts_by_run_id.get(result.run_id)
        if artifact is None:
            raise ClaimAnalysisError(
                f"no artifact found for run_id={result.run_id!r} "
                f"(task_id={result.task_id!r}, index={index})"
            )
        summaries.append(build_claim_verification_summary(artifact, result))
    return summaries


def _format_claim(value: bool | None) -> str:
    if value is None:
        return "—"
    return "pass" if value else "fail"


def _format_match(value: bool | None) -> str:
    if value is None:
        return "—"
    return "match" if value else "MISMATCH"


def render_claim_verification_summary_markdown(
    summaries: list[ClaimVerificationSummary],
) -> str:
    """Render the per-row claim-vs-verified table plus a mismatch section.

    Empty input produces a short notice. No file I/O.
    """
    if not isinstance(summaries, list):
        raise ClaimAnalysisError(
            f"summaries must be a list, got {type(summaries).__name__}"
        )

    lines: list[str] = ["# Agent claims vs verified outcomes", ""]
    if not summaries:
        lines.append("_No summaries provided._")
        return "\n".join(lines) + "\n"

    lines.append(
        "| Agent | Task | Run | Claimed public | Verified public | "
        "Claimed hidden | Verified hidden | Match |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    for s in summaries:
        match_cells = []
        if s.public_claim_matches is not None:
            match_cells.append(f"public:{_format_match(s.public_claim_matches)}")
        if s.hidden_claim_matches is not None:
            match_cells.append(f"hidden:{_format_match(s.hidden_claim_matches)}")
        match_cell = ", ".join(match_cells) if match_cells else "no claim"
        lines.append(
            "| "
            + " | ".join(
                [
                    s.agent_name,
                    s.task_id,
                    s.run_id,
                    _format_claim(s.claimed_public_tests_passed),
                    "pass" if s.verified_public_tests_passed else "fail",
                    _format_claim(s.claimed_hidden_tests_passed),
                    "pass" if s.verified_hidden_tests_passed else "fail",
                    match_cell,
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Mismatches")
    lines.append("")
    mismatches = [s for s in summaries if s.has_mismatch]
    if not mismatches:
        lines.append("_No mismatches between agent claims and verified outcomes._")
    else:
        for s in mismatches:
            buckets = ", ".join(s.mismatch_labels)
            lines.append(
                f"- **{s.agent_name}** / {s.task_id} / `{s.run_id}` — "
                f"mismatch in: {buckets}. {s.rationale}"
            )
    return "\n".join(lines) + "\n"


__all__ = [
    "ClaimAnalysisError",
    "ClaimVerificationSummary",
    "build_claim_verification_summaries",
    "build_claim_verification_summary",
    "render_claim_verification_summary_markdown",
]
