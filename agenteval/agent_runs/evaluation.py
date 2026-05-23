"""Bridge :class:`IngestedAgentRun` objects into :class:`EvaluationResult`.

This module turns ingested external agent artifacts into the framework's
existing :class:`EvaluationResult` shape, so they can flow into the rest of
the evidence-in / report-out pipeline. It performs **no** patch application,
**no** test execution, and **no** network calls. Standard library only.

The boundary is strict: every :class:`EvaluationResult` produced here is
unverified. The agent's ``claimed_*`` test flags are surfaced in the rationale
(via the preliminary evidence) but never used as real pass/fail outcomes —
:class:`WeaknessCode.VERIFY` is always recorded.
"""

from __future__ import annotations

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
    WeaknessCode,
)
from agenteval.evaluation.result_builder import build_evaluation_result


class AgentRunEvaluationError(ValueError):
    """Raised when evaluating an :class:`IngestedAgentRun` fails."""


def _build_agent_run_from_artifact(artifact: AgentRunArtifact) -> AgentRun:
    """Map an :class:`AgentRunArtifact` onto an :class:`AgentRun`.

    ``transcript_path`` is left empty because the artifact carries transcript
    text inline rather than as a sidecar path.
    """
    return AgentRun(
        run_id=artifact.run_id,
        agent_name=artifact.agent_name,
        task_id=artifact.task_id,
        transcript_path="",
        final_message=artifact.final_message,
        commands_run=list(artifact.claimed_commands),
    )


def build_evaluation_result_from_ingested_run(
    task: TaskSpec,
    ingested: IngestedAgentRun,
) -> EvaluationResult:
    """Build an unverified :class:`EvaluationResult` from an ingested artifact.

    The result uses the preliminary evidence produced during ingestion: tests
    are recorded as not passed, :class:`WeaknessCode.VERIFY` is present, and
    the rationale is the deterministic preliminary text (which surfaces any
    agent claims as claims). When the artifact carries a diff, it is attached
    as patch evidence via the existing result builder.

    Args:
        task: The task spec the artifact targets.
        ingested: The :class:`IngestedAgentRun` produced by
            :func:`ingest_agent_run_artifact`.

    Raises:
        AgentRunEvaluationError: If ``task.task_id`` does not match
            ``ingested.artifact.task_id``, or if ``ingested.preliminary_evidence``
            is missing.
    """
    if not isinstance(ingested, IngestedAgentRun):
        raise AgentRunEvaluationError(
            f"ingested must be an IngestedAgentRun, got {type(ingested).__name__}"
        )
    artifact = ingested.artifact
    if task.task_id != artifact.task_id:
        raise AgentRunEvaluationError(
            f"task_id mismatch: task.task_id={task.task_id!r} "
            f"but artifact.task_id={artifact.task_id!r} "
            f"(run_id={artifact.run_id!r})"
        )

    evidence = ingested.preliminary_evidence
    if evidence is None:
        raise AgentRunEvaluationError(
            f"ingested run for {artifact.run_id!r} is missing preliminary "
            "evidence; call ingest_agent_run_artifact first"
        )

    weaknesses = list(evidence.weaknesses)
    if WeaknessCode.VERIFY not in weaknesses:
        # Defensive: preliminary evidence should always carry VERIFY. If a
        # caller passed a hand-built IngestedAgentRun without it, restore the
        # invariant rather than emitting a falsely-verified result.
        weaknesses.append(WeaknessCode.VERIFY)

    run = _build_agent_run_from_artifact(artifact)

    return build_evaluation_result(
        task,
        run,
        passed_public_tests=False,
        passed_hidden_tests=False,
        weaknesses=weaknesses,
        rationale=evidence.rationale,
        diff_text=evidence.diff_text,
    )


def build_evaluation_results_from_ingested_runs(
    tasks_by_id: dict[str, TaskSpec],
    ingested_runs: list[IngestedAgentRun],
) -> list[EvaluationResult]:
    """Build :class:`EvaluationResult` objects for many ingested runs.

    Input order is preserved. Each run's task is looked up by its artifact's
    ``task_id``.

    Raises:
        AgentRunEvaluationError: If ``tasks_by_id`` is not a dict, if
            ``ingested_runs`` is not a list, or if any artifact references a
            task that is not present in ``tasks_by_id``.
    """
    if not isinstance(tasks_by_id, dict):
        raise AgentRunEvaluationError(
            f"tasks_by_id must be a dict, got {type(tasks_by_id).__name__}"
        )
    if not isinstance(ingested_runs, list):
        raise AgentRunEvaluationError(
            f"ingested_runs must be a list, got {type(ingested_runs).__name__}"
        )

    results: list[EvaluationResult] = []
    for index, ingested in enumerate(ingested_runs):
        if not isinstance(ingested, IngestedAgentRun):
            raise AgentRunEvaluationError(
                f"ingested_runs[{index}] must be an IngestedAgentRun, "
                f"got {type(ingested).__name__}"
            )
        task_id = ingested.artifact.task_id
        task = tasks_by_id.get(task_id)
        if task is None:
            raise AgentRunEvaluationError(
                f"no task found for task_id={task_id!r} "
                f"(run_id={ingested.artifact.run_id!r}, index={index})"
            )
        results.append(build_evaluation_result_from_ingested_run(task, ingested))
    return results


def build_evaluation_results_from_agent_artifacts(
    tasks_by_id: dict[str, TaskSpec],
    artifacts: list[AgentRunArtifact],
) -> list[EvaluationResult]:
    """Ingest artifacts and build :class:`EvaluationResult` objects in one step.

    Order is preserved. Still no patch application and no test execution — the
    results remain unverified.

    Raises:
        AgentRunEvaluationError: For invalid input types, ingestion failures,
            or missing tasks.
    """
    if not isinstance(artifacts, list):
        raise AgentRunEvaluationError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    ingested_runs: list[IngestedAgentRun] = []
    for index, artifact in enumerate(artifacts):
        try:
            ingested_runs.append(ingest_agent_run_artifact(artifact))
        except AgentRunIngestionError as exc:
            run_id = getattr(artifact, "run_id", "<unknown>") or "<unknown>"
            raise AgentRunEvaluationError(
                f"failed to ingest artifact at index {index} "
                f"(run_id={run_id!r}): {exc}"
            ) from exc
    return build_evaluation_results_from_ingested_runs(tasks_by_id, ingested_runs)


__all__ = [
    "AgentRunEvaluationError",
    "build_evaluation_result_from_ingested_run",
    "build_evaluation_results_from_agent_artifacts",
    "build_evaluation_results_from_ingested_runs",
]
