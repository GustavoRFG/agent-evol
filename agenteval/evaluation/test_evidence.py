"""Convert pytest execution evidence into :class:`TaskEvidence`.

This module bridges Week 4 Day 5's controlled execution harness
(:mod:`agenteval.execution.pytest_harness`) to the evidence-in / report-out
pipeline assembled by :mod:`agenteval.evaluation`. Given the public and
hidden :class:`PytestRunResult` objects for one task, it produces a single
:class:`TaskEvidence` that :func:`build_pack_evaluation_results` can later
feed into the result builder.

It performs **no** agent execution and **no** patch application. The
optional :func:`build_task_evidence_from_task_test_run` does spawn the
controlled pytest harness, but only against the *current* fixture state —
the fixture is copied to ``workspace_root`` first and never mutated.

Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.core.schemas import TaskSpec, WeaknessCode
from agenteval.evaluation.batch_builder import TaskEvidence
from agenteval.execution.pytest_harness import (
    PytestRunResult,
    run_task_tests,
)
from agenteval.fixtures import TaskFixtureLayout


def _weaknesses_for_test_outcome(
    *, public_passed: bool, hidden_passed: bool
) -> list[WeaknessCode]:
    """Pick :class:`WeaknessCode` values that fit a public/hidden outcome.

    Choices are made against the *existing* :class:`WeaknessCode` enum;
    no new codes are introduced. The mapping is:

    - both pass:        no weaknesses;
    - public pass only: ``ROOT`` — the surface symptom was patched but
      the hidden suite shows the root cause is still present;
    - public fail:      ``LAZY`` — the work is incomplete / low effort
      because even the publicly visible tests fail.
    """
    if public_passed and hidden_passed:
        return []
    if public_passed and not hidden_passed:
        return [WeaknessCode.ROOT]
    return [WeaknessCode.LAZY]


def _default_rationale(
    public_result: PytestRunResult,
    hidden_result: PytestRunResult,
) -> str:
    """Produce a deterministic rationale string for one task's test run.

    The format is intentionally stable — same inputs always produce the
    same text — so it can be compared across reports without spurious
    diffs.
    """

    def fragment(kind: str, result: PytestRunResult) -> str:
        outcome = "passed" if result.passed else "failed"
        return f"{kind} tests {outcome} (exit {result.exit_code})"

    return (
        f"{fragment('Public', public_result)}; "
        f"{fragment('Hidden', hidden_result)}."
    )


def build_task_evidence_from_pytest_results(
    *,
    public_result: PytestRunResult,
    hidden_result: PytestRunResult,
    rationale: str | None = None,
    diff_text: str | None = None,
    final_message: str = "",
) -> TaskEvidence:
    """Summarize a public + hidden pytest run as :class:`TaskEvidence`.

    The two :class:`PytestRunResult` inputs are read but never mutated.
    ``passed_*`` flags come straight from each result's ``passed`` field.
    ``weaknesses`` is derived from the outcome using only existing
    :class:`WeaknessCode` values. ``rationale`` is either passed through
    verbatim (when non-``None``) or generated deterministically from the
    public/hidden pass states and pytest exit codes.

    Args:
        public_result: Outcome of running the task's public tests.
        hidden_result: Outcome of running the task's hidden tests.
        rationale: Caller-supplied rationale; defaults to a deterministic
            summary derived from the two results.
        diff_text: Optional unified diff to forward into the evidence
            (e.g. for downstream patch-evidence parsing).
        final_message: Optional final message to forward into the
            evidence (e.g. the agent's final answer text).

    Returns:
        A :class:`TaskEvidence` ready for
        :func:`build_pack_evaluation_results`.
    """
    text = rationale if rationale is not None else _default_rationale(
        public_result, hidden_result
    )
    weaknesses = _weaknesses_for_test_outcome(
        public_passed=public_result.passed,
        hidden_passed=hidden_result.passed,
    )
    return TaskEvidence(
        passed_public_tests=bool(public_result.passed),
        passed_hidden_tests=bool(hidden_result.passed),
        weaknesses=weaknesses,
        rationale=text,
        diff_text=diff_text,
        final_message=final_message,
    )


def build_task_evidence_from_task_test_run(
    task: TaskSpec,
    layout: TaskFixtureLayout,
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    rationale: str | None = None,
    diff_text: str | None = None,
    final_message: str = "",
) -> TaskEvidence:
    """Run the task's public + hidden tests once, then summarize as evidence.

    This is a thin convenience wrapper over :func:`run_task_tests` followed
    by :func:`build_task_evidence_from_pytest_results`. It is **not** agent
    execution and **not** patch application — the harness runs the fixture
    in its current on-disk state, against a fresh workspace copy.
    """
    public_result, hidden_result = run_task_tests(
        task,
        layout,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
    )
    return build_task_evidence_from_pytest_results(
        public_result=public_result,
        hidden_result=hidden_result,
        rationale=rationale,
        diff_text=diff_text,
        final_message=final_message,
    )
