"""Week 4 capstone — end-to-end controlled patch evaluation.

Wires every Week 4 building block into one test so the path
``TaskSpec -> TaskFixtureLayout -> apply patch -> run tests ->
TaskEvidence -> EvaluationResult -> RunReport`` is exercised in a
single place. No agent is executed; only a controlled synthetic patch
for ``bugfix_005`` is applied inside a tmp_path workspace copy.
"""

from pathlib import Path

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import (
    BenchmarkPack,
    RunReport,
    TaskSpec,
    WeaknessCode,
)
from agenteval.evaluation import (
    TaskEvidence,
    build_pack_evaluation_results,
)
from agenteval.execution import (
    PatchApplyResult,
    apply_patch_to_workspace,
    copy_fixture_apply_patch_and_build_evidence,
    copy_fixture_to_workspace,
    run_pytest_nodes_in_workspace,
)
from agenteval.fixtures import resolve_task_fixture_layout
from agenteval.reports.run_report import build_run_report

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"


BUGFIX_005_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -12,4 +12,4 @@ def is_within_range(value, low, high):
     The function should be inclusive on both bounds, but currently uses
     strict inequalities.
     """
-    return low < value < high
+    return low <= value <= high
'''


def test_week4_capstone_controlled_patch_to_run_report(tmp_path: Path):
    # --- 1. TaskSpec from the shipped pack -------------------------------
    pack: BenchmarkPack = load_benchmark_pack(PACK_DIR)
    task: TaskSpec = next(t for t in pack.tasks if t.task_id == "bugfix_005")

    # --- 2. TaskFixtureLayout from the on-disk fixture --------------------
    layout = resolve_task_fixture_layout(task, project_root=REPO_ROOT)
    assert layout.repo_path.is_dir()

    # --- 3. Apply candidate patch inside a copied workspace ---------------
    workspace = copy_fixture_to_workspace(layout, tmp_path / "manual")
    patch_result: PatchApplyResult = apply_patch_to_workspace(
        workspace_path=workspace,
        diff_text=BUGFIX_005_PATCH,
    )
    assert patch_result.applied is True
    assert "is_within_range.py" in patch_result.changed_files

    # The original fixture on disk must remain untouched.
    original_source = (layout.repo_path / "is_within_range.py").read_text(
        encoding="utf-8"
    )
    assert "low < value < high" in original_source
    # The copied workspace got the fix.
    patched_source = (workspace / "is_within_range.py").read_text(
        encoding="utf-8"
    )
    assert "low <= value <= high" in patched_source

    # --- 4. Run public and hidden tests inside the patched workspace -----
    public_result = run_pytest_nodes_in_workspace(
        task_id=task.task_id,
        node_ids=task.public_tests,
        test_kind="public",
        workspace_path=workspace,
    )
    hidden_result = run_pytest_nodes_in_workspace(
        task_id=task.task_id,
        node_ids=task.hidden_tests,
        test_kind="hidden",
        workspace_path=workspace,
    )
    assert public_result.passed is True
    assert hidden_result.passed is True

    # --- 5. Build TaskEvidence via the convenience helper -----------------
    # The helper does the copy/patch/run end-to-end against a fresh
    # workspace so we exercise that path too, alongside the manual one
    # above.
    evidence: TaskEvidence = copy_fixture_apply_patch_and_build_evidence(
        task=task,
        layout=layout,
        diff_text=BUGFIX_005_PATCH,
        workspace_root=tmp_path / "helper",
        final_message="Inclusive-bounds fix applied to bugfix_005.",
    )
    assert evidence.passed_public_tests is True
    assert evidence.passed_hidden_tests is True
    assert evidence.weaknesses == []
    assert evidence.diff_text == BUGFIX_005_PATCH
    assert "Inclusive-bounds fix" in evidence.final_message
    # The original fixture must still be untouched after the second run.
    assert (
        layout.repo_path / "is_within_range.py"
    ).read_text(encoding="utf-8") == original_source

    # --- 6. Build EvaluationResult from the TaskEvidence ------------------
    # Run a single-task pack through the existing batch builder so the
    # produced EvaluationResult flows through exactly the same code path
    # the comparison/report layer already consumes.
    minimal_pack = BenchmarkPack(
        name=pack.name, version=pack.version, tasks=[task]
    )
    results = build_pack_evaluation_results(
        minimal_pack,
        agent_name="capstone_synthetic_patch",
        evidence_by_task_id={task.task_id: evidence},
    )
    assert len(results) == 1
    result = results[0]
    assert result.task_id == "bugfix_005"
    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is True
    assert WeaknessCode.LAZY not in result.weaknesses
    assert WeaknessCode.ROOT not in result.weaknesses
    assert WeaknessCode.VERIFY not in result.weaknesses
    # Both buckets green plus no weaknesses must yield a high score; pin a
    # loose floor so this test does not over-specify the scoring formula.
    assert result.score >= 0.9, f"Expected high score, got {result.score}"
    # The diff travelled through as patch evidence.
    assert result.patch_summary is not None
    assert "is_within_range.py" in result.patch_summary.changed_files

    # --- 7. Build a RunReport from the EvaluationResult -------------------
    report: RunReport = build_run_report(
        minimal_pack,
        agent_name="capstone_synthetic_patch",
        results=results,
    )
    assert isinstance(report, RunReport)
    assert report.pack_name == pack.name
    assert report.pack_version == pack.version
    assert report.agent_name == "capstone_synthetic_patch"
    assert report.total_tasks == 1
    assert report.mean_score >= 0.9
    # No weakness recorded for this clean-pass case.
    assert report.weakness_tally == {}
    assert report.results == results
