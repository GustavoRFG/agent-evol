"""Tests for ``agenteval.execution.patch_workspace``.

These tests exercise three things:

1. The error contract of :func:`apply_patch_to_workspace` — empty diff,
   missing workspace, unsafe paths, invalid patch.
2. A real end-to-end "copy → patch → re-run tests" against the shipped
   ``bugfix_005`` fixture, using a hand-written unified diff that fixes
   the strict-inequality bug.
3. The convenience helper that converts the patched test outcome into
   :class:`TaskEvidence`.

No agent is invoked, no API is called. The original fixture directory is
never used as the patch target — every test patches a tmp_path copy.
"""

from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import WeaknessCode
from agenteval.evaluation import TaskEvidence
from agenteval.execution import (
    PatchApplyError,
    PatchApplyResult,
    PytestRunResult,
    apply_patch_to_workspace,
    copy_fixture_apply_patch_and_build_evidence,
    copy_fixture_apply_patch_and_run_tests,
    copy_fixture_to_workspace,
)
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


# --- error contract -------------------------------------------------------


def test_empty_diff_raises(tmp_path: Path):
    (tmp_path / "ws").mkdir()
    with pytest.raises(PatchApplyError):
        apply_patch_to_workspace(workspace_path=tmp_path / "ws", diff_text="")


def test_whitespace_only_diff_raises(tmp_path: Path):
    (tmp_path / "ws").mkdir()
    with pytest.raises(PatchApplyError):
        apply_patch_to_workspace(
            workspace_path=tmp_path / "ws", diff_text="   \n\t\n"
        )


def test_missing_workspace_raises(tmp_path: Path):
    with pytest.raises(PatchApplyError):
        apply_patch_to_workspace(
            workspace_path=tmp_path / "nope",
            diff_text=BUGFIX_005_GOOD_PATCH,
        )


def test_workspace_must_be_a_directory(tmp_path: Path):
    file_target = tmp_path / "not_a_dir"
    file_target.write_text("file, not directory", encoding="utf-8")
    with pytest.raises(PatchApplyError):
        apply_patch_to_workspace(
            workspace_path=file_target, diff_text=BUGFIX_005_GOOD_PATCH
        )


def test_invalid_patch_raises_apply_error(tmp_path: Path):
    _task, layout = _bugfix_005()
    workspace = copy_fixture_to_workspace(layout, tmp_path)
    with pytest.raises(PatchApplyError) as exc_info:
        apply_patch_to_workspace(
            workspace_path=workspace, diff_text=BUGFIX_005_BROKEN_PATCH
        )
    assert "git apply" in str(exc_info.value)


def test_diff_with_absolute_path_is_refused(tmp_path: Path):
    (tmp_path / "ws").mkdir()
    bad_diff = (
        "diff --git a//etc/passwd b//etc/passwd\n"
        "--- a//etc/passwd\n"
        "+++ b//etc/passwd\n"
        "@@ -1 +1 @@\n"
        "-x\n+y\n"
    )
    with pytest.raises(PatchApplyError) as exc_info:
        apply_patch_to_workspace(
            workspace_path=tmp_path / "ws", diff_text=bad_diff
        )
    assert "absolute" in str(exc_info.value).lower() or "unsafe" in str(
        exc_info.value
    ).lower()


def test_diff_with_parent_escape_is_refused(tmp_path: Path):
    (tmp_path / "ws").mkdir()
    bad_diff = (
        "diff --git a/../escape.py b/../escape.py\n"
        "--- a/../escape.py\n"
        "+++ b/../escape.py\n"
        "@@ -1 +1 @@\n"
        "-x\n+y\n"
    )
    with pytest.raises(PatchApplyError) as exc_info:
        apply_patch_to_workspace(
            workspace_path=tmp_path / "ws", diff_text=bad_diff
        )
    assert ".." in str(exc_info.value)


# --- happy path against the shipped bugfix_005 fixture -------------------


