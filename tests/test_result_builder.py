"""Tests for the evidence-backed EvaluationResult builder."""

from agenteval.core.schemas import (
    AgentRun,
    BenchmarkPack,
    EvaluationResult,
    PatchSummary,
    TaskSpec,
    WeaknessCode,
)
from agenteval.core.scoring import compute_basic_score
from agenteval.evaluation.result_builder import (
    build_evaluation_result,
    build_unverified_result,
)
from agenteval.reports.markdown import render_run_report_markdown
from agenteval.reports.run_report import build_run_report
from agenteval.runs.scaffold import evaluate_pack_placeholder

MODIFIED_DIFF = """diff --git a/file.py b/file.py
index 1234567..89abcde 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def f():
-    return 1
+    return 2
"""


def _task(task_id: str = "bugfix_001") -> TaskSpec:
    return TaskSpec(task_id=task_id, title="A task")


def _run(task_id: str = "bugfix_001") -> AgentRun:
    return AgentRun(
        run_id=f"claude-code:{task_id}:r1",
        agent_name="claude-code",
        task_id=task_id,
    )


def test_build_evaluation_result_sets_task_id_and_run_id():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=True,
    )
    assert isinstance(result, EvaluationResult)
    assert result.task_id == "bugfix_001"
    assert result.run_id == "claude-code:bugfix_001:r1"


def test_build_evaluation_result_score_matches_compute_basic_score():
    weaknesses = [WeaknessCode.INST]
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=False,
        weaknesses=weaknesses,
    )
    expected = compute_basic_score(True, False, weaknesses)
    assert result.score == expected


def test_build_evaluation_result_weaknesses_none_defaults_to_empty_list():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=True,
        weaknesses=None,
    )
    assert result.weaknesses == []


def test_build_evaluation_result_preserves_pass_flags():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=False,
    )
    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is False


def test_build_evaluation_result_preserves_rationale():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=False,
        passed_hidden_tests=False,
        rationale="Fixed the root cause.",
    )
    assert result.rationale == "Fixed the root cause."


def test_build_evaluation_result_diff_text_none_leaves_patch_summary_none():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=True,
        diff_text=None,
    )
    assert result.patch_summary is None


def test_build_evaluation_result_diff_text_attaches_patch_summary():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=True,
        diff_text=MODIFIED_DIFF,
    )
    assert isinstance(result.patch_summary, PatchSummary)


def test_build_evaluation_result_modified_diff_in_changed_files():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=True,
        diff_text=MODIFIED_DIFF,
    )
    assert result.patch_summary.changed_files == ["file.py"]


def test_build_evaluation_result_does_not_mutate_inputs():
    task = _task()
    run = _run()
    weaknesses = [WeaknessCode.LAZY]
    result = build_evaluation_result(
        task,
        run,
        passed_public_tests=True,
        passed_hidden_tests=True,
        weaknesses=weaknesses,
    )
    # The caller's list is untouched and not aliased by the result.
    assert weaknesses == [WeaknessCode.LAZY]
    assert result.weaknesses is not weaknesses
    # Task and run identities are unchanged.
    assert task.task_id == "bugfix_001"
    assert run.run_id == "claude-code:bugfix_001:r1"


def test_build_unverified_result_adds_verify_weakness_and_zero_score():
    result = build_unverified_result(_task(), _run())
    assert WeaknessCode.VERIFY in result.weaknesses
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    assert result.score == 0.0


def test_build_unverified_result_can_attach_diff_text():
    result = build_unverified_result(
        _task(), _run(), diff_text=MODIFIED_DIFF
    )
    assert result.patch_summary is not None
    assert result.patch_summary.changed_files == ["file.py"]


def test_builder_result_works_with_build_run_report():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=False,
        weaknesses=[WeaknessCode.INST],
        diff_text=MODIFIED_DIFF,
    )
    report = build_run_report(
        BenchmarkPack(name="demo", version="1.0"), "claude-code", [result]
    )
    assert report.total_tasks == 1
    assert report.weakness_tally.get("INST") == 1
    assert report.results[0].patch_summary.changed_files == ["file.py"]


def test_builder_result_appears_in_markdown_report():
    result = build_evaluation_result(
        _task(),
        _run(),
        passed_public_tests=True,
        passed_hidden_tests=True,
        rationale="All checks passed.",
        diff_text=MODIFIED_DIFF,
    )
    report = build_run_report(
        BenchmarkPack(name="demo", version="1.0"), "claude-code", [result]
    )
    md = render_run_report_markdown(report)
    assert "bugfix_001" in md
    assert "All checks passed." in md
    assert "file.py" in md


def test_placeholder_pipeline_still_works():
    pack = BenchmarkPack(
        name="demo",
        tasks=[TaskSpec(task_id="t1", title="A task")],
    )
    results = evaluate_pack_placeholder(pack, "claude-code")
    assert len(results) == 1
    assert results[0].patch_summary is None
