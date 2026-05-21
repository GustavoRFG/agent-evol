"""Tests for the benchmark task loader."""

import json
from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import TaskLoadError, load_task
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
