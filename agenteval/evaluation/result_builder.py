"""Build complete :class:`EvaluationResult` objects from evidence inputs.

This module assembles an :class:`EvaluationResult` from already-known evidence:
test outcomes, recorded weaknesses, a rationale, and optionally raw diff text.
It computes the score with :func:`compute_basic_score` and attaches patch
evidence via :func:`attach_patch_to_result`.

It performs **no** agent execution, patch application, or test execution — it
only assembles results from inputs the caller already has. Standard library
only.
"""

from __future__ import annotations

from agenteval.core.schemas import (
    AgentRun,
    EvaluationResult,
    TaskSpec,
    WeaknessCode,
)
from agenteval.core.scoring import compute_basic_score
from agenteval.evaluation.patch_evidence import attach_patch_to_result


def build_evaluation_result(
    task: TaskSpec,
    run: AgentRun,
    *,
    passed_public_tests: bool,
    passed_hidden_tests: bool,
    weaknesses: list[WeaknessCode] | None = None,
    rationale: str = "",
    diff_text: str | None = None,
) -> EvaluationResult:
    """Assemble a complete :class:`EvaluationResult` from structured evidence.

    The score is computed by :func:`compute_basic_score` from the test outcomes
    and recorded weaknesses. ``task.task_id`` and ``run.run_id`` identify the
    result. When ``diff_text`` is provided, patch evidence is parsed and
    attached; when it is ``None``, ``patch_summary`` is left as ``None``.

    Inputs are not mutated — the recorded weaknesses are stored as a copy.

    Args:
        task: The task that was evaluated.
        run: The agent run being evaluated.
        passed_public_tests: Whether the public test suite passed.
        passed_hidden_tests: Whether the hidden test suite passed.
        weaknesses: Recorded weaknesses; ``None`` is treated as an empty list.
        rationale: Human-readable explanation of the outcome.
        diff_text: Optional raw unified diff to attach as patch evidence.

    Returns:
        A complete :class:`EvaluationResult`.
    """
    weakness_list = list(weaknesses) if weaknesses is not None else []

    score = compute_basic_score(
        passed_public_tests,
        passed_hidden_tests,
        weakness_list,
    )

    result = EvaluationResult(
        task_id=task.task_id,
        run_id=run.run_id,
        score=score,
        passed_public_tests=passed_public_tests,
        passed_hidden_tests=passed_hidden_tests,
        weaknesses=weakness_list,
        rationale=rationale,
    )

    if diff_text is not None:
        result = attach_patch_to_result(result, diff_text)

    return result


def build_unverified_result(
    task: TaskSpec,
    run: AgentRun,
    *,
    rationale: str = "No verification evidence was provided.",
    diff_text: str | None = None,
) -> EvaluationResult:
    """Build an :class:`EvaluationResult` for a run with no verification.

    Both test buckets are recorded as not passed and a
    :attr:`WeaknessCode.VERIFY` weakness is recorded, so the score (via
    :func:`compute_basic_score`) is ``0.0``. Optional ``diff_text`` is still
    attached as patch evidence when provided.

    Args:
        task: The task that was evaluated.
        run: The agent run being evaluated.
        rationale: Human-readable explanation; defaults to a no-evidence note.
        diff_text: Optional raw unified diff to attach as patch evidence.

    Returns:
        An :class:`EvaluationResult` marked as unverified.
    """
    return build_evaluation_result(
        task,
        run,
        passed_public_tests=False,
        passed_hidden_tests=False,
        weaknesses=[WeaknessCode.VERIFY],
        rationale=rationale,
        diff_text=diff_text,
    )
