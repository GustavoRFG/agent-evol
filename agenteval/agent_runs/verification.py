"""Verify an external agent artifact by re-running its work locally.

Week 5 produced *unverified* :class:`EvaluationResult` objects from external
:class:`AgentRunArtifact` data. Week 6 starts crossing the boundary: this
module copies the task fixture into an isolated workspace, applies the
artifact's diff via the Week 4 controlled patch helper, runs the task's public
and hidden tests via the Week 4 pytest harness, and converts the real test
outcomes into a verified :class:`EvaluationResult`.

The agent's ``claimed_*`` flags are still not trusted as evidence — only real
test outcomes count. The original fixture is never touched; all work happens
in a copy under ``workspace_root``. Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.ingestion import (
    AgentRunIngestionError,
    IngestedAgentRun,
    ingest_agent_run_artifact,
)
from agenteval.core.schemas import (
    AgentRun,
    EvaluationResult,
    TaskSpec,
)
from agenteval.evaluation.result_builder import build_evaluation_result
from agenteval.execution.patch_workspace import (
    PatchApplyError,
    copy_fixture_apply_patch_and_build_evidence,
)
from agenteval.execution.pytest_harness import TestHarnessError
from agenteval.fixtures import TaskFixtureLayout


class AgentRunVerificationError(RuntimeError):
    """Raised when verifying an :class:`IngestedAgentRun` fails.

    Covers task/artifact mismatches, empty diffs, patch-apply failures, and
    pytest harness errors. Subclasses :class:`RuntimeError` because the
    failures here are operational (subprocess / I/O), not value-shape.
    """


def _agent_run_from_artifact(artifact: AgentRunArtifact) -> AgentRun:
    return AgentRun(
        run_id=artifact.run_id,
        agent_name=artifact.agent_name,
        task_id=artifact.task_id,
        transcript_path="",
        final_message=artifact.final_message,
        commands_run=list(artifact.claimed_commands),
    )


def verify_ingested_agent_run(
    task: TaskSpec,
    ingested: IngestedAgentRun,
    layout: TaskFixtureLayout,
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
) -> EvaluationResult:
    """Verify ``ingested`` against ``task`` by patching + testing in a copy.

    The fixture described by ``layout`` is copied into ``workspace_root``, the
    artifact's ``diff_text`` is applied with ``git apply``, and the task's
    public + hidden test buckets are executed against the patched copy. The
    resulting :class:`TaskEvidence` drives the returned
    :class:`EvaluationResult`; agent ``claimed_*`` flags are ignored.

    Args:
        task: The benchmark task spec.
        ingested: The :class:`IngestedAgentRun` produced by
            :func:`ingest_agent_run_artifact`.
        layout: The resolved fixture layout for ``task``.
        workspace_root: Directory under which the per-run workspace copy is
            created. Must be writable.
        timeout_seconds: Subprocess timeout for ``git apply`` and pytest.

    Raises:
        AgentRunVerificationError: For task/artifact mismatches, empty diff
            text, missing preliminary evidence, patch-apply failures, or
            pytest harness failures.
    """
    if not isinstance(ingested, IngestedAgentRun):
        raise AgentRunVerificationError(
            f"ingested must be an IngestedAgentRun, got {type(ingested).__name__}"
        )

    artifact = ingested.artifact
    if task.task_id != artifact.task_id:
        raise AgentRunVerificationError(
            f"task_id mismatch: task.task_id={task.task_id!r} "
            f"but artifact.task_id={artifact.task_id!r} "
            f"(run_id={artifact.run_id!r})"
        )

    diff_text = artifact.diff_text
    if not diff_text or not diff_text.strip():
        raise AgentRunVerificationError(
            f"artifact for run_id={artifact.run_id!r} has empty diff_text; "
            "nothing to verify"
        )

    try:
        evidence = copy_fixture_apply_patch_and_build_evidence(
            task=task,
            layout=layout,
            diff_text=diff_text,
            workspace_root=workspace_root,
            timeout_seconds=timeout_seconds,
            final_message=artifact.final_message,
        )
    except PatchApplyError as exc:
        raise AgentRunVerificationError(
            f"failed to apply patch for run_id={artifact.run_id!r} "
            f"(task_id={task.task_id!r}): {exc}"
        ) from exc
    except TestHarnessError as exc:
        raise AgentRunVerificationError(
            f"pytest harness failed for run_id={artifact.run_id!r} "
            f"(task_id={task.task_id!r}): {exc}"
        ) from exc

    run = _agent_run_from_artifact(artifact)
    return build_evaluation_result(
        task,
        run,
        passed_public_tests=evidence.passed_public_tests,
        passed_hidden_tests=evidence.passed_hidden_tests,
        weaknesses=evidence.weaknesses,
        rationale=evidence.rationale,
        diff_text=evidence.diff_text,
    )


def verify_agent_run_artifact(
    task: TaskSpec,
    artifact: AgentRunArtifact,
    layout: TaskFixtureLayout,
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
) -> EvaluationResult:
    """Ingest ``artifact`` and verify it in one call.

    Thin convenience over :func:`ingest_agent_run_artifact` +
    :func:`verify_ingested_agent_run`. No real agent execution.

    Raises:
        AgentRunVerificationError: For ingestion failures (wrapped with
            run_id context) and any failure raised by
            :func:`verify_ingested_agent_run`.
    """
    try:
        ingested = ingest_agent_run_artifact(artifact)
    except AgentRunIngestionError as exc:
        run_id = getattr(artifact, "run_id", "<unknown>") or "<unknown>"
        raise AgentRunVerificationError(
            f"failed to ingest artifact (run_id={run_id!r}): {exc}"
        ) from exc

    return verify_ingested_agent_run(
        task,
        ingested,
        layout,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "AgentRunVerificationError",
    "verify_agent_run_artifact",
    "verify_ingested_agent_run",
]
