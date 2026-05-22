"""Tests for carrying PatchSummary evidence through reports and Markdown."""

import json

from agenteval.core.schemas import (
    BenchmarkPack,
    EvaluationResult,
    PatchSummary,
    TaskSpec,
    WeaknessCode,
)
from agenteval.patches.diff_summary import parse_unified_diff
from agenteval.reports.markdown import render_run_report_markdown
from agenteval.reports.run_report import (
    build_run_report,
    run_report_from_dict,
    run_report_to_dict,
)
from agenteval.runs.scaffold import evaluate_pack_placeholder


def _patch() -> PatchSummary:
    return PatchSummary(
        changed_files=["sum_range.py"],
        added_files=["helpers.py"],
        deleted_files=["legacy.py"],
        diff_text="diff --git a/sum_range.py b/sum_range.py\n",
    )


def _result(
    task_id: str = "t1",
    patch_summary: PatchSummary | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=f"claude-code:{task_id}:placeholder",
        score=0.5,
        weaknesses=[WeaknessCode.VERIFY],
        rationale="A rationale.",
        patch_summary=patch_summary,
    )


def _report(results: list[EvaluationResult]):
    return build_run_report(
        BenchmarkPack(name="demo_pack", version="1.0"),
        "claude-code",
        results,
    )


def test_evaluation_result_without_patch_summary_defaults_to_none():
    result = EvaluationResult(task_id="t1", run_id="r1")
    assert result.patch_summary is None


def test_evaluation_result_with_patch_summary():
    patch = _patch()
    result = EvaluationResult(task_id="t1", run_id="r1", patch_summary=patch)
    assert result.patch_summary is patch
    assert result.patch_summary.changed_files == ["sum_range.py"]


def test_run_report_to_dict_includes_patch_summary_when_present():
    data = run_report_to_dict(_report([_result("t1", _patch())]))
    patch_dict = data["results"][0]["patch_summary"]
    assert patch_dict is not None
    assert patch_dict["changed_files"] == ["sum_range.py"]
    assert patch_dict["added_files"] == ["helpers.py"]
    assert patch_dict["deleted_files"] == ["legacy.py"]
    # The whole report stays JSON-serializable.
    assert isinstance(json.dumps(data), str)


def test_run_report_to_dict_patch_summary_is_none_when_absent():
    data = run_report_to_dict(_report([_result("t1", None)]))
    assert data["results"][0]["patch_summary"] is None


def test_run_report_from_dict_reconstructs_patch_summary():
    report = _report([_result("t1", _patch())])
    rebuilt = run_report_from_dict(run_report_to_dict(report))
    patch = rebuilt.results[0].patch_summary
    assert isinstance(patch, PatchSummary)
    assert patch.changed_files == ["sum_range.py"]
    assert patch.added_files == ["helpers.py"]
    assert patch.deleted_files == ["legacy.py"]
    assert patch.diff_text == "diff --git a/sum_range.py b/sum_range.py\n"


def test_run_report_from_dict_works_without_patch_summary_key():
    # An older report, written before the patch_summary field existed.
    legacy_data = {
        "pack_name": "demo_pack",
        "pack_version": "1.0",
        "agent_name": "claude-code",
        "total_tasks": 1,
        "mean_score": 0.5,
        "weakness_tally": {"VERIFY": 1},
        "results": [
            {
                "task_id": "t1",
                "run_id": "r1",
                "score": 0.5,
                "passed_public_tests": False,
                "passed_hidden_tests": False,
                "weaknesses": ["VERIFY"],
                "rationale": "Legacy result.",
            }
        ],
    }
    report = run_report_from_dict(legacy_data)
    assert report.results[0].patch_summary is None


def test_markdown_shows_changed_added_deleted_files():
    md = render_run_report_markdown(_report([_result("t1", _patch())]))
    assert "Patch evidence" in md
    assert "sum_range.py" in md
    assert "helpers.py" in md
    assert "legacy.py" in md


def test_markdown_handles_missing_patch_evidence():
    md = render_run_report_markdown(_report([_result("t1", None)]))
    assert "Patch evidence" in md
    assert "No patch evidence recorded" in md


def test_markdown_handles_empty_patch_evidence():
    empty_patch = PatchSummary(diff_text="")
    md = render_run_report_markdown(_report([_result("t1", empty_patch)]))
    assert "no changed/added/deleted files were detected" in md


def test_parsed_diff_flows_into_markdown_report():
    diff = (
        "diff --git a/sum_range.py b/sum_range.py\n"
        "--- a/sum_range.py\n"
        "+++ b/sum_range.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    patch = parse_unified_diff(diff)
    md = render_run_report_markdown(_report([_result("t1", patch)]))
    assert "sum_range.py" in md


def test_placeholder_pipeline_still_works():
    pack = BenchmarkPack(
        name="demo",
        tasks=[TaskSpec(task_id="t1", title="A task")],
    )
    results = evaluate_pack_placeholder(pack, "claude-code")
    assert len(results) == 1
    # Placeholder results carry no patch evidence.
    assert results[0].patch_summary is None
    md = render_run_report_markdown(_report(results))
    assert "No patch evidence recorded" in md
