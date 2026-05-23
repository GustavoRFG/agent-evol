"""Tests for the on-disk repo fixtures of ``python_bugfix_basic``.

These tests check that every bugfix task spec is backed by a real repo
fixture on disk — README, a source file containing the expected function,
a ``tests/`` directory, and the public and hidden test files declared by
the task JSON.

They never execute the fixture tests themselves; the fixtures are
benchmark inputs for coding agents, not part of the AgentEval Forge suite.
"""

from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import BenchmarkPack, TaskSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

# Tasks that ship with a fixture as of Week 4 Day 2.
FIXTURE_TASK_IDS = ("bugfix_002", "bugfix_003", "bugfix_004", "bugfix_005")

# Per-task source-file and function-name expectations. The mapping mirrors
# the layout suggested in the task spec — one source file per fixture,
# named after the function it exposes.
TASK_SOURCE_FILES: dict[str, tuple[str, str]] = {
    "bugfix_002": ("safe_average.py", "safe_average"),
    "bugfix_003": ("normalize_name.py", "normalize_name"),
    "bugfix_004": ("count_words.py", "count_words"),
    "bugfix_005": ("is_within_range.py", "is_within_range"),
}


@pytest.fixture(scope="module")
def pack() -> BenchmarkPack:
    return load_benchmark_pack(PACK_DIR)


def _task_by_id(pack: BenchmarkPack, task_id: str) -> TaskSpec:
    for task in pack.tasks:
        if task.task_id == task_id:
            return task
    raise AssertionError(
        f"Task '{task_id}' is missing from pack '{pack.name}'."
    )


def _fixture_dir(task_id: str) -> Path:
    return PACK_DIR / "repos" / task_id


def _split_node_id(node_id: str) -> tuple[str, str]:
    """Split a pytest node ID into ``(file_path, test_name)``."""
    assert "::" in node_id, f"Node id '{node_id}' is missing the '::' separator."
    file_path, test_name = node_id.split("::", 1)
    return file_path, test_name


# --- structural fixture layout --------------------------------------------


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_fixture_directory_exists(task_id: str):
    fixture = _fixture_dir(task_id)
    assert fixture.is_dir(), f"Missing fixture directory: {fixture}"


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_fixture_has_readme(task_id: str):
    readme = _fixture_dir(task_id) / "README.md"
    assert readme.is_file(), f"Missing README: {readme}"
    assert readme.read_text(encoding="utf-8").strip(), (
        f"README is empty: {readme}"
    )


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_fixture_has_source_file(task_id: str):
    source_name, _ = TASK_SOURCE_FILES[task_id]
    source = _fixture_dir(task_id) / source_name
    assert source.is_file(), f"Missing source file: {source}"


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_fixture_has_tests_directory(task_id: str):
    tests_dir = _fixture_dir(task_id) / "tests"
    assert tests_dir.is_dir(), f"Missing tests directory: {tests_dir}"


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_fixture_source_defines_expected_function(task_id: str):
    source_name, function_name = TASK_SOURCE_FILES[task_id]
    source = _fixture_dir(task_id) / source_name
    text = source.read_text(encoding="utf-8")
    assert f"def {function_name}(" in text, (
        f"Source '{source}' does not define expected function "
        f"'{function_name}'."
    )


# --- task JSON node IDs match fixture files -------------------------------


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_task_public_test_node_ids_map_to_real_files(
    pack: BenchmarkPack, task_id: str
):
    task = _task_by_id(pack, task_id)
    fixture = _fixture_dir(task_id)
    assert task.public_tests, f"Task '{task_id}' has no public tests."
    for node_id in task.public_tests:
        file_path, test_name = _split_node_id(node_id)
        full_path = fixture / file_path
        assert full_path.is_file(), (
            f"Public test file declared by task '{task_id}' is missing: "
            f"{full_path}"
        )
        contents = full_path.read_text(encoding="utf-8")
        assert f"def {test_name}(" in contents, (
            f"Public test '{node_id}' is not defined inside {full_path}."
        )


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_task_hidden_test_node_ids_map_to_real_files(
    pack: BenchmarkPack, task_id: str
):
    task = _task_by_id(pack, task_id)
    fixture = _fixture_dir(task_id)
    assert task.hidden_tests, f"Task '{task_id}' has no hidden tests."
    for node_id in task.hidden_tests:
        file_path, test_name = _split_node_id(node_id)
        full_path = fixture / file_path
        assert full_path.is_file(), (
            f"Hidden test file declared by task '{task_id}' is missing: "
            f"{full_path}"
        )
        contents = full_path.read_text(encoding="utf-8")
        assert f"def {test_name}(" in contents, (
            f"Hidden test '{node_id}' is not defined inside {full_path}."
        )


@pytest.mark.parametrize("task_id", FIXTURE_TASK_IDS)
def test_task_repo_path_points_at_fixture_directory(
    pack: BenchmarkPack, task_id: str
):
    task = _task_by_id(pack, task_id)
    # Task ``repo_path`` is relative to the AgentEval Forge repository root.
    assert (REPO_ROOT / task.repo_path).resolve() == _fixture_dir(
        task_id
    ).resolve()


# --- pack-level regression -------------------------------------------------


def test_load_benchmark_pack_still_loads_at_least_five_tasks(
    pack: BenchmarkPack,
):
    assert pack.name == "python_bugfix_basic"
    assert len(pack.tasks) >= 5
    task_ids = {task.task_id for task in pack.tasks}
    for task_id in FIXTURE_TASK_IDS:
        assert task_id in task_ids, (
            f"Pack lost expected task id '{task_id}' after fixture work."
        )
