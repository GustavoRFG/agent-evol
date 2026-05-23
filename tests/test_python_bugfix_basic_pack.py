"""Tests for the shipped ``python_bugfix_basic`` benchmark pack.

These tests validate the on-disk structure and content of the pack itself —
that every shipped task spec has the fields a coding agent needs to attempt
it. They do not run any agent, apply any patch, or execute any target tests.
"""

from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import BenchmarkPack, TaskSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

EXPECTED_TASK_IDS = {
    "bugfix_001",
    "bugfix_002",
    "bugfix_003",
    "bugfix_004",
    "bugfix_005",
}


@pytest.fixture(scope="module")
def pack() -> BenchmarkPack:
    return load_benchmark_pack(PACK_DIR)


def test_pack_loads_successfully(pack: BenchmarkPack):
    assert isinstance(pack, BenchmarkPack)
    assert pack.name == "python_bugfix_basic"
    assert pack.version == "1.0"


def test_pack_has_at_least_five_tasks(pack: BenchmarkPack):
    assert len(pack.tasks) >= 5
    assert all(isinstance(task, TaskSpec) for task in pack.tasks)


def test_pack_contains_bugfix_001_through_bugfix_005(pack: BenchmarkPack):
    task_ids = {task.task_id for task in pack.tasks}
    missing = EXPECTED_TASK_IDS - task_ids
    assert not missing, f"Pack is missing expected task IDs: {sorted(missing)}"


def test_pack_task_ids_are_unique(pack: BenchmarkPack):
    task_ids = [task.task_id for task in pack.tasks]
    assert len(set(task_ids)) == len(task_ids)


def test_every_task_has_non_empty_title(pack: BenchmarkPack):
    for task in pack.tasks:
        assert task.title.strip(), (
            f"Task '{task.task_id}' has an empty title"
        )


def test_every_task_has_non_empty_description(pack: BenchmarkPack):
    for task in pack.tasks:
        assert task.description.strip(), (
            f"Task '{task.task_id}' has an empty description"
        )


def test_every_task_has_non_empty_repo_path(pack: BenchmarkPack):
    for task in pack.tasks:
        assert task.repo_path.strip(), (
            f"Task '{task.task_id}' has an empty repo_path"
        )


def test_every_task_has_at_least_one_public_test(pack: BenchmarkPack):
    for task in pack.tasks:
        assert len(task.public_tests) >= 1, (
            f"Task '{task.task_id}' has no public tests"
        )
        for node_id in task.public_tests:
            assert isinstance(node_id, str) and node_id.strip()


def test_every_task_has_at_least_one_hidden_test(pack: BenchmarkPack):
    for task in pack.tasks:
        assert len(task.hidden_tests) >= 1, (
            f"Task '{task.task_id}' has no hidden tests"
        )
        for node_id in task.hidden_tests:
            assert isinstance(node_id, str) and node_id.strip()


def test_repo_path_values_are_deterministic_strings(pack: BenchmarkPack):
    # Loading the pack twice must yield the exact same repo_path strings, in
    # the same order — so downstream tooling can rely on them as stable keys.
    first = [task.repo_path for task in pack.tasks]
    second = [task.repo_path for task in load_benchmark_pack(PACK_DIR).tasks]
    assert first == second
    # Plain non-empty strings, no None / bytes / Path objects slipped in.
    for repo_path in first:
        assert isinstance(repo_path, str)
        assert repo_path.strip() == repo_path
        assert repo_path  # non-empty


def test_new_tasks_use_distinct_repo_paths(pack: BenchmarkPack):
    repo_paths = [task.repo_path for task in pack.tasks]
    assert len(set(repo_paths)) == len(repo_paths)


def test_task_ids_match_their_filenames():
    # Filename without ``.json`` must equal the ``task_id`` field inside.
    tasks_dir = PACK_DIR / "tasks"
    for task_file in sorted(tasks_dir.glob("*.json")):
        expected_id = task_file.stem
        # load via the public loader so the assertion is end-to-end.
        pack = load_benchmark_pack(PACK_DIR)
        task = next(t for t in pack.tasks if t.task_id == expected_id)
        assert task.task_id == expected_id, (
            f"File {task_file.name} declares task_id '{task.task_id}'"
        )
