"""Tests for the batch evaluation result builder."""

from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import (
    AgentRun,
    BenchmarkPack,
    EvaluationResult,
    TaskSpec,
    WeaknessCode,
)
from agenteval.evaluation.batch_builder import (
    BatchEvaluationError,
    TaskEvidence,
    build_pack_evaluation_results,
    build_run_for_task,
)
from agenteval.reports.markdown import render_run_report_markdown
from agenteval.reports.run_report import build_run_report
from agenteval.runs.scaffold import evaluate_pack_placeholder

REPO_ROOT = Path(__file__).resolve().parent.parent

MODIFIED_DIFF = """diff --git a/file.py b/file.py
index 1234567..89abcde 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def f():
-    return 1
+    return 2
"""


def _pack(*task_ids: str) -> BenchmarkPack:
    return BenchmarkPack(
        name="demo_pack",
        version="1.0",
        tasks=[TaskSpec(task_id=tid, title=f"Task {tid}") for tid in task_ids],
    )


def test_one_result_per_task():
    results = build_pack_evaluation_results(_pack("a", "b", "c"), "codex", {})
    assert len(results) == 3
    assert all(isinstance(r, EvaluationResult) for r in results)


def test_results_follow_pack_task_order():
    results = build_pack_evaluation_results(
        _pack("first", "second", "third"), "codex", {}
    )
    assert [r.task_id for r in results] == ["first", "second", "third"]


def test_evidence_is_used_correctly():
    evidence = {
        "a": TaskEvidence(
            passed_public_tests=True,
            passed_hidden_tests=True,
            rationale="All tests passed.",
        )
    }
    results = build_pack_evaluation_results(_pack("a"), "claude-code", evidence)
    result = results[0]
    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is True
    assert result.rationale == "All tests passed."
    assert result.score == 1.0


def test_missing_evidence_creates_unverified_result():
    evidence = {
        "a": TaskEvidence(passed_public_tests=True, passed_hidden_tests=True)
    }
    results = build_pack_evaluation_results(
        _pack("a", "b"), "claude-code", evidence
    )
    result_b = results[1]
    assert result_b.task_id == "b"
    assert WeaknessCode.VERIFY in result_b.weaknesses
    assert result_b.score == 0.0


def test_unknown_task_id_in_evidence_raises_clear_error():
    evidence = {"a": TaskEvidence(), "ghost": TaskEvidence()}
    with pytest.raises(BatchEvaluationError) as exc_info:
        build_pack_evaluation_results(_pack("a"), "claude-code", evidence)
    assert "ghost" in str(exc_info.value)


def test_diff_text_attaches_patch_summary():
    evidence = {"a": TaskEvidence(diff_text=MODIFIED_DIFF)}
    results = build_pack_evaluation_results(_pack("a"), "claude-code", evidence)
    assert results[0].patch_summary is not None
    assert results[0].patch_summary.changed_files == ["file.py"]


def test_build_run_for_task_carries_final_message():
    run = build_run_for_task(
        TaskSpec(task_id="a", title="A"), "claude-code", final_message="Done."
    )
    assert isinstance(run, AgentRun)
    assert run.final_message == "Done."
    assert run.task_id == "a"


def test_build_run_for_task_without_message_keeps_placeholder_message():
    run = build_run_for_task(TaskSpec(task_id="a", title="A"), "claude-code")
    # The placeholder run's own final message is preserved.
    assert run.final_message != ""


def test_input_evidence_is_not_mutated():
    weaknesses = [WeaknessCode.INST]
    evidence_obj = TaskEvidence(passed_public_tests=True, weaknesses=weaknesses)
    build_pack_evaluation_results(
        _pack("a"), "claude-code", {"a": evidence_obj}
    )
    assert evidence_obj.weaknesses is weaknesses
    assert evidence_obj.weaknesses == [WeaknessCode.INST]


def test_results_work_with_build_run_report():
    evidence = {
        "a": TaskEvidence(passed_public_tests=True, passed_hidden_tests=True)
    }
    pack = _pack("a", "b")
    results = build_pack_evaluation_results(pack, "claude-code", evidence)
    report = build_run_report(pack, "claude-code", results)
    assert report.total_tasks == 2
    assert report.weakness_tally.get("VERIFY") == 1


def test_results_render_with_markdown():
    evidence = {
        "a": TaskEvidence(rationale="Looks good.", diff_text=MODIFIED_DIFF)
    }
    pack = _pack("a")
    results = build_pack_evaluation_results(pack, "claude-code", evidence)
    md = render_run_report_markdown(
        build_run_report(pack, "claude-code", results)
    )
    assert "Looks good." in md
    assert "file.py" in md


def test_shipped_pack_end_to_end_with_one_evidence_item():
    pack = load_benchmark_pack(
        REPO_ROOT / "benchmarks" / "python_bugfix_basic"
    )
    evidence = {
        "bugfix_001": TaskEvidence(
            passed_public_tests=True,
            passed_hidden_tests=True,
            rationale="Fixed the off-by-one.",
            diff_text=MODIFIED_DIFF,
        )
    }
    results = build_pack_evaluation_results(pack, "claude-code", evidence)
    assert len(results) == len(pack.tasks)
    md = render_run_report_markdown(
        build_run_report(pack, "claude-code", results)
    )
    assert "python_bugfix_basic" in md
    assert "bugfix_001" in md


def test_placeholder_pipeline_still_works():
    results = evaluate_pack_placeholder(_pack("t1"), "claude-code")
    assert len(results) == 1
    assert results[0].patch_summary is None
