"""Tests for the controlled pytest execution harness.

The harness invokes ``python -m pytest`` in a subprocess against an isolated
copy of a benchmark fixture. These tests exercise the harness end-to-end
against the shipped ``python_bugfix_basic`` fixtures (``bugfix_005`` is the
key fixture here because its public tests pass on the broken implementation
while its hidden tests fail).

Boundaries: no agent is invoked, no patch is applied, no fixture source is
mutated. The original fixture directories are never used as cwd.
"""

from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import BenchmarkPack, TaskSpec
from agenteval.execution import (
    PytestRunResult,
    TestHarnessError,
    copy_fixture_to_workspace,
    run_hidden_tests,
    run_public_tests,
    run_pytest_nodes,
    run_task_tests,
)
from agenteval.fixtures import (
    TaskFixtureLayout,
    resolve_task_fixture_layout,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"


@pytest.fixture(scope="module")
def pack() -> BenchmarkPack:
    return load_benchmark_pack(PACK_DIR)


def _task(pack: BenchmarkPack, task_id: str) -> TaskSpec:
    for task in pack.tasks:
        if task.task_id == task_id:
            return task
    raise AssertionError(f"Task '{task_id}' missing from pack '{pack.name}'.")


def _layout(pack: BenchmarkPack, task_id: str) -> TaskFixtureLayout:
    return resolve_task_fixture_layout(
        _task(pack, task_id), project_root=REPO_ROOT
    )


# --- copy_fixture_to_workspace --------------------------------------------


def test_copy_fixture_to_workspace_copies_bugfix_005(
    pack: BenchmarkPack, tmp_path: Path
):
    layout = _layout(pack, "bugfix_005")
    destination = copy_fixture_to_workspace(layout, tmp_path)

    assert destination.is_dir()
    assert destination.parent == tmp_path
    assert "bugfix_005" in destination.name
    # Expected files present in the copy.
    assert (destination / "README.md").is_file()
    assert (destination / "is_within_range.py").is_file()
    assert (destination / "tests" / "test_is_within_range.py").is_file()
    assert (
        destination / "tests" / "test_is_within_range_hidden.py"
    ).is_file()


def test_copy_fixture_does_not_mutate_original(
    pack: BenchmarkPack, tmp_path: Path
):
    layout = _layout(pack, "bugfix_005")
    original_files = sorted(
        p.relative_to(layout.repo_path).as_posix()
        for p in layout.repo_path.rglob("*")
        if "__pycache__" not in p.parts
    )
    original_source = (layout.repo_path / "is_within_range.py").read_text(
        encoding="utf-8"
    )

    copy_fixture_to_workspace(layout, tmp_path)

    after_files = sorted(
        p.relative_to(layout.repo_path).as_posix()
        for p in layout.repo_path.rglob("*")
        if "__pycache__" not in p.parts
    )
    after_source = (layout.repo_path / "is_within_range.py").read_text(
        encoding="utf-8"
    )
    assert original_files == after_files
    assert original_source == after_source


def test_copy_fixture_raises_when_destination_exists(
    pack: BenchmarkPack, tmp_path: Path
):
    layout = _layout(pack, "bugfix_005")
    copy_fixture_to_workspace(layout, tmp_path)
    with pytest.raises(TestHarnessError):
        copy_fixture_to_workspace(layout, tmp_path)


# --- run_public_tests / run_hidden_tests ----------------------------------


def test_run_public_tests_passes_for_bugfix_005(
    pack: BenchmarkPack, tmp_path: Path
):
    # bugfix_005's broken implementation still satisfies the public tests
    # (strictly inside / strictly outside cases), so the public run passes
    # even before any patch is applied.
    task = _task(pack, "bugfix_005")
    layout = _layout(pack, "bugfix_005")

    result = run_public_tests(task, layout, workspace_root=tmp_path)

    assert isinstance(result, PytestRunResult)
    assert result.task_id == "bugfix_005"
    assert result.test_kind == "public"
    assert result.node_ids == list(task.public_tests)
    assert result.passed is True
    assert result.exit_code == 0
    assert result.workspace_path
    # Workspace lives under the requested root, not the original fixture.
    assert Path(result.workspace_path).is_dir()
    assert Path(result.workspace_path).parent == tmp_path
    # Pytest produced some output.
    assert "passed" in (result.stdout + result.stderr).lower()


def test_run_hidden_tests_fails_for_bugfix_005(
    pack: BenchmarkPack, tmp_path: Path
):
    # The hidden tests for bugfix_005 cover the boundary-inclusivity cases
    # that the broken implementation gets wrong, so the hidden run must
    # report failure without raising a harness error.
    task = _task(pack, "bugfix_005")
    layout = _layout(pack, "bugfix_005")

    result = run_hidden_tests(task, layout, workspace_root=tmp_path)

    assert isinstance(result, PytestRunResult)
    assert result.task_id == "bugfix_005"
    assert result.test_kind == "hidden"
    assert result.passed is False
    assert result.exit_code != 0
    # Failing tests still produce pytest output.
    combined = result.stdout + result.stderr
    assert combined.strip(), "Expected pytest to produce output on failure."


def test_failing_run_does_not_raise(pack: BenchmarkPack, tmp_path: Path):
    # Explicit guarantee: a failing test run is *evidence*, not a harness
    # failure — the helper must return a PytestRunResult, not raise.
    task = _task(pack, "bugfix_005")
    layout = _layout(pack, "bugfix_005")

    result = run_hidden_tests(task, layout, workspace_root=tmp_path)

    assert result.passed is False
    assert result.exit_code != 0
    assert not isinstance(result, BaseException)


# --- command shape and node-id forwarding ---------------------------------


def test_command_uses_sys_executable_and_python_dash_m_pytest(
    pack: BenchmarkPack, tmp_path: Path
):
    import sys as _sys

    task = _task(pack, "bugfix_005")
    layout = _layout(pack, "bugfix_005")

    result = run_public_tests(task, layout, workspace_root=tmp_path)

    assert result.command[0] == _sys.executable
    assert result.command[1:3] == ["-m", "pytest"]
    # Every declared node id appears in the command tail.
    for node_id in task.public_tests:
        assert node_id in result.command[3:]


# --- error paths ----------------------------------------------------------


def test_invalid_test_kind_raises_harness_error(
    pack: BenchmarkPack, tmp_path: Path
):
    task = _task(pack, "bugfix_005")
    layout = _layout(pack, "bugfix_005")

    with pytest.raises(TestHarnessError) as exc_info:
        run_pytest_nodes(
            task=task,
            layout=layout,
            node_ids=task.public_tests,
            test_kind="surprise",
            workspace_root=tmp_path,
        )
    assert "test_kind" in str(exc_info.value)


def test_empty_node_ids_raises_harness_error(
    pack: BenchmarkPack, tmp_path: Path
):
    task = _task(pack, "bugfix_005")
    layout = _layout(pack, "bugfix_005")

    with pytest.raises(TestHarnessError) as exc_info:
        run_pytest_nodes(
            task=task,
            layout=layout,
            node_ids=[],
            test_kind="public",
            workspace_root=tmp_path,
        )
    assert "bugfix_005" in str(exc_info.value)


# --- run_task_tests -------------------------------------------------------


def test_run_task_tests_returns_public_and_hidden_results(
    pack: BenchmarkPack, tmp_path: Path
):
    task = _task(pack, "bugfix_005")
    layout = _layout(pack, "bugfix_005")

    public_result, hidden_result = run_task_tests(
        task, layout, workspace_root=tmp_path
    )

    assert isinstance(public_result, PytestRunResult)
    assert isinstance(hidden_result, PytestRunResult)
    assert public_result.test_kind == "public"
    assert hidden_result.test_kind == "hidden"
    # Each kind ran in its own copied workspace.
    assert public_result.workspace_path != hidden_result.workspace_path
    # bugfix_005 specifically: public passes, hidden fails.
    assert public_result.passed is True
    assert hidden_result.passed is False


# --- integration with resolve_task_fixture_layout -------------------------


def test_layout_then_run_public_then_run_hidden(
    pack: BenchmarkPack, tmp_path: Path
):
    # End-to-end: resolve the layout from the task spec, then run public
    # and hidden tests in separate workspaces.
    task = _task(pack, "bugfix_005")
    layout = resolve_task_fixture_layout(task, project_root=REPO_ROOT)

    public_result = run_public_tests(
        task, layout, workspace_root=tmp_path / "pub"
    )
    hidden_result = run_hidden_tests(
        task, layout, workspace_root=tmp_path / "hid"
    )

    assert public_result.passed is True
    assert hidden_result.passed is False
    # Workspaces are under the requested roots, not the original fixture.
    assert Path(public_result.workspace_path).is_relative_to(tmp_path / "pub")
    assert Path(hidden_result.workspace_path).is_relative_to(tmp_path / "hid")
