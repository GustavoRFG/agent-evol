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

import re
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
from agenteval.evaluation.result_builder import (
    build_evaluation_result,
    build_unverified_result,
)
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


_UNSAFE_SUBDIR_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_for_subdir(value: str) -> str:
    """Make ``value`` safe for use as a single filesystem path segment."""
    cleaned = _UNSAFE_SUBDIR_CHARS.sub("_", value).strip("._-")
    return cleaned or "run"


def _per_run_workspace_root(
    workspace_root: Path, index: int, ingested: IngestedAgentRun
) -> Path:
    """Return a unique sibling workspace for one batch entry.

    Each run gets ``workspace_root / "<index>_<sanitized_run_id>"`` so distinct
    runs cannot collide even if they share a ``run_id``. The directory itself
    is created lazily by the patch harness when it copies the fixture.
    """
    run_id = getattr(ingested.artifact, "run_id", "") or "run"
    return workspace_root / f"{index:04d}_{_sanitize_for_subdir(run_id)}"


def _placeholder_run(ingested: IngestedAgentRun) -> AgentRun:
    """Build a placeholder :class:`AgentRun` for an error-result path.

    The artifact's metadata is preserved so the error result still names the
    real agent / task / run. Used only when the framework cannot produce a
    verified result.
    """
    return _agent_run_from_artifact(ingested.artifact)


def _verification_failure_result(
    *,
    task: TaskSpec | None,
    ingested: IngestedAgentRun,
    reason: str,
    fallback_task_id: str | None = None,
) -> EvaluationResult:
    """Build an unverified :class:`EvaluationResult` for a failed batch entry.

    When ``task`` is ``None`` (missing task lookup), a minimal placeholder
    :class:`TaskSpec` is fabricated so the existing builder can still attach
    ``task_id`` / ``run_id``. No real test outcomes are claimed.
    """
    artifact = ingested.artifact
    effective_task = task or TaskSpec(
        task_id=fallback_task_id or artifact.task_id,
        title=f"<unknown task {fallback_task_id or artifact.task_id!r}>",
    )
    run = _placeholder_run(ingested)
    diff_text = artifact.diff_text if artifact.diff_text.strip() else None
    return build_unverified_result(
        effective_task,
        run,
        rationale=f"Verification failed: {reason}",
        diff_text=diff_text,
    )


