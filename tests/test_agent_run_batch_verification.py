"""Tests for batch verification of ingested external agent artifacts."""

from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunVerificationError,
    ingest_agent_run_artifact,
    verify_agent_run_artifacts,
    verify_ingested_agent_runs,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import WeaknessCode
from agenteval.fixtures import resolve_task_fixture_layout

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

BUGFIX_005_GOOD_PATCH = '''\
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

BUGFIX_005_SEMANTICALLY_WRONG_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -12,4 +12,4 @@ def is_within_range(value, low, high):
     The function should be inclusive on both bounds, but currently uses
     strict inequalities.
     """
-    return low < value < high
+    return low == value == high
'''

BUGFIX_005_INVALID_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -999,1 +999,1 @@
-this line does not exist
+this line will never apply
'''


def _bugfix_005():
    pack = load_benchmark_pack(PACK_DIR)
    task = next(t for t in pack.tasks if t.task_id == "bugfix_005")
    layout = resolve_task_fixture_layout(task, project_root=REPO_ROOT)
    return task, layout


def _artifact(
    *,
    agent_name: str = "claude-code",
    task_id: str = "bugfix_005",
    run_id: str | None = None,
    diff_text: str = BUGFIX_005_GOOD_PATCH,
    final_message: str = "Inclusive comparisons.",
    **overrides,
) -> AgentRunArtifact:
    return AgentRunArtifact(
        agent_name=agent_name,
        task_id=task_id,
        run_id=run_id or f"{agent_name}:{task_id}:001",
        diff_text=diff_text,
        final_message=final_message,
        **overrides,
    )


# ---- happy path -------------------------------------------------------------


def test_two_valid_artifacts_can_be_verified_in_batch(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="r1")),
        ingest_agent_run_artifact(_artifact(run_id="r2")),
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert len(results) == 2
    for result in results:
        assert result.passed_public_tests is True
        assert result.passed_hidden_tests is True
        assert WeaknessCode.VERIFY not in result.weaknesses
        assert result.score >= 0.9


def test_input_order_is_preserved(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="r-z")),
        ingest_agent_run_artifact(_artifact(run_id="r-a")),
        ingest_agent_run_artifact(_artifact(run_id="r-m")),
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert [r.run_id for r in results] == ["r-z", "r-a", "r-m"]


def test_each_run_uses_distinct_sibling_workspace(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="dup")),
        ingest_agent_run_artifact(_artifact(run_id="dup")),
    ]
    verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )
    # Even with identical run_ids, the index prefix guarantees siblings.
    subdirs = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert len(subdirs) >= 2
    assert subdirs[0] != subdirs[1]
    assert all(d.startswith(("0000_", "0001_")) for d in subdirs[:2])


# ---- continue_on_error=True converts failures into results ------------------


def test_semantically_wrong_patch_yields_failing_result(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="good")),
        ingest_agent_run_artifact(
            _artifact(
                run_id="bad",
                diff_text=BUGFIX_005_SEMANTICALLY_WRONG_PATCH,
            )
        ),
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert len(results) == 2
    good, bad = results
    assert good.passed_public_tests is True and good.passed_hidden_tests is True
    # Bad patch applies cleanly but fails real tests — not an exception.
    assert bad.passed_public_tests is False
    assert bad.passed_hidden_tests is False
    assert bad.score < 0.9


def test_empty_diff_yields_unverified_result_when_lenient(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="empty", diff_text=""))
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert len(results) == 1
    result = results[0]
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert "empty diff_text" in result.rationale


def test_invalid_patch_yields_unverified_result_when_lenient(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(
            _artifact(run_id="invalid", diff_text=BUGFIX_005_INVALID_PATCH)
        )
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert len(results) == 1
    result = results[0]
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert "failed to apply patch" in result.rationale.lower() or (
        "git apply" in result.rationale.lower()
    )


def test_missing_task_yields_unverified_result_when_lenient(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(
            _artifact(run_id="orphan", task_id="bugfix_999")
        )
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert len(results) == 1
    result = results[0]
    assert result.task_id == "bugfix_999"
    assert result.passed_public_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert "no task found" in result.rationale


def test_missing_layout_yields_unverified_result_when_lenient(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [ingest_agent_run_artifact(_artifact(run_id="lay-miss"))]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        layouts_by_task_id={},  # no layouts
        workspace_root=tmp_path,
    )

    assert len(results) == 1
    result = results[0]
    assert result.task_id == task.task_id
    assert result.passed_public_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert "no layout found" in result.rationale


def test_mixed_batch_keeps_good_runs_and_marks_bad_runs(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="good")),
        ingest_agent_run_artifact(
            _artifact(run_id="invalid", diff_text=BUGFIX_005_INVALID_PATCH)
        ),
        ingest_agent_run_artifact(
            _artifact(run_id="orphan", task_id="bugfix_999")
        ),
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert [r.run_id for r in results] == ["good", "invalid", "orphan"]
    assert results[0].passed_public_tests is True
    assert results[1].passed_public_tests is False
    assert WeaknessCode.VERIFY in results[1].weaknesses
    assert results[2].passed_public_tests is False
    assert results[2].task_id == "bugfix_999"


# ---- continue_on_error=False raises on first failure -----------------------


def test_continue_on_error_false_raises_for_missing_task(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="good")),
        ingest_agent_run_artifact(
            _artifact(run_id="orphan", task_id="bugfix_999")
        ),
    ]
    with pytest.raises(AgentRunVerificationError, match="bugfix_999"):
        verify_ingested_agent_runs(
            {task.task_id: task},
            ingested_runs,
            {task.task_id: layout},
            workspace_root=tmp_path,
            continue_on_error=False,
        )


def test_continue_on_error_false_raises_for_invalid_patch(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(
            _artifact(run_id="invalid", diff_text=BUGFIX_005_INVALID_PATCH)
        ),
    ]
    with pytest.raises(AgentRunVerificationError, match="invalid"):
        verify_ingested_agent_runs(
            {task.task_id: task},
            ingested_runs,
            {task.task_id: layout},
            workspace_root=tmp_path,
            continue_on_error=False,
        )


def test_continue_on_error_false_raises_for_empty_diff(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="empty", diff_text=""))
    ]
    with pytest.raises(AgentRunVerificationError, match="empty"):
        verify_ingested_agent_runs(
            {task.task_id: task},
            ingested_runs,
            {task.task_id: layout},
            workspace_root=tmp_path,
            continue_on_error=False,
        )


# ---- claim non-trust + immutability ----------------------------------------


def test_claimed_results_do_not_override_real_outcomes(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested_runs = [
        ingest_agent_run_artifact(
            _artifact(
                run_id="liar",
                diff_text=BUGFIX_005_SEMANTICALLY_WRONG_PATCH,
                claimed_public_tests_passed=True,
                claimed_hidden_tests_passed=True,
            )
        ),
        ingest_agent_run_artifact(
            _artifact(
                run_id="modest",
                diff_text=BUGFIX_005_GOOD_PATCH,
                claimed_public_tests_passed=False,
                claimed_hidden_tests_passed=False,
            )
        ),
    ]
    results = verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    liar, modest = results
    # Liar claimed pass but really fails.
    assert liar.passed_public_tests is False
    assert liar.passed_hidden_tests is False
    # Modest claimed fail but really passes.
    assert modest.passed_public_tests is True
    assert modest.passed_hidden_tests is True


def test_original_fixture_is_not_mutated(tmp_path: Path):
    task, layout = _bugfix_005()
    original = REPO_ROOT / task.repo_path / "is_within_range.py"
    snapshot = original.read_bytes()

    ingested_runs = [
        ingest_agent_run_artifact(_artifact(run_id="a")),
        ingest_agent_run_artifact(
            _artifact(run_id="b", diff_text=BUGFIX_005_SEMANTICALLY_WRONG_PATCH)
        ),
    ]
    verify_ingested_agent_runs(
        {task.task_id: task},
        ingested_runs,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )
    assert original.read_bytes() == snapshot


def test_batch_does_not_mutate_inputs(tmp_path: Path):
    task, layout = _bugfix_005()
    artifact = _artifact(claimed_commands=["pytest"], metadata={"k": "v"})
    ingested = ingest_agent_run_artifact(artifact)
    snapshot_commands = list(artifact.claimed_commands)
    snapshot_metadata = dict(artifact.metadata)

    verify_ingested_agent_runs(
        {task.task_id: task},
        [ingested],
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert artifact.claimed_commands == snapshot_commands
    assert artifact.metadata == snapshot_metadata


# ---- argument-shape errors -------------------------------------------------


def test_non_dict_tasks_raises(tmp_path: Path):
    with pytest.raises(AgentRunVerificationError, match="tasks_by_id"):
        verify_ingested_agent_runs(
            [("t", None)],  # type: ignore[arg-type]
            [],
            {},
            workspace_root=tmp_path,
        )


def test_non_dict_layouts_raises(tmp_path: Path):
    with pytest.raises(AgentRunVerificationError, match="layouts_by_task_id"):
        verify_ingested_agent_runs(
            {}, [], [], workspace_root=tmp_path  # type: ignore[arg-type]
        )


def test_non_list_runs_raises(tmp_path: Path):
    task, layout = _bugfix_005()
    with pytest.raises(AgentRunVerificationError, match="ingested_runs"):
        verify_ingested_agent_runs(
            {task.task_id: task},
            ingest_agent_run_artifact(_artifact()),  # type: ignore[arg-type]
            {task.task_id: layout},
            workspace_root=tmp_path,
        )


def test_empty_batch_returns_empty_list(tmp_path: Path):
    assert (
        verify_ingested_agent_runs({}, [], {}, workspace_root=tmp_path) == []
    )


# ---- verify_agent_run_artifacts convenience helper -------------------------


def test_convenience_helper_works(tmp_path: Path):
    task, layout = _bugfix_005()
    results = verify_agent_run_artifacts(
        {task.task_id: task},
        [_artifact(run_id="r1"), _artifact(run_id="r2")],
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert len(results) == 2
    for result in results:
        assert result.passed_public_tests is True
        assert result.passed_hidden_tests is True
        assert WeaknessCode.VERIFY not in result.weaknesses


def test_convenience_helper_lenient_handles_bad_ingest(tmp_path: Path):
    task, layout = _bugfix_005()
    good = _artifact(run_id="good")
    bad = _artifact(run_id="bad")
    bad.agent_name = ""  # makes ingestion fail

    results = verify_agent_run_artifacts(
        {task.task_id: task},
        [good, bad],
        {task.task_id: layout},
        workspace_root=tmp_path,
    )

    assert len(results) == 2
    assert results[0].passed_public_tests is True
    assert results[1].passed_public_tests is False
    assert "ingestion error" in results[1].rationale.lower()


def test_convenience_helper_strict_raises_on_bad_ingest(tmp_path: Path):
    task, layout = _bugfix_005()
    bad = _artifact(run_id="bad")
    bad.agent_name = ""

    with pytest.raises(AgentRunVerificationError, match="ingest"):
        verify_agent_run_artifacts(
            {task.task_id: task},
            [bad],
            {task.task_id: layout},
            workspace_root=tmp_path,
            continue_on_error=False,
        )


def test_convenience_helper_preserves_order(tmp_path: Path):
    task, layout = _bugfix_005()
    artifacts = [
        _artifact(run_id="r-z"),
        _artifact(run_id="r-a"),
        _artifact(run_id="r-m"),
    ]
    results = verify_agent_run_artifacts(
        {task.task_id: task},
        artifacts,
        {task.task_id: layout},
        workspace_root=tmp_path,
    )
    assert [r.run_id for r in results] == ["r-z", "r-a", "r-m"]


def test_convenience_helper_non_list_artifacts_raises(tmp_path: Path):
    with pytest.raises(AgentRunVerificationError, match="artifacts"):
        verify_agent_run_artifacts(
            {}, _artifact(), {}, workspace_root=tmp_path  # type: ignore[arg-type]
        )