def test_good_patch_applies_to_copied_bugfix_005(tmp_path: Path):
    _task, layout = _bugfix_005()
    workspace = copy_fixture_to_workspace(layout, tmp_path)

    result = apply_patch_to_workspace(
        workspace_path=workspace, diff_text=BUGFIX_005_GOOD_PATCH
    )

    assert isinstance(result, PatchApplyResult)
    assert result.applied is True
    assert "is_within_range.py" in result.changed_files
    assert result.command[0:3] == ["git", "apply", "--whitespace=nowarn"]
    assert result.workspace_path == str(workspace)

    patched_source = (workspace / "is_within_range.py").read_text(
        encoding="utf-8"
    )
    assert "low <= value <= high" in patched_source
    assert "low < value < high" not in patched_source


def test_apply_does_not_mutate_original_fixture(tmp_path: Path):
    _task, layout = _bugfix_005()
    original_text = (layout.repo_path / "is_within_range.py").read_text(
        encoding="utf-8"
    )

    workspace = copy_fixture_to_workspace(layout, tmp_path)
    apply_patch_to_workspace(
        workspace_path=workspace, diff_text=BUGFIX_005_GOOD_PATCH
    )

    after_text = (layout.repo_path / "is_within_range.py").read_text(
        encoding="utf-8"
    )
    assert after_text == original_text
    assert "low < value < high" in after_text


def test_failing_patch_does_not_mutate_original_fixture(tmp_path: Path):
    _task, layout = _bugfix_005()
    original_text = (layout.repo_path / "is_within_range.py").read_text(
        encoding="utf-8"
    )

    workspace = copy_fixture_to_workspace(layout, tmp_path)
    with pytest.raises(PatchApplyError):
        apply_patch_to_workspace(
            workspace_path=workspace, diff_text=BUGFIX_005_BROKEN_PATCH
        )

    after_text = (layout.repo_path / "is_within_range.py").read_text(
        encoding="utf-8"
    )
    assert after_text == original_text


# --- copy + patch + run tests --------------------------------------------


def test_copy_patch_and_run_tests_flips_hidden_to_pass(tmp_path: Path):
    task, layout = _bugfix_005()

    patch_result, public_result, hidden_result = (
        copy_fixture_apply_patch_and_run_tests(
            task=task,
            layout=layout,
            diff_text=BUGFIX_005_GOOD_PATCH,
            workspace_root=tmp_path,
        )
    )

    assert isinstance(patch_result, PatchApplyResult)
    assert patch_result.applied is True
    assert isinstance(public_result, PytestRunResult)
    assert isinstance(hidden_result, PytestRunResult)

    # Public tests already passed before patching; they must still pass.
    assert public_result.passed is True
    # The whole point of the patch: hidden tests now pass too.
    assert hidden_result.passed is True
    assert hidden_result.exit_code == 0

    # Both pytest runs reused the same patched workspace (no double-copy).
    assert public_result.workspace_path == hidden_result.workspace_path
    assert public_result.workspace_path == patch_result.workspace_path


# --- evidence helper -----------------------------------------------------


def test_evidence_helper_produces_clean_pass_for_good_patch(tmp_path: Path):
    task, layout = _bugfix_005()

    evidence = copy_fixture_apply_patch_and_build_evidence(
        task=task,
        layout=layout,
        diff_text=BUGFIX_005_GOOD_PATCH,
        workspace_root=tmp_path,
        final_message="Applied inclusive-bounds fix for bugfix_005.",
    )

    assert isinstance(evidence, TaskEvidence)
    assert evidence.passed_public_tests is True
    assert evidence.passed_hidden_tests is True
    # With both buckets green the weakness list must be empty.
    assert evidence.weaknesses == []
    # Confirm a few existing codes are absent — i.e. the green path really
    # does *not* attach LAZY/ROOT just because the helper has access to them.
    assert WeaknessCode.LAZY not in evidence.weaknesses
    assert WeaknessCode.ROOT not in evidence.weaknesses
    assert evidence.diff_text == BUGFIX_005_GOOD_PATCH
    assert "inclusive-bounds fix" in evidence.final_message
