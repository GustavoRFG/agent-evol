"""Apply a candidate unified diff inside an isolated workspace copy.

This module is the final piece of the controlled-execution pipeline:
:mod:`agenteval.execution.pytest_harness` copies a fixture and runs tests
on it; this module additionally applies a unified diff to the *copied*
workspace and lets the caller re-run the tests against the patched code.

Boundaries observed by this module:
- No agent is invoked, no API is called, no network access happens.
- Patches are applied **only** inside the copied workspace path; the
  original fixture directory is never used as the patch target.
- Diff paths are sanitized against ``..``, absolute paths and empty
  segments before ``git apply`` is invoked.
- ``git apply`` runs with ``--whitespace=nowarn`` and reads the diff from
  stdin so no temporary file is left on disk.
- Standard library only (``dataclasses``, ``os``, ``subprocess``).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from agenteval.core.schemas import TaskSpec
from agenteval.execution.pytest_harness import (
    PytestRunResult,
    copy_fixture_to_workspace,
    run_pytest_nodes_in_workspace,
)
from agenteval.fixtures import TaskFixtureLayout
from agenteval.patches.diff_summary import parse_unified_diff

if TYPE_CHECKING:  # pragma: no cover - import-time hint only
    from agenteval.evaluation.batch_builder import TaskEvidence


class PatchApplyError(RuntimeError):
    """Raised when a candidate diff cannot be applied to a workspace.

    Reserved for *application-level* failures: an empty diff, a missing
    workspace, an unsafe path inside the diff, a ``git apply`` exit with
    a non-zero code, a subprocess launch failure, or a timeout.
    """


@dataclass
class PatchApplyResult:
    """Structured outcome of one ``git apply`` invocation."""

    applied: bool = False
    changed_files: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    workspace_path: str = ""


def _diff_paths(diff_text: str) -> list[str]:
    """Return all file paths touched by ``diff_text`` (changed/added/deleted).

    Order mirrors ``parse_unified_diff`` (deterministic, no duplicates).
    """
    summary = parse_unified_diff(diff_text)
    seen: set[str] = set()
    ordered: list[str] = []
    for path in (
        *summary.changed_files,
        *summary.added_files,
        *summary.deleted_files,
    ):
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _refuse_unsafe_paths(paths: list[str]) -> None:
    """Reject diffs whose paths could escape the workspace root."""
    for path in paths:
        if not path:
            raise PatchApplyError(
                "Diff contains an empty file path; refusing to apply."
            )
        if os.path.isabs(path):
            raise PatchApplyError(
                f"Diff path is absolute, refusing to apply outside workspace: "
                f"{path!r}"
            )
        normalized = path.replace("\\", "/")
        parts = [segment for segment in normalized.split("/") if segment]
        if ".." in parts:
            raise PatchApplyError(
                f"Diff path escapes the workspace via '..': {path!r}"
            )


def apply_patch_to_workspace(
    *,
    workspace_path: str | Path,
    diff_text: str,
    timeout_seconds: int = 30,
) -> PatchApplyResult:
    """Apply ``diff_text`` to ``workspace_path`` via ``git apply``.

    ``workspace_path`` is the caller-prepared (typically copied) fixture
    directory. The diff is fed to ``git apply --whitespace=nowarn -`` over
    stdin with ``cwd=workspace_path`` so no temporary file is needed and
    every change is rooted in the workspace.

    Args:
        workspace_path: Directory the patch should be applied inside.
        diff_text: Unified-diff text to apply (must not be empty).
        timeout_seconds: ``git apply`` subprocess timeout.

    Returns:
        A :class:`PatchApplyResult` with ``applied=True`` on success.

    Raises:
        PatchApplyError: If the workspace is missing, the diff is empty
            or unsafe, ``git apply`` exits non-zero, the subprocess fails
            to launch, or the call times out.
    """
    workspace = Path(workspace_path)
    if not workspace.is_dir():
        raise PatchApplyError(
            f"Workspace path does not exist or is not a directory: {workspace}"
        )

    if not diff_text or not diff_text.strip():
        raise PatchApplyError(
            "Cannot apply an empty or whitespace-only diff."
        )

    changed_files = _diff_paths(diff_text)
    _refuse_unsafe_paths(changed_files)

    command = ["git", "apply", "--whitespace=nowarn", "-"]
    # The diff is passed as **bytes** so Python's text-mode wrapper does not
    # translate ``\n`` into ``\r\n`` on Windows. ``git apply`` matches the
    # patch byte-for-byte against the workspace file, and any newline
    # translation breaks the hunk match. ``stdout``/``stderr`` are captured
    # as bytes for the same reason and decoded manually below.
    try:
        completed = subprocess.run(
            command,
            cwd=str(workspace),
            input=diff_text.encode("utf-8"),
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PatchApplyError(
            f"git apply timed out after {timeout_seconds}s in {workspace}."
        ) from exc
    except OSError as exc:
        raise PatchApplyError(
            f"Failed to launch git apply in {workspace}: {exc}"
        ) from exc

    stdout_text = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr_text = (completed.stderr or b"").decode("utf-8", errors="replace")

    if completed.returncode != 0:
        raise PatchApplyError(
            f"git apply exited with code {completed.returncode} in "
            f"{workspace}.\nstdout: {stdout_text!r}\n"
            f"stderr: {stderr_text!r}"
        )

    return PatchApplyResult(
        applied=True,
        changed_files=changed_files,
        stdout=stdout_text,
        stderr=stderr_text,
        command=command,
        workspace_path=str(workspace),
    )


def copy_fixture_apply_patch_and_run_tests(
    *,
    task: TaskSpec,
    layout: TaskFixtureLayout,
    diff_text: str,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
) -> tuple[PatchApplyResult, PytestRunResult, PytestRunResult]:
    """End-to-end "copy → patch → public → hidden" in one workspace.

    Avoids the double-copy that would happen if the caller used
    :func:`run_task_tests` after :func:`apply_patch_to_workspace`: the
    fixture is copied once and both pytest invocations reuse the same
    patched workspace via :func:`run_pytest_nodes_in_workspace`.
    """
    workspace = copy_fixture_to_workspace(layout, workspace_root)
    patch_result = apply_patch_to_workspace(
        workspace_path=workspace,
        diff_text=diff_text,
        timeout_seconds=timeout_seconds,
    )
    public_result = run_pytest_nodes_in_workspace(
        task_id=task.task_id,
        node_ids=task.public_tests,
        test_kind="public",
        workspace_path=workspace,
        timeout_seconds=timeout_seconds,
    )
    hidden_result = run_pytest_nodes_in_workspace(
        task_id=task.task_id,
        node_ids=task.hidden_tests,
        test_kind="hidden",
        workspace_path=workspace,
        timeout_seconds=timeout_seconds,
    )
    return patch_result, public_result, hidden_result


def copy_fixture_apply_patch_and_build_evidence(
    *,
    task: TaskSpec,
    layout: TaskFixtureLayout,
    diff_text: str,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    final_message: str = "",
) -> "TaskEvidence":
    """Run "copy -> patch -> public -> hidden" and summarize as :class:`TaskEvidence`.

    Convenience wrapper over :func:`copy_fixture_apply_patch_and_run_tests`
    that forwards the two :class:`PytestRunResult` objects through
    :func:`build_task_evidence_from_pytest_results`. ``diff_text`` is
    preserved on the returned evidence so downstream code can attach it as
    patch evidence.
    """
    # Local import to break the import cycle:
    # ``agenteval.evaluation`` imports from ``agenteval.execution`` via
    # ``test_evidence``; if this helper imported ``test_evidence`` at module
    # scope, ``execution/__init__`` would in turn re-enter a half-loaded
    # ``evaluation`` package during import.
    from agenteval.evaluation.test_evidence import (
        build_task_evidence_from_pytest_results,
    )

    _patch_result, public_result, hidden_result = (
        copy_fixture_apply_patch_and_run_tests(
            task=task,
            layout=layout,
            diff_text=diff_text,
            workspace_root=workspace_root,
            timeout_seconds=timeout_seconds,
        )
    )
    return build_task_evidence_from_pytest_results(
        public_result=public_result,
        hidden_result=hidden_result,
        diff_text=diff_text,
        final_message=final_message,
    )
