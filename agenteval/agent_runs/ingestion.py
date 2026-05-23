"""Bridge external :class:`AgentRunArtifact` objects into preliminary evidence.

External agents produce artifacts; this module turns those artifacts into the
internal shapes (:class:`PatchSummary`, :class:`TaskEvidence`) that the rest of
AgentEval Forge already understands. It performs no patch application, no test
execution, no scoring, and no network calls. Standard library only.

Crucially, this bridge does **not** trust the agent's own ``claimed_*`` test
flags as if they were verified outcomes. Until AgentEval Forge actually runs
the task's tests against the patched workspace, the resulting
:class:`TaskEvidence` is marked unverified (:class:`WeaknessCode.VERIFY`).
"""

from __future__ import annotations

from dataclasses import dataclass

from agenteval.agent_runs.artifacts import (
    AgentRunArtifact,
    AgentRunArtifactError,
    validate_agent_run_artifact,
)
from agenteval.core.schemas import PatchSummary, WeaknessCode
from agenteval.evaluation.batch_builder import TaskEvidence
from agenteval.patches.diff_summary import parse_unified_diff

_PRELIMINARY_RATIONALE_PREFIX = (
    "Preliminary evidence from external agent artifact: AgentEval Forge has "
    "not executed any tests, so public and hidden test outcomes are recorded "
    "as not passed and a VERIFY weakness is added."
)


class AgentRunIngestionError(ValueError):
    """Raised when ingesting an :class:`AgentRunArtifact` fails."""


@dataclass
class IngestedAgentRun:
    """Result of ingesting one :class:`AgentRunArtifact`.

    The original artifact is preserved verbatim. ``patch_summary`` is ``None``
    when the artifact carries no diff text. ``preliminary_evidence`` is always
    a :class:`TaskEvidence` marked unverified — it captures what is knowable
    without execution and must not be mistaken for a real evaluation.
    """

    artifact: AgentRunArtifact
    patch_summary: PatchSummary | None = None
    preliminary_evidence: TaskEvidence | None = None


def parse_patch_summary_from_artifact(
    artifact: AgentRunArtifact,
) -> PatchSummary | None:
    """Parse the artifact's ``diff_text`` into a :class:`PatchSummary`.

    Returns ``None`` when ``diff_text`` is empty or whitespace only. Wraps any
    unexpected parser failure in :class:`AgentRunIngestionError` with context.
    The artifact is not mutated.
    """
    diff_text = artifact.diff_text
    if not diff_text or not diff_text.strip():
        return None
    try:
        return parse_unified_diff(diff_text)
    except Exception as exc:  # defensive: existing parser is permissive
        raise AgentRunIngestionError(
            f"failed to parse diff_text for run {artifact.run_id!r}: {exc}"
        ) from exc


def _claim_fragment(label: str, value: bool | None) -> str | None:
    if value is None:
        return None
    word = "passed" if value else "failed"
    return f"agent claimed {label} {word}"


def build_preliminary_task_evidence_from_artifact(
    artifact: AgentRunArtifact,
) -> TaskEvidence:
    """Build a preliminary, unverified :class:`TaskEvidence` from an artifact.

    Tests are recorded as not passed and a :class:`WeaknessCode.VERIFY`
    weakness is added, regardless of what the agent claimed. Any non-``None``
    ``claimed_*`` flags are surfaced in the rationale as agent claims only.

    The artifact's ``diff_text`` and ``final_message`` are forwarded onto the
    returned :class:`TaskEvidence` so downstream evidence consumers can still
    parse the patch or display the agent's final answer. The artifact itself
    is not mutated.
    """
    rationale_parts: list[str] = [_PRELIMINARY_RATIONALE_PREFIX]

    claims = [
        _claim_fragment("public tests", artifact.claimed_public_tests_passed),
        _claim_fragment("hidden tests", artifact.claimed_hidden_tests_passed),
    ]
    claim_text = "; ".join(c for c in claims if c)
    if claim_text:
        rationale_parts.append(
            f"Agent self-report (unverified by AgentEval Forge): {claim_text}."
        )

    rationale = " ".join(rationale_parts)
    diff_text = artifact.diff_text if artifact.diff_text else None

    return TaskEvidence(
        passed_public_tests=False,
        passed_hidden_tests=False,
        weaknesses=[WeaknessCode.VERIFY],
        rationale=rationale,
        diff_text=diff_text,
        final_message=artifact.final_message,
    )


def ingest_agent_run_artifact(artifact: AgentRunArtifact) -> IngestedAgentRun:
    """Validate ``artifact`` and build an :class:`IngestedAgentRun` from it.

    Raises:
        AgentRunIngestionError: If the artifact fails validation or its diff
            text cannot be parsed.
    """
    try:
        validate_agent_run_artifact(artifact)
    except AgentRunArtifactError as exc:
        raise AgentRunIngestionError(
            f"invalid agent run artifact: {exc}"
        ) from exc

    patch_summary = parse_patch_summary_from_artifact(artifact)
    preliminary_evidence = build_preliminary_task_evidence_from_artifact(artifact)

    return IngestedAgentRun(
        artifact=artifact,
        patch_summary=patch_summary,
        preliminary_evidence=preliminary_evidence,
    )


def ingest_agent_run_artifacts(
    artifacts: list[AgentRunArtifact],
) -> list[IngestedAgentRun]:
    """Ingest a list of artifacts, preserving input order.

    Raises:
        AgentRunIngestionError: For the first artifact that fails ingestion,
            with the offending ``run_id`` included in the message.
    """
    if not isinstance(artifacts, list):
        raise AgentRunIngestionError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    ingested: list[IngestedAgentRun] = []
    for index, artifact in enumerate(artifacts):
        try:
            ingested.append(ingest_agent_run_artifact(artifact))
        except AgentRunIngestionError as exc:
            run_id = getattr(artifact, "run_id", "<unknown>") or "<unknown>"
            raise AgentRunIngestionError(
                f"failed to ingest artifact at index {index} "
                f"(run_id={run_id!r}): {exc}"
            ) from exc
    return ingested


__all__ = [
    "AgentRunIngestionError",
    "IngestedAgentRun",
    "build_preliminary_task_evidence_from_artifact",
    "ingest_agent_run_artifact",
    "ingest_agent_run_artifacts",
    "parse_patch_summary_from_artifact",
]
