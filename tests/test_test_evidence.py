"""Tests for ``agenteval.evaluation.test_evidence``.

These tests cover the small bridge that turns two :class:`PytestRunResult`
objects (public + hidden) into one :class:`TaskEvidence`. The unit tests
fabricate ``PytestRunResult`` objects directly so they exercise every
public-pass / hidden-pass combination without spawning subprocesses, and an
end-to-end test wires the bridge to the controlled execution harness
against the shipped ``bugfix_005`` fixture.

No agent is invoked, no patch is applied, no fixture source is mutated.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import BenchmarkPack, TaskSpec, WeaknessCode
from agenteval.evaluation import (
    TaskEvidence,
    build_evaluation_result,
    build_pack_evaluation_results,
    build_task_evidence_from_pytest_results,
    build_task_evidence_from_task_test_run,
)
from agenteval.execution.pytest_harness import PytestRunResult
from agenteval.fixtures import resolve_task_fixture_layout
from agenteval.runs.scaffold import create_placeholder_run

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"


# --- helpers --------------------------------------------------------------


def _fake_result(
    *,
    task_id: str = "bugfix_005",
    kind: str = "public",
    passed: bool = True,
    exit_code: int | None = None,
) -> PytestRunResult:
    code = exit_code if exit_code is not None else (0 if passed else 1)
    node_ids = [f"tests/test_{task_id}.py::test_one"]
    return PytestRunResult(
        task_id=task_id,
        test_kind=kind,
        node_ids=list(node_ids),
        passed=passed,
        exit_code=code,
        stdout="== 1 passed ==" if passed else "== 1 failed ==",
        stderr="",
        command=["python", "-m", "pytest", *node_ids],
        workspace_path="/tmp/fake",
    )


# --- public/hidden combinatorics ------------------------------------------


def test_both_pass_yields_evidence_with_both_flags_and_no_weaknesses():
    public = _fake_result(kind="public", passed=True)
    hidden = _fake_result(kind="hidden", passed=True)

    evidence = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    )

    assert isinstance(evidence, TaskEvidence)
    assert evidence.passed_public_tests is True
    assert evidence.passed_hidden_tests is True
    assert evidence.weaknesses == []
    assert "Public tests passed" in evidence.rationale
    assert "Hidden tests passed" in evidence.rationale


def test_public_pass_hidden_fail_yields_root_weakness():
    public = _fake_result(kind="public", passed=True)
    hidden = _fake_result(kind="hidden", passed=False)

    evidence = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    )

    assert evidence.passed_public_tests is True
    assert evidence.passed_hidden_tests is False
    assert evidence.weaknesses, "Expected at least one weakness."
    assert WeaknessCode.ROOT in evidence.weaknesses
    assert "Hidden tests failed" in evidence.rationale


def test_public_fail_hidden_pass_yields_lazy_weakness():
    public = _fake_result(kind="public", passed=False)
    hidden = _fake_result(kind="hidden", passed=True)

    evidence = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    )

    assert evidence.passed_public_tests is False
    assert evidence.passed_hidden_tests is True
    assert WeaknessCode.LAZY in evidence.weaknesses


def test_both_fail_yields_at_least_one_weakness_and_both_flags_false():
    public = _fake_result(kind="public", passed=False)
    hidden = _fake_result(kind="hidden", passed=False)

    evidence = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    )

    assert evidence.passed_public_tests is False
    assert evidence.passed_hidden_tests is False
    assert evidence.weaknesses, "Expected at least one weakness."
    assert all(
        isinstance(code, WeaknessCode) for code in evidence.weaknesses
    )


# --- field forwarding -----------------------------------------------------


def test_explicit_rationale_is_preserved_verbatim():
    public = _fake_result(passed=True)
    hidden = _fake_result(kind="hidden", passed=True)

    evidence = build_task_evidence_from_pytest_results(
        public_result=public,
        hidden_result=hidden,
        rationale="Custom rationale that must survive untouched.",
    )

    assert evidence.rationale == "Custom rationale that must survive untouched."


def test_default_rationale_mentions_both_outcomes_and_exit_codes():
    public = _fake_result(kind="public", passed=True, exit_code=0)
    hidden = _fake_result(kind="hidden", passed=False, exit_code=2)

    evidence = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    )

    rationale = evidence.rationale
    assert "Public" in rationale and "passed" in rationale
    assert "Hidden" in rationale and "failed" in rationale
    assert "exit 0" in rationale
    assert "exit 2" in rationale


def test_default_rationale_is_deterministic_for_same_inputs():
    public = _fake_result(passed=True)
    hidden = _fake_result(kind="hidden", passed=False)

    first = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    ).rationale
    second = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    ).rationale

    assert first == second


def test_diff_text_is_preserved():
    public = _fake_result(passed=True)
    hidden = _fake_result(kind="hidden", passed=True)
    diff = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-x\n+y\n"

    evidence = build_task_evidence_from_pytest_results(
        public_result=public,
        hidden_result=hidden,
        diff_text=diff,
    )

    assert evidence.diff_text == diff


def test_final_message_is_preserved():
    public = _fake_result(passed=True)
    hidden = _fake_result(kind="hidden", passed=True)

    evidence = build_task_evidence_from_pytest_results(
        public_result=public,
        hidden_result=hidden,
        final_message="Done. All tests pass.",
    )

    assert evidence.final_message == "Done. All tests pass."


def test_pytest_result_inputs_are_not_mutated():
    public = _fake_result(kind="public", passed=True)
    hidden = _fake_result(kind="hidden", passed=False)
    public_snapshot = replace(public)
    hidden_snapshot = replace(hidden)

    build_task_evidence_from_pytest_results(
        public_result=public,
        hidden_result=hidden,
        diff_text="dummy",
        final_message="dummy",
        rationale="dummy",
    )

    assert public == public_snapshot
    assert hidden == hidden_snapshot


# --- integration with the existing result builder -------------------------


def test_evidence_feeds_build_evaluation_result_cleanly():
    public = _fake_result(passed=True)
    hidden = _fake_result(kind="hidden", passed=False)
    evidence = build_task_evidence_from_pytest_results(
        public_result=public, hidden_result=hidden
    )
    task = TaskSpec(task_id="bugfix_005", title="x", repo_path="repos/bugfix_005")
    run = create_placeholder_run(task, agent_name="harness_smoke")

    result = build_evaluation_result(
        task,
        run,
        passed_public_tests=evidence.passed_public_tests,
        passed_hidden_tests=evidence.passed_hidden_tests,
        weaknesses=evidence.weaknesses,
        rationale=evidence.rationale,
        diff_text=evidence.diff_text,
    )

    assert result.task_id == "bugfix_005"
    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is False
    assert WeaknessCode.ROOT in result.weaknesses
    # Score is bounded by the existing scoring function — we just check it's
    # within [0, 1] so this test does not pin a specific scoring formula.
    assert 0.0 <= result.score <= 1.0


def test_evidence_feeds_pack_batch_builder():
    # Round-trip: one TaskEvidence for one task, no mutation expected.
    pack = load_benchmark_pack(PACK_DIR)
    task = next(t for t in pack.tasks if t.task_id == "bugfix_005")
    public = _fake_result(passed=True)
    hidden = _fake_result(kind="hidden", passed=False)
    evidence = build_task_evidence_from_pytest_results(
        public_result=public,
        hidden_result=hidden,
        final_message="ran the harness on the broken fixture",
    )

    minimal_pack = type(pack)(
        name=pack.name, version=pack.version, tasks=[task]
    )
    results = build_pack_evaluation_results(
        minimal_pack,
        agent_name="harness_smoke",
        evidence_by_task_id={"bugfix_005": evidence},
    )

    assert len(results) == 1
    assert results[0].task_id == "bugfix_005"
    assert results[0].passed_public_tests is True
    assert results[0].passed_hidden_tests is False
    assert WeaknessCode.ROOT in results[0].weaknesses


# --- end-to-end against the bugfix_005 fixture ----------------------------


def test_build_evidence_from_task_test_run_on_bugfix_005(tmp_path: Path):
    pack: BenchmarkPack = load_benchmark_pack(PACK_DIR)
    task = next(t for t in pack.tasks if t.task_id == "bugfix_005")
    layout = resolve_task_fixture_layout(task, project_root=REPO_ROOT)

    evidence = build_task_evidence_from_task_test_run(
        task,
        layout,
        workspace_root=tmp_path,
    )

    # bugfix_005's broken implementation: public tests still pass, hidden
    # tests fail on the boundary-inclusivity edges.
    assert evidence.passed_public_tests is True
    assert evidence.passed_hidden_tests is False
    assert WeaknessCode.ROOT in evidence.weaknesses
    assert "Public tests passed" in evidence.rationale
    assert "Hidden tests failed" in evidence.rationale
