"""Tests for verifying ingested external agent artifacts.

Verification: copy fixture -> apply diff -> run public + hidden tests -> build
a real :class:`EvaluationResult`. The original fixture is never patched.
"""

from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunVerificationError,
    ingest_agent_run_artifact,
    verify_agent_run_artifact,
    verify_ingested_agent_run,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import EvaluationResult, WeaknessCode
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

BUGFIX_005_BROKEN_PATCH = '''\
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
    task_id: str = "bugfix_005",
    diff_text: str = BUGFIX_005_GOOD_PATCH,
    final_message: str = "Replaced strict inequalities with inclusive ones.",
    **overrides,
) -> AgentRunArtifact:
    return AgentRunArtifact(
        agent_name="claude-code",
        task_id=task_id,
        run_id=f"claude-code:{task_id}:001",
        diff_text=diff_text,
        final_message=final_message,
        **overrides,
    )


# ---- successful verification path ------------------------------------------


def test_correct_patch_produces_verified_evaluation_result(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())

    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )

    assert isinstance(result, EvaluationResult)
    assert result.task_id == "bugfix_005"
    assert result.run_id == "claude-code:bugfix_005:001"


def test_verified_result_passes_public_tests(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    assert result.passed_public_tests is True


def test_verified_result_passes_hidden_tests(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    assert result.passed_hidden_tests is True


def test_verified_result_has_no_weaknesses(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    assert result.weaknesses == []


def test_verified_result_does_not_include_verify_weakness(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    assert WeaknessCode.VERIFY not in result.weaknesses


def test_verified_result_has_high_score(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    assert result.score >= 0.9


def test_verified_result_preserves_diff_text(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    assert result.patch_summary is not None
    assert result.patch_summary.diff_text == BUGFIX_005_GOOD_PATCH


def test_verified_result_patch_summary_includes_target_file(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact())
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    assert result.patch_summary is not None
    assert "is_within_range.py" in result.patch_summary.changed_files


# ---- agent claims are not trusted ------------------------------------------


def test_claimed_public_false_does_not_block_verified_pass(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(
        _artifact(claimed_public_tests_passed=False)
    )
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    # Real test outcome wins over the agent's claim.
    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is True


def test_claimed_public_true_alone_does_not_produce_pass(tmp_path: Path):
    task, layout = _bugfix_005()
    # Use a syntactically valid but semantically wrong patch: replace `<`
    # with `==` so the function compiles but the tests fail.
    wrong_patch = (
        "diff --git a/is_within_range.py b/is_within_range.py\n"
        "--- a/is_within_range.py\n"
        "+++ b/is_within_range.py\n"
        "@@ -12,4 +12,4 @@ def is_within_range(value, low, high):\n"
        "     The function should be inclusive on both bounds, but currently uses\n"
        "     strict inequalities.\n"
        '     """\n'
        "-    return low < value < high\n"
        "+    return low == value == high\n"
    )
    ingested = ingest_agent_run_artifact(
        _artifact(
            diff_text=wrong_patch,
            claimed_public_tests_passed=True,
            claimed_hidden_tests_passed=True,
        )
    )
    result = verify_ingested_agent_run(
        task, ingested, layout, workspace_root=tmp_path
    )
    # Even though the agent claimed both passed, real tests fail.
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    # And the score is not high.
    assert result.score < 0.9


# ---- error contract --------------------------------------------------------


def test_task_id_mismatch_raises(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact(task_id="bugfix_001"))
    with pytest.raises(AgentRunVerificationError, match="task_id mismatch"):
        verify_ingested_agent_run(task, ingested, layout, workspace_root=tmp_path)


def test_empty_diff_text_raises(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact(diff_text=""))
    with pytest.raises(AgentRunVerificationError, match="empty diff_text"):
        verify_ingested_agent_run(task, ingested, layout, workspace_root=tmp_path)


def test_whitespace_diff_text_raises(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(_artifact(diff_text="   \n\t"))
    with pytest.raises(AgentRunVerificationError, match="empty diff_text"):
        verify_ingested_agent_run(task, ingested, layout, workspace_root=tmp_path)


def test_invalid_patch_raises(tmp_path: Path):
    task, layout = _bugfix_005()
    ingested = ingest_agent_run_artifact(
        _artifact(diff_text=BUGFIX_005_BROKEN_PATCH)
    )
    with pytest.raises(AgentRunVerificationError, match="failed to apply patch"):
        verify_ingested_agent_run(task, ingested, layout, workspace_root=tmp_path)


def test_non_ingested_input_raises(tmp_path: Path):
    task, layout = _bugfix_005()
    with pytest.raises(AgentRunVerificationError, match="IngestedAgentRun"):
        verify_ingested_agent_run(
            task, "not ingested", layout, workspace_root=tmp_path  # type: ignore[arg-type]
        )


# ---- original-fixture immutability -----------------------------------------


def test_original_fixture_file_is_not_mutated(tmp_path: Path):
    task, layout = _bugfix_005()
    original = REPO_ROOT / task.repo_path / "is_within_range.py"
    snapshot = original.read_bytes()

    ingested = ingest_agent_run_artifact(_artifact())
    verify_ingested_agent_run(task, ingested, layout, workspace_root=tmp_path)

    assert original.read_bytes() == snapshot
    # Sanity: the original still contains the buggy strict inequality.
    assert "low < value < high" in snapshot.decode("utf-8")


# ---- input-immutability ----------------------------------------------------


def test_verify_does_not_mutate_inputs(tmp_path: Path):
    task, layout = _bugfix_005()
    artifact = _artifact(
        claimed_commands=["pytest"],
        metadata={"k": "v"},
    )
    ingested = ingest_agent_run_artifact(artifact)
    snapshot_commands = list(artifact.claimed_commands)
    snapshot_metadata = dict(artifact.metadata)
    snapshot_layout_repo = layout.repo_path

    verify_ingested_agent_run(task, ingested, layout, workspace_root=tmp_path)

    assert artifact.claimed_commands == snapshot_commands
    assert artifact.metadata == snapshot_metadata
    assert layout.repo_path == snapshot_layout_repo


# ---- verify_agent_run_artifact convenience helper --------------------------


def test_verify_agent_run_artifact_helper_works(tmp_path: Path):
    task, layout = _bugfix_005()
    result = verify_agent_run_artifact(
        task, _artifact(), layout, workspace_root=tmp_path
    )

    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is True
    assert WeaknessCode.VERIFY not in result.weaknesses
    assert result.score >= 0.9


def test_verify_agent_run_artifact_helper_rejects_invalid_artifact(tmp_path: Path):
    task, layout = _bugfix_005()
    bad = _artifact()
    bad.agent_name = ""

    with pytest.raises(AgentRunVerificationError, match="ingest"):
        verify_agent_run_artifact(task, bad, layout, workspace_root=tmp_path)
