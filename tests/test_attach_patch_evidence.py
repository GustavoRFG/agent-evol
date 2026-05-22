"""Tests for attaching patch evidence to an EvaluationResult."""

from agenteval.core.schemas import (
    BenchmarkPack,
    EvaluationResult,
    PatchSummary,
    TaskSpec,
    WeaknessCode,
)
from agenteval.evaluation.patch_evidence import (
    attach_patch_summary_to_result,
    attach_patch_to_result,
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

ADDED_DIFF = """diff --git a/new_module.py b/new_module.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new_module.py
@@ -0,0 +1,2 @@
+def hello():
+    return "hi"
"""

DELETED_DIFF = """diff --git a/old_module.py b/old_module.py
deleted file mode 100644
index 1234567..0000000
--- a/old_module.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def gone():
-    pass
"""


def _result(task_id: str = "t1") -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=f"claude-code:{task_id}:placeholder",
        score=0.5,
        passed_public_tests=True,
        passed_hidden_tests=False,
        weaknesses=[WeaknessCode.VERIFY],
        rationale="A rationale.",
    )


def test_attach_patch_to_result_returns_new_instance():
    original = _result()
    updated = attach_patch_to_result(original, MODIFIED_DIFF)
    assert isinstance(updated, EvaluationResult)
    assert updated is not original


def test_attach_patch_to_result_does_not_mutate_original():
    original = _result()
    attach_patch_to_result(original, MODIFIED_DIFF)
    assert original.patch_summary is None


def test_attach_patch_to_result_preserves_all_existing_fields():
    original = _result("bugfix_001")
    updated = attach_patch_to_result(original, MODIFIED_DIFF)
    assert updated.task_id == original.task_id
    assert updated.run_id == original.run_id
    assert updated.score == original.score
    assert updated.passed_public_tests == original.passed_public_tests
    assert updated.passed_hidden_tests == original.passed_hidden_tests
    assert updated.weaknesses == original.weaknesses
    assert updated.rationale == original.rationale


def test_attach_modified_diff_populates_changed_files():
    updated = attach_patch_to_result(_result(), MODIFIED_DIFF)
    assert updated.patch_summary is not None
    assert updated.patch_summary.changed_files == ["file.py"]


def test_attach_added_diff_populates_added_files():
    updated = attach_patch_to_result(_result(), ADDED_DIFF)
    assert updated.patch_summary is not None
    assert updated.patch_summary.added_files == ["new_module.py"]


def test_attach_deleted_diff_populates_deleted_files():
    updated = attach_patch_to_result(_result(), DELETED_DIFF)
    assert updated.patch_summary is not None
    assert updated.patch_summary.deleted_files == ["old_module.py"]


def test_attach_empty_diff_still_attaches_patch_summary():
    updated = attach_patch_to_result(_result(), "   \n")
    assert isinstance(updated.patch_summary, PatchSummary)
    assert updated.patch_summary.changed_files == []
    assert updated.patch_summary.added_files == []
    assert updated.patch_summary.deleted_files == []
    assert updated.patch_summary.diff_text == "   \n"


def test_attach_patch_summary_to_result_uses_existing_summary():
    patch = PatchSummary(changed_files=["x.py"], diff_text="raw diff")
    original = _result()
    updated = attach_patch_summary_to_result(original, patch)
    assert updated is not original
    assert original.patch_summary is None
    assert updated.patch_summary is patch


def test_result_with_patch_evidence_works_in_build_run_report():
    result = attach_patch_to_result(_result("t1"), MODIFIED_DIFF)
    report = build_run_report(
        BenchmarkPack(name="demo", version="1.0"), "claude-code", [result]
    )
    assert report.total_tasks == 1
    assert report.results[0].patch_summary is not None
    assert report.results[0].patch_summary.changed_files == ["file.py"]


def test_result_with_patch_evidence_appears_in_markdown():
    result = attach_patch_to_result(_result("t1"), MODIFIED_DIFF)
    report = build_run_report(
        BenchmarkPack(name="demo", version="1.0"), "claude-code", [result]
    )
    md = render_run_report_markdown(report)
    assert "Patch evidence" in md
    assert "file.py" in md


def test_placeholder_pipeline_still_works():
    pack = BenchmarkPack(
        name="demo",
        tasks=[TaskSpec(task_id="t1", title="A task")],
    )
    results = evaluate_pack_placeholder(pack, "claude-code")
    assert len(results) == 1
    assert results[0].patch_summary is None
