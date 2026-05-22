"""Batch assembly of evidence-backed :class:`EvaluationResult` objects.

This module assembles one :class:`EvaluationResult` per task in a
:class:`BenchmarkPack`, using per-task evidence the caller already has. Tasks
with no evidence become unverified (``VERIFY``) results.

It performs **no** agent execution, patch application, or test execution — it
only assembles results from inputs that already exist. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from agenteval.core.schemas import (
    AgentRun,
    BenchmarkPack,
    EvaluationResult,
    TaskSpec,
    WeaknessCode,
)
from agenteval.evaluation.result_builder import (
    build_evaluation_result,
    build_unverified_result,
)
from agenteval.runs.scaffold import create_placeholder_run


class BatchEvaluationError(ValueError):
    """Raised when batch evaluation inputs are inconsistent.

    Subclasses :class:`ValueError` so callers may catch either type.
    """


@dataclass
class TaskEvidence:
    """Per-task evidence used to build one :class:`EvaluationResult`.

    Every field is optional. An all-default ``TaskEvidence`` describes a task
    with no passing tests, no recorded weaknesses, and no patch.
    """

    passed_public_tests: bool = False
    passed_hidden_tests: bool = False
    weaknesses: list[WeaknessCode] = field(default_factory=list)
    rationale: str = ""
    diff_text: str | None = None
    final_message: str = ""


def build_run_for_task(
    task: TaskSpec,
    agent_name: str,
    final_message: str = "",
) -> AgentRun:
    """Build a deterministic placeholder :class:`AgentRun` for a task.

    Reuses :func:`create_placeholder_run`. When a non-empty ``final_message``
    is supplied it is carried onto the returned run (the placeholder run is
    copied, not mutated); otherwise the placeholder's own message is kept.
    """
    run = create_placeholder_run(task, agent_name)
    if final_message:
        run = replace(run, final_message=final_message)
    return run


def build_pack_evaluation_results(
    pack: BenchmarkPack,
    agent_name: str,
    evidence_by_task_id: dict[str, TaskEvidence],
) -> list[EvaluationResult]:
    """Assemble one :class:`EvaluationResult` per task in a benchmark pack.

    For each task in ``pack.tasks`` (in order): a deterministic placeholder
    :class:`AgentRun` is created; if evidence exists for the task's id it is
    used to build an evidence-backed result, otherwise an unverified
    (``VERIFY``) result is produced. Input evidence objects are not mutated.

    Args:
        pack: The benchmark pack whose tasks should be evaluated.
        agent_name: Name of the agent the results are attributed to.
        evidence_by_task_id: Map from ``task_id`` to its :class:`TaskEvidence`.
            Tasks absent from this map become unverified results.

    Returns:
        One :class:`EvaluationResult` per task, in ``pack.tasks`` order.

    Raises:
        BatchEvaluationError: If ``evidence_by_task_id`` contains a ``task_id``
            that is not present in the pack.
    """
    pack_task_ids = {task.task_id for task in pack.tasks}
    unknown = sorted(set(evidence_by_task_id) - pack_task_ids)
    if unknown:
        raise BatchEvaluationError(
            f"evidence_by_task_id contains task ID(s) not in pack "
            f"'{pack.name}': {', '.join(unknown)}"
        )

    results: list[EvaluationResult] = []
    for task in pack.tasks:
        evidence = evidence_by_task_id.get(task.task_id)
        run = build_run_for_task(
            task,
            agent_name,
            final_message=evidence.final_message if evidence else "",
        )

        if evidence is None:
            results.append(build_unverified_result(task, run))
        else:
            results.append(
                build_evaluation_result(
                    task,
                    run,
                    passed_public_tests=evidence.passed_public_tests,
                    passed_hidden_tests=evidence.passed_hidden_tests,
                    weaknesses=evidence.weaknesses,
                    rationale=evidence.rationale,
                    diff_text=evidence.diff_text,
                )
            )
    return results
