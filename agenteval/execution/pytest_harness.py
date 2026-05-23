"""Run a benchmark task's pytest node IDs in an isolated workspace copy.

The harness exists so AgentEval Forge can turn a test run into structured
evidence (``PytestRunResult``) without mutating the original fixture and
without invoking any coding agent. It only knows how to copy a fixture to a
fresh workspace directory and invoke ``python -m pytest`` against the node
IDs declared by a :class:`TaskSpec`.

Boundaries observed by this module:
- No patches are applied — the fixture is copied verbatim.
- No coding agent or external API is called.
- Tests in the original fixture directory are never executed.
- Standard library only (``dataclasses``, ``shutil``, ``subprocess``, ``sys``).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agenteval.core.schemas import TaskSpec
from agenteval.fixtures import TaskFixtureLayout

_VALID_TEST_KINDS = ("public", "hidden")


class TestHarnessError(RuntimeError):
    """Raised when the harness itself cannot run a pytest invocation.

    Reserved for *harness-level* failures: an invalid ``test_kind``, an empty
    node-ID list, a copy that overwrites an existing workspace, a subprocess
    launch error, or a pytest timeout. A failing test is not a harness
    failure — it is valid evidence and is returned as a
    :class:`PytestRunResult` with ``passed=False``.
    """

    # Tell pytest not to collect this exception class as a test container —
    # its name starts with ``Test`` purely for naming consistency.
    __test__ = False


@dataclass
class PytestRunResult:
    """Structured outcome of one pytest invocation against a fixture copy.

    ``passed`` mirrors ``exit_code == 0`` so callers do not have to interpret
    pytest's exit codes themselves. ``workspace_path`` is the *copied*
    fixture directory the run executed in — the original fixture on disk is
    never used as the working directory.
    """

    task_id: str
    test_kind: str
    node_ids: list[str] = field(default_factory=list)
    passed: bool = False
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    workspace_path: str = ""


def copy_fixture_to_workspace(
    layout: TaskFixtureLayout,
    workspace_root: str | Path,
) -> Path:
    """Copy a fixture repo into a fresh directory under ``workspace_root``.

    The destination is ``workspace_root / "fixture_<task_id>"``. The original
    fixture directory is never mutated.

    Args:
        layout: A resolved :class:`TaskFixtureLayout` whose ``repo_path``
            points at the on-disk fixture to copy.
        workspace_root: Parent directory for the workspace copy. Created if
            it does not yet exist.

    Returns:
        The path of the freshly copied fixture directory.

    Raises:
        TestHarnessError: If the destination already exists or ``shutil``
            cannot copy the tree.
    """
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"fixture_{layout.task_id}"

    if destination.exists():
        raise TestHarnessError(
            f"Workspace destination already exists for task "
            f"'{layout.task_id}': {destination}"
        )

    try:
        shutil.copytree(layout.repo_path, destination)
    except OSError as exc:
        raise TestHarnessError(
            f"Failed to copy fixture for task '{layout.task_id}' "
            f"from {layout.repo_path} to {destination}: {exc}"
        ) from exc

    return destination


def run_pytest_nodes(
    *,
    task: TaskSpec,
    layout: TaskFixtureLayout,
    node_ids: list[str],
    test_kind: str,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
) -> PytestRunResult:
    """Run a list of pytest node IDs in a fresh copy of the fixture.

    The fixture is first copied via :func:`copy_fixture_to_workspace` so the
    original is never used as a working directory. Each declared node ID is
    interpreted relative to the copied fixture root. ``python -m pytest`` is
    invoked using ``sys.executable`` (so it always matches the active
    interpreter), with stdout, stderr, exit code, and the full command line
    captured into the returned :class:`PytestRunResult`.

    Failing tests are *not* harness failures: they return a result with
    ``passed=False`` and a non-zero ``exit_code``. The harness only raises
    :class:`TestHarnessError` for harness-level problems (invalid kind,
    empty node list, copy failure, subprocess launch failure, timeout).

    The workspace copy is intentionally left on disk so callers can inspect
    it; pass a ``tmp_path`` so pytest cleans it up automatically.
    """
    if test_kind not in _VALID_TEST_KINDS:
        raise TestHarnessError(
            f"Invalid test_kind '{test_kind}'; expected one of "
            f"{_VALID_TEST_KINDS}."
        )
    if not node_ids:
        raise TestHarnessError(
            f"No {test_kind} test node IDs provided for task "
            f"'{task.task_id}'; cannot run pytest with an empty selection."
        )

    workspace = copy_fixture_to_workspace(layout, workspace_root)

    command = [sys.executable, "-m", "pytest", *list(node_ids)]

    try:
        completed = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TestHarnessError(
            f"pytest timed out after {timeout_seconds}s while running "
            f"{test_kind} tests for task '{task.task_id}' in {workspace}."
        ) from exc
    except OSError as exc:
        raise TestHarnessError(
            f"Failed to launch pytest for task '{task.task_id}' in "
            f"{workspace}: {exc}"
        ) from exc

    return PytestRunResult(
        task_id=task.task_id,
        test_kind=test_kind,
        node_ids=list(node_ids),
        passed=completed.returncode == 0,
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        command=command,
        workspace_path=str(workspace),
    )


def run_public_tests(
    task: TaskSpec,
    layout: TaskFixtureLayout,
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
) -> PytestRunResult:
    """Run the task's declared public tests in a fresh fixture copy."""
    return run_pytest_nodes(
        task=task,
        layout=layout,
        node_ids=task.public_tests,
        test_kind="public",
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
    )


def run_hidden_tests(
    task: TaskSpec,
    layout: TaskFixtureLayout,
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
) -> PytestRunResult:
    """Run the task's declared hidden tests in a fresh fixture copy."""
    return run_pytest_nodes(
        task=task,
        layout=layout,
        node_ids=task.hidden_tests,
        test_kind="hidden",
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
    )


def run_task_tests(
    task: TaskSpec,
    layout: TaskFixtureLayout,
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
) -> tuple[PytestRunResult, PytestRunResult]:
    """Run public and hidden tests in two separate fixture copies.

    Each kind runs in its own sub-directory of ``workspace_root`` so the two
    invocations cannot interfere via leftover state on disk and so neither
    copy collides with the other when :func:`copy_fixture_to_workspace`
    creates ``fixture_<task_id>``. Returns ``(public_result, hidden_result)``
    in that order.
    """
    root = Path(workspace_root)
    public_result = run_public_tests(
        task,
        layout,
        workspace_root=root / "public",
        timeout_seconds=timeout_seconds,
    )
    hidden_result = run_hidden_tests(
        task,
        layout,
        workspace_root=root / "hidden",
        timeout_seconds=timeout_seconds,
    )
    return public_result, hidden_result
