"""Tests for the benchmark task loader."""

import json
from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import TaskLoadError, load_pack, load_task
from agenteval.core.schemas import TaskSpec

# Path to the first shipped example task, relative to the repository root.
REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_TASK = (
    REPO_ROOT / "benchmarks" / "python_bugfix_basic" / "tasks" / "bugfix_001.json"
)


def _write_task(tmp_path: Path, data: dict, name: str = "task.json") -> Path:
    """Write ``data`` as a JSON task file and return its path."""
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_example_task_loads_into_task_spec():
    task = load_task(EXAMPLE_TASK)
    assert isinstance(task, TaskSpec)
    assert task.task_id == "bugfix_001"
    assert task.version == "1.0"
    assert len(task.public_tests) == 2
    assert len(task.hidden_tests) == 2


def test_valid_task_loads_all_fields(tmp_path):
    data = {
        "version": "1.2",
        "task_id": "t-valid",
        "title": "A valid task",
        "description": "Some description.",
        "repo_path": "repos/t-valid",
        "public_tests": ["tests/test_a.py::test_one"],
        "hidden_tests": ["tests/hidden.py::test_two"],
    }
    task = load_task(_write_task(tmp_path, data))
    assert isinstance(task, TaskSpec)
    assert task.task_id == "t-valid"
    assert task.title == "A valid task"
    assert task.description == "Some description."
    assert task.repo_path == "repos/t-valid"
    assert task.public_tests == ["tests/test_a.py::test_one"]
    assert task.hidden_tests == ["tests/hidden.py::test_two"]


def test_optional_fields_default_when_omitted(tmp_path):
    data = {"task_id": "t-minimal", "title": "Only required fields"}
    task = load_task(_write_task(tmp_path, data))
    assert task.version == "1.0"
    assert task.description == ""
    assert task.repo_path == ""
    assert task.public_tests == []
    assert task.hidden_tests == []


def test_list_defaults_are_independent_between_loads(tmp_path):
    data = {"task_id": "t1", "title": "First"}
    first = load_task(_write_task(tmp_path, data, "a.json"))
    second = load_task(_write_task(tmp_path, data, "b.json"))
    first.public_tests.append("tests/test_x.py::test_x")
    assert first.public_tests == ["tests/test_x.py::test_x"]
    assert second.public_tests == []


def test_version_field_is_read_from_file(tmp_path):
    data = {"task_id": "t-ver", "title": "Versioned", "version": "2.5"}
    task = load_task(_write_task(tmp_path, data))
    assert task.version == "2.5"


def test_missing_required_field_raises_clear_error(tmp_path):
    data = {"task_id": "t-no-title"}  # missing "title"
    with pytest.raises(TaskLoadError) as exc_info:
        load_task(_write_task(tmp_path, data))
    assert "title" in str(exc_info.value)


def test_missing_file_raises_clear_error(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(TaskLoadError) as exc_info:
        load_task(missing)
    assert "not found" in str(exc_info.value)


def test_invalid_json_raises_clear_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(TaskLoadError) as exc_info:
        load_task(path)
    assert "Invalid JSON" in str(exc_info.value)


def test_non_object_json_raises_clear_error(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(TaskLoadError) as exc_info:
        load_task(path)
    assert "JSON object" in str(exc_info.value)


def test_non_list_test_field_raises_clear_error(tmp_path):
    data = {
        "task_id": "t-badlist",
        "title": "Bad public_tests",
        "public_tests": "not-a-list",
    }
    with pytest.raises(TaskLoadError) as exc_info:
        load_task(_write_task(tmp_path, data))
    assert "public_tests" in str(exc_info.value)


# --- load_pack -------------------------------------------------------------


def _make_pack(tmp_path: Path, tasks: dict[str, dict]) -> Path:
    """Create a benchmark pack directory with the given ``{filename: data}``.

    Always creates the ``tasks/`` subdirectory, even when ``tasks`` is empty.
    Returns the pack directory path.
    """
    pack_dir = tmp_path / "pack"
    tasks_dir = pack_dir / "tasks"
    tasks_dir.mkdir(parents=True)
    for filename, data in tasks.items():
        (tasks_dir / filename).write_text(json.dumps(data), encoding="utf-8")
    return pack_dir


def test_load_pack_loads_multiple_tasks(tmp_path):
    pack_dir = _make_pack(
        tmp_path,
        {
            "bugfix_001.json": {"task_id": "bugfix_001", "title": "First"},
            "bugfix_002.json": {"task_id": "bugfix_002", "title": "Second"},
        },
    )
    tasks = load_pack(pack_dir)
    assert len(tasks) == 2
    assert all(isinstance(task, TaskSpec) for task in tasks)
    assert {task.task_id for task in tasks} == {"bugfix_001", "bugfix_002"}


def test_load_pack_orders_tasks_by_filename(tmp_path):
    pack_dir = _make_pack(
        tmp_path,
        {
            "bugfix_003.json": {"task_id": "bugfix_003", "title": "Third"},
            "bugfix_001.json": {"task_id": "bugfix_001", "title": "First"},
            "bugfix_002.json": {"task_id": "bugfix_002", "title": "Second"},
        },
    )
    tasks = load_pack(pack_dir)
    assert [task.task_id for task in tasks] == [
        "bugfix_001",
        "bugfix_002",
        "bugfix_003",
    ]


def test_load_pack_empty_tasks_dir_returns_empty_list(tmp_path):
    pack_dir = _make_pack(tmp_path, {})
    assert load_pack(pack_dir) == []


def test_load_pack_missing_pack_dir_raises_clear_error(tmp_path):
    missing = tmp_path / "no_such_pack"
    with pytest.raises(TaskLoadError) as exc_info:
        load_pack(missing)
    assert "pack directory not found" in str(exc_info.value)


def test_load_pack_missing_tasks_dir_raises_clear_error(tmp_path):
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()  # pack exists, but has no tasks/ subdirectory
    with pytest.raises(TaskLoadError) as exc_info:
        load_pack(pack_dir)
    assert "tasks" in str(exc_info.value)


def test_load_pack_invalid_task_raises_clear_error(tmp_path):
    pack_dir = _make_pack(
        tmp_path,
        {
            "good.json": {"task_id": "good", "title": "Valid task"},
            "bad.json": {"task_id": "bad-no-title"},  # missing "title"
        },
    )
    with pytest.raises(TaskLoadError) as exc_info:
        load_pack(pack_dir)
    assert "title" in str(exc_info.value)


def test_load_pack_loads_shipped_example_pack():
    pack_dir = REPO_ROOT / "benchmarks" / "python_bugfix_basic"
    tasks = load_pack(pack_dir)
    assert len(tasks) >= 1
    assert any(task.task_id == "bugfix_001" for task in tasks)
