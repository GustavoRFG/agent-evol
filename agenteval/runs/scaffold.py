"""Deterministic placeholder evaluation pipeline for AgentEval Forge.

This scaffold wires together :class:`BenchmarkPack`, :class:`TaskSpec`,
:class:`AgentRun`, :class:`EvaluationResult`, and :func:`compute_basic_score` to
prove the internal data flow end to end.

It deliberately performs **no real agent execution**: no Claude Code, Codex,
ForgeAgent, or DGM is invoked, and there are no network calls, external APIs,
subprocesses, or shell commands. Every run and result here is a deterministic
placeholder. A real runner will replace this scaffold in a later milestone.
"""

from __future__ import annotations

from agenteval.core.schemas import (
    AgentRun,
    BenchmarkPack,
    EvaluationResult,
    TaskSpec,
    WeaknessCode,
)
from agenteval.core.scoring import compute_basic_score

PLACEHOLDER_FINAL_MESSAGE = (
    "Placeholder run: no agent was executed and no commands were run. "
    "This AgentRun exists only to exercise the AgentEval Forge data flow."
)

PLACEHOLDER_RATIONALE = (
    "Placeholder evaluation: no real agent execution and no tests were run. "
    "Public and hidden tests are recorded as not passed, and a VERIFY weakness "
    "is recorded because nothing was actually verified."
)


def create_placeholder_run(task: TaskSpec, agent_name: str) -> AgentRun:
    """Create a deterministic placeholder :class:`AgentRun` for a task.

    No agent is executed. The returned run is fully determined by
    ``agent_name`` and ``task.task_id``, so calling this twice with the same
    arguments yields an identical ``run_id``.

    Args:
        task: The task the placeholder run is associated with.
        agent_name: Name of the agent this run stands in for.

    Returns:
        An :class:`AgentRun` with a deterministic ``run_id`` and no recorded
        execution (empty transcript path and empty command list).
    """
    return AgentRun(
        run_id=f"{agent_name}:{task.task_id}:placeholder",
        agent_name=agent_name,
        task_id=task.task_id,
        transcript_path="",
        final_message=PLACEHOLDER_FINAL_MESSAGE,
        commands_run=[],
    )


def evaluate_placeholder_run(task: TaskSpec, run: AgentRun) -> EvaluationResult:
    """Produce a deterministic placeholder :class:`EvaluationResult`.

    This is **not** a real evaluation: no tests are run. Public and hidden tests
    are recorded as not passed, a :attr:`WeaknessCode.VERIFY` weakness is
    recorded, and the score is computed by :func:`compute_basic_score` from
    those facts (no passed tests + one weakness, clamped to ``0.0``).

    Args:
        task: The task being "evaluated".
        run: The placeholder run produced by :func:`create_placeholder_run`.

    Returns:
        An :class:`EvaluationResult` reflecting that nothing was verified.
    """
    passed_public_tests = False
    passed_hidden_tests = False
    weaknesses = [WeaknessCode.VERIFY]

    score = compute_basic_score(
        passed_public_tests,
        passed_hidden_tests,
        weaknesses,
    )

    return EvaluationResult(
        task_id=task.task_id,
        run_id=run.run_id,
        score=score,
        passed_public_tests=passed_public_tests,
        passed_hidden_tests=passed_hidden_tests,
        weaknesses=list(weaknesses),
        rationale=PLACEHOLDER_RATIONALE,
    )


def evaluate_pack_placeholder(
    pack: BenchmarkPack, agent_name: str
) -> list[EvaluationResult]:
    """Run the placeholder pipeline across every task in a benchmark pack.

    For each task in ``pack.tasks`` a placeholder :class:`AgentRun` and
    :class:`EvaluationResult` are created. Tasks are processed in
    ``pack.tasks`` order, so the returned list is deterministic.

    Args:
        pack: The benchmark pack whose tasks should be processed.
        agent_name: Name of the agent the placeholder runs stand in for.

    Returns:
        One :class:`EvaluationResult` per task, in ``pack.tasks`` order.
    """
    results: list[EvaluationResult] = []
    for task in pack.tasks:
        run = create_placeholder_run(task, agent_name)
        results.append(evaluate_placeholder_run(task, run))
    return results
