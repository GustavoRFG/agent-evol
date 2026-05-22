"""Tests for the one-call pack evaluation report builder."""

from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import (
    BenchmarkPack,
    RunReport,
    TaskSpec,
    WeaknessCode,
)
from agenteval.evaluation.batch_builder import BatchEvaluationError, TaskEvidence
from agenteval.evaluation.pack_report import (
    evaluate_pack_to_json_report,
    evaluate_pack_to_markdown_report,
    evaluate_pack_to_report,
)
from agenteval.reports.markdown import render_run_report_markdown
from agenteval.reports.run_report import load_run_report
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
        version="2.0",
        tasks=[TaskSpec(task_id=tid, title=f"Task {tid}") for tid in task_ids],
    )


def test_evaluate_pack_to_report_returns_run_report():
    report = evaluate_pack_to_report(_pack("a"), "claude-code", {})
    assert isinstance(report, RunReport)


def test_report_carries_pack_and_agent_metadata():
    report = evaluate_pack_to_report(_pack("a", "b"), "codex", {})
    assert report.pack_name == "demo_pack"
    assert report.pack_version == "2.0"
    assert report.agent_name == "codex"


def test_report_total_tasks_matches_pack():
    report = evaluate_pack_to_report(_pack("a", "b", "c"), "codex", {})
    assert report.total_tasks == 3
    assert len(report.results) == 3


def test_evidence_is_reflected_in_report_results():
    evidence = {
        "a": TaskEvidence(
            passed_public_tests=True,
            passed_hidden_tests=True,
            rationale="All good.",
        )
    }
    report = evaluate_pack_to_report(_pack("a"), "claude-code", evidence)
    result = report.results[0]
    assert result.task_id == "a"
    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is True
    assert result.rationale == "All good."
    assert result.score == 1.0


def test_missing_evidence_becomes_unverified_result():
    report = evaluate_pack_to_report(_pack("a"), "claude-code", {})
    result = report.results[0]
    assert WeaknessCode.VERIFY in result.weaknesses
    assert result.score == 0.0
    assert report.weakness_tally.get("VERIFY") == 1


def test_unknown_task_id_raises_batch_evaluation_error():
    with pytest.raises(BatchEvaluationError) as exc_info:
        evaluate_pack_to_report(
            _pack("a"), "claude-code", {"ghost": TaskEvidence()}
        )
    assert "ghost" in str(exc_info.value)


def test_diff_text_evidence_appears_as_patch_summary():
    evidence = {"a": TaskEvidence(diff_text=MODIFIED_DIFF)}
    report = evaluate_pack_to_report(_pack("a"), "claude-code", evidence)
    patch = report.results[0].patch_summary
    assert patch is not None
    assert patch.changed_files == ["file.py"]


def test_report_renders_to_markdown():
    evidence = {"a": TaskEvidence(rationale="Looks good.")}
    report = evaluate_pack_to_report(_pack("a"), "claude-code", evidence)
    md = render_run_report_markdown(report)
    assert "demo_pack" in md
    assert "Looks good." in md


def test_json_save_helper_writes_and_round_trips(tmp_path):
    evidence = {
        "a": TaskEvidence(passed_public_tests=True, diff_text=MODIFIED_DIFF)
    }
    path = tmp_path / "report.json"
    report = evaluate_pack_to_json_report(
        _pack("a"), "claude-code", evidence, path
    )
    assert isinstance(report, RunReport)
    assert path.is_file()
    loaded = load_run_report(path)
    assert loaded.pack_name == "demo_pack"
    assert loaded.agent_name == "claude-code"
    assert loaded.results[0].patch_summary.changed_files == ["file.py"]


def test_markdown_save_helper_writes_readable_file(tmp_path):
    evidence = {"a": TaskEvidence(rationale="Readable rationale.")}
    # A nested path also exercises parent-directory creation.
    path = tmp_path / "nested" / "report.md"
    report = evaluate_pack_to_markdown_report(
        _pack("a"), "claude-code", evidence, path
    )
    assert isinstance(report, RunReport)
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# ")
    assert "Readable rationale." in content


def test_shipped_pack_end_to_end(tmp_path):
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
    report = evaluate_pack_to_report(pack, "claude-code", evidence)
    assert report.pack_name == "python_bugfix_basic"
    assert report.total_tasks == len(pack.tasks)

    md_path = tmp_path / "shipped.md"
    evaluate_pack_to_markdown_report(pack, "claude-code", evidence, md_path)
    assert md_path.is_file()
    assert "bugfix_001" in md_path.read_text(encoding="utf-8")


def test_placeholder_pipeline_still_works():
    results = evaluate_pack_placeholder(_pack("t1"), "claude-code")
    assert len(results) == 1
    assert results[0].patch_summary is None