def verify_ingested_agent_runs(
    tasks_by_id: dict[str, TaskSpec],
    ingested_runs: list[IngestedAgentRun],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> list[EvaluationResult]:
    """Verify multiple ingested external agent runs in sequence.

    Each run is verified inside its own sibling workspace under
    ``workspace_root`` (``"<index>_<run_id>"``), so workspaces never collide.
    Input order is preserved.

    With ``continue_on_error=True`` (the default) per-run failures — missing
    task, missing layout, empty diff, patch-apply error, harness error — are
    converted into unverified :class:`EvaluationResult` objects with a
    descriptive rationale, instead of aborting the batch.

    With ``continue_on_error=False`` the first failure is re-raised as
    :class:`AgentRunVerificationError` with run_id / task_id context.

    Args:
        tasks_by_id: Map from ``task_id`` to the matching :class:`TaskSpec`.
        ingested_runs: Ingested runs to verify, in the desired result order.
        layouts_by_task_id: Map from ``task_id`` to the resolved fixture
            layout for that task.
        workspace_root: Parent directory under which each run's isolated
            workspace is created.
        timeout_seconds: Subprocess timeout forwarded to ``git apply`` and
            pytest for each run.
        continue_on_error: When ``True``, convert per-run failures into
            unverified results. When ``False``, raise.

    Raises:
        AgentRunVerificationError: For invalid argument types, or — when
            ``continue_on_error`` is ``False`` — for the first per-run
            failure (with run_id / task_id context).
    """
    if not isinstance(tasks_by_id, dict):
        raise AgentRunVerificationError(
            f"tasks_by_id must be a dict, got {type(tasks_by_id).__name__}"
        )
    if not isinstance(layouts_by_task_id, dict):
        raise AgentRunVerificationError(
            "layouts_by_task_id must be a dict, "
            f"got {type(layouts_by_task_id).__name__}"
        )
    if not isinstance(ingested_runs, list):
        raise AgentRunVerificationError(
            f"ingested_runs must be a list, got {type(ingested_runs).__name__}"
        )

    workspace_root_path = Path(workspace_root)
    results: list[EvaluationResult] = []

    for index, ingested in enumerate(ingested_runs):
        if not isinstance(ingested, IngestedAgentRun):
            raise AgentRunVerificationError(
                f"ingested_runs[{index}] must be an IngestedAgentRun, "
                f"got {type(ingested).__name__}"
            )

        artifact = ingested.artifact
        task_id = artifact.task_id
        per_run_workspace = _per_run_workspace_root(
            workspace_root_path, index, ingested
        )

        task = tasks_by_id.get(task_id)
        if task is None:
            reason = (
                f"no task found for task_id={task_id!r} "
                f"(run_id={artifact.run_id!r}, index={index})"
            )
            if not continue_on_error:
                raise AgentRunVerificationError(reason)
            results.append(
                _verification_failure_result(
                    task=None,
                    ingested=ingested,
                    reason=reason,
                    fallback_task_id=task_id,
                )
            )
            continue

        layout = layouts_by_task_id.get(task_id)
        if layout is None:
            reason = (
                f"no layout found for task_id={task_id!r} "
                f"(run_id={artifact.run_id!r}, index={index})"
            )
            if not continue_on_error:
                raise AgentRunVerificationError(reason)
            results.append(
                _verification_failure_result(
                    task=task, ingested=ingested, reason=reason
                )
            )
            continue

        try:
            results.append(
                verify_ingested_agent_run(
                    task,
                    ingested,
                    layout,
                    workspace_root=per_run_workspace,
                    timeout_seconds=timeout_seconds,
                )
            )
        except AgentRunVerificationError as exc:
            if not continue_on_error:
                raise AgentRunVerificationError(
                    f"verification failed for run_id={artifact.run_id!r} "
                    f"(task_id={task_id!r}, index={index}): {exc}"
                ) from exc
            results.append(
                _verification_failure_result(
                    task=task, ingested=ingested, reason=str(exc)
                )
            )

    return results


def verify_agent_run_artifacts(
    tasks_by_id: dict[str, TaskSpec],
    artifacts: list[AgentRunArtifact],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> list[EvaluationResult]:
    """Ingest then verify a list of external agent artifacts.

    Thin wrapper over :func:`ingest_agent_run_artifact` and
    :func:`verify_ingested_agent_runs`. Per-artifact ingestion failures are
    converted into unverified results when ``continue_on_error=True`` and
    re-raised as :class:`AgentRunVerificationError` otherwise. No real agent
    execution.

    Raises:
        AgentRunVerificationError: For invalid argument types, or — when
            ``continue_on_error`` is ``False`` — for the first ingestion
            failure (with run_id context), then propagated from the batch
            verifier for any later failure.
    """
    if not isinstance(artifacts, list):
        raise AgentRunVerificationError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    ingested_runs: list[IngestedAgentRun] = []
    # We need to feed verify_ingested_agent_runs with the *same number of*
    # entries as ``artifacts`` so callers can map results back by index. For a
    # malformed artifact we synthesize an IngestedAgentRun whose ``artifact``
    # is the offending input plus a sentinel preliminary evidence; the batch
    # verifier will then fail it through the missing-task/layout path or the
    # empty-diff path. But we cannot rely on that — the artifact itself may be
    # malformed (e.g. empty agent_name). So we ingest defensively here and, on
    # failure, either raise (strict) or emit a synthesized failure result up
    # front (lenient) and skip the entry from ``ingested_runs``.
    pre_results: list[EvaluationResult | None] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, AgentRunArtifact):
            raise AgentRunVerificationError(
                f"artifacts[{index}] must be an AgentRunArtifact, "
                f"got {type(artifact).__name__}"
            )
        try:
            ingested_runs.append(ingest_agent_run_artifact(artifact))
            pre_results.append(None)
        except AgentRunIngestionError as exc:
            run_id = getattr(artifact, "run_id", "<unknown>") or "<unknown>"
            if not continue_on_error:
                raise AgentRunVerificationError(
                    f"failed to ingest artifact at index {index} "
                    f"(run_id={run_id!r}): {exc}"
                ) from exc
            task_id = getattr(artifact, "task_id", "<unknown>") or "<unknown>"
            placeholder_task = tasks_by_id.get(task_id) or TaskSpec(
                task_id=task_id, title=f"<unknown task {task_id!r}>"
            )
            placeholder_run = AgentRun(
                run_id=run_id,
                agent_name=getattr(artifact, "agent_name", "") or "<unknown>",
                task_id=task_id,
            )
            pre_results.append(
                build_unverified_result(
                    placeholder_task,
                    placeholder_run,
                    rationale=f"Verification failed: ingestion error: {exc}",
                )
            )

    verified = verify_ingested_agent_runs(
        tasks_by_id,
        ingested_runs,
        layouts_by_task_id,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
        continue_on_error=continue_on_error,
    )

    # Merge pre-results (ingestion failures) and verified results, preserving
    # the original artifact order.
    merged: list[EvaluationResult] = []
    verified_iter = iter(verified)
    for pre in pre_results:
        if pre is None:
            merged.append(next(verified_iter))
        else:
            merged.append(pre)
    return merged


__all__ = [
    "AgentRunVerificationError",
    "verify_agent_run_artifact",
    "verify_agent_run_artifacts",
    "verify_ingested_agent_run",
    "verify_ingested_agent_runs",
]
