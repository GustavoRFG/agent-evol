"""Tests for the fixture-layout discovery layer.

These tests exercise :func:`resolve_task_fixture_layout` and
:func:`resolve_pack_fixture_layouts` against the shipped
``python_bugfix_basic`` pack and against synthetic fixtures built under
``tmp_path``. They never import or execute any fixture source file.
"""

import json
from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import BenchmarkPack, TaskSpec
from agenteval.fixtures import (
    FixtureLayoutError,
    TaskFixtureLayout,
    resolve_pack_fixture_layouts,
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


# --- happy path against the shipped fixtures -------------------------------


def test_resolve_layout_for_bugfix_002(pack: BenchmarkPack):
    layout = resolve_task_fixture_layout(
        _task(pack, "bugfix_002"), project_root=REPO_ROOT
    )
    assert isinstance(layout, TaskFixtureLayout)
    assert layout.task_id == "bugfix_002"


def test_bugfix_002_repo_path_exists(pack: BenchmarkPack):
    layout = resolve_task_fixture_layout(
        _task(pack, "bugfix_002"), project_root=REPO_ROOT
    )
    assert layout.repo_path.is_dir()
    expected = PACK_DIR / "repos" / "bugfix_002"
    assert layout.repo_path.resolve() == expected.resolve()


def test_bugfix_002_readme_path_exists(pack: BenchmarkPack):
    layout = resolve_task_fixture_layout(
        _task(pack, "bugfix_002"), project_root=REPO_ROOT
    )
    assert layout.readme_path.is_file()
    assert layout.readme_path.name == "README.md"


def test_bugfix_002_source_files_include_safe_average(pack: BenchmarkPack):
    layout = resolve_task_fixture_layout(
        _task(pack, "bugfix_002"), project_root=REPO_ROOT
    )
    names = [path.name for path in layout.source_files]
    assert "safe_average.py" in names
    # Top-level discovery only — no test files should appear here.
    assert all(not name.startswith("test_") for name in names)


def test_bugfix_002_public_test_files_include_test_safe_average(
    pack: BenchmarkPack,
):
    layout = resolve_task_fixture_layout(
        _task(pack, "bugfix_002"), project_root=REPO_ROOT
    )
    names = [path.name for path in layout.public_test_files]
    assert "test_safe_average.py" in names


def test_bugfix_002_hidden_test_files_include_hidden_module(
    pack: BenchmarkPack,
):
    layout = resolve_task_fixture_layout(
        _task(pack, "bugfix_002"), project_root=REPO_ROOT
    )
    names = [path.name for path in layout.hidden_test_files]
    assert "test_safe_average_hidden.py" in names


def test_test_files_are_deterministic_and_unique(pack: BenchmarkPack):
    layout_a = resolve_task_fixture_layout(
        _task(pack, "bugfix_003"), project_root=REPO_ROOT
    )
    layout_b = resolve_task_fixture_layout(
        _task(pack, "bugfix_003"), project_root=REPO_ROOT
    )
    # Two consecutive resolves return the same ordering.
    assert layout_a.public_test_files == layout_b.public_test_files
    assert layout_a.hidden_test_files == layout_b.hidden_test_files
    # Strings are sorted.
    public_strs = [p.as_posix() for p in layout_a.public_test_files]
    hidden_strs = [p.as_posix() for p in layout_a.hidden_test_files]
    assert public_strs == sorted(public_strs)
    assert hidden_strs == sorted(hidden_strs)
    # No duplicate entries.
    assert len(set(layout_a.public_test_files)) == len(layout_a.public_test_files)
    assert len(set(layout_a.hidden_test_files)) == len(layout_a.hidden_test_files)


# --- error paths via synthetic fixtures -----------------------------------


def _write_min_repo(repo_dir: Path, *, with_readme: bool = True) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "tests").mkdir(exist_ok=True)
    if with_readme:
        (repo_dir / "README.md").write_text("# Fake fixture\n", encoding="utf-8")


def test_missing_repo_raises_fixture_layout_error(tmp_path: Path):
    task = TaskSpec(
        task_id="ghost",
        title="Ghost task",
        repo_path="repos/ghost",  # Never created on disk.
    )
    with pytest.raises(FixtureLayoutError) as exc_info:
        resolve_task_fixture_layout(task, project_root=tmp_path)
    message = str(exc_info.value)
    assert "ghost" in message
    assert "missing" in message.lower()


def test_missing_readme_raises_fixture_layout_error(tmp_path: Path):
    repo_dir = tmp_path / "repos" / "noreadme"
    _write_min_repo(repo_dir, with_readme=False)
    task = TaskSpec(
        task_id="noreadme",
        title="Missing README task",
        repo_path="repos/noreadme",
    )
    with pytest.raises(FixtureLayoutError) as exc_info:
        resolve_task_fixture_layout(task, project_root=tmp_path)
    message = str(exc_info.value)
    assert "noreadme" in message
    assert "README" in message


def test_missing_declared_test_file_raises_fixture_layout_error(
    tmp_path: Path,
):
    repo_dir = tmp_path / "repos" / "lostpub"
    _write_min_repo(repo_dir)
    # Source file is present, but the declared public test file is not.
    (repo_dir / "thing.py").write_text("def thing():\n    return 1\n", encoding="utf-8")
    task = TaskSpec(
        task_id="lostpub",
        title="Lost public test task",
        repo_path="repos/lostpub",
        public_tests=["tests/test_thing.py::test_thing"],
    )
    with pytest.raises(FixtureLayoutError) as exc_info:
        resolve_task_fixture_layout(task, project_root=tmp_path)
    message = str(exc_info.value)
    assert "lostpub" in message
    assert "test_thing.py" in message


def test_missing_declared_hidden_file_raises_fixture_layout_error(
    tmp_path: Path,
):
    repo_dir = tmp_path / "repos" / "losthidden"
    _write_min_repo(repo_dir)
    (repo_dir / "thing.py").write_text("def thing():\n    return 1\n", encoding="utf-8")
    # A real public test file exists, but the hidden one is missing.
    (repo_dir / "tests" / "test_thing.py").write_text(
        "def test_thing():\n    assert True\n", encoding="utf-8"
    )
    task = TaskSpec(
        task_id="losthidden",
        title="Lost hidden test task",
        repo_path="repos/losthidden",
        public_tests=["tests/test_thing.py::test_thing"],
        hidden_tests=["tests/test_thing_hidden.py::test_hidden"],
    )
    with pytest.raises(FixtureLayoutError) as exc_info:
        resolve_task_fixture_layout(task, project_root=tmp_path)
    message = str(exc_info.value)
    assert "losthidden" in message
    assert "test_thing_hidden.py" in message


def test_malformed_node_id_raises_fixture_layout_error(tmp_path: Path):
    repo_dir = tmp_path / "repos" / "badnode"
    _write_min_repo(repo_dir)
    task = TaskSpec(
        task_id="badnode",
        title="Malformed node id task",
        repo_path="repos/badnode",
        public_tests=["tests/test_thing.py"],  # missing ::test_name
    )
    with pytest.raises(FixtureLayoutError) as exc_info:
        resolve_task_fixture_layout(task, project_root=tmp_path)
    assert "badnode" in str(exc_info.value)


# --- pack-level resolution -------------------------------------------------


def test_resolve_pack_layouts_include_missing_returns_existing_fixtures(
    pack: BenchmarkPack,
):
    layouts = resolve_pack_fixture_layouts(
        pack, project_root=REPO_ROOT, include_missing=True
    )
    resolved_ids = [layout.task_id for layout in layouts]
    for task_id in ("bugfix_002", "bugfix_003", "bugfix_004", "bugfix_005"):
        assert task_id in resolved_ids


def test_resolve_pack_layouts_preserves_task_order(pack: BenchmarkPack):
    layouts = resolve_pack_fixture_layouts(
        pack, project_root=REPO_ROOT, include_missing=True
    )
    resolved_ids = [layout.task_id for layout in layouts]
    task_id_order = [task.task_id for task in pack.tasks]
    # Resolved IDs must appear in the same relative order as in the pack.
    indices = [task_id_order.index(tid) for tid in resolved_ids]
    assert indices == sorted(indices)


def test_resolve_pack_layouts_default_raises_when_bugfix_001_is_missing(
    pack: BenchmarkPack,
):
    # bugfix_001 ships without a repo fixture yet; the default (include
    # missing fixtures disabled) must surface that as a FixtureLayoutError.
    assert any(
        task.task_id == "bugfix_001"
        and not (REPO_ROOT / task.repo_path).is_dir()
        for task in pack.tasks
    ), "Precondition: bugfix_001 fixture is expected to be absent."
    with pytest.raises(FixtureLayoutError):
        resolve_pack_fixture_layouts(pack, project_root=REPO_ROOT)


def test_resolve_pack_layouts_does_not_mutate_pack(pack: BenchmarkPack):
    snapshot = json.dumps(
        {
            "name": pack.name,
            "version": pack.version,
            "task_ids": [task.task_id for task in pack.tasks],
        }
    )
    resolve_pack_fixture_layouts(
        pack, project_root=REPO_ROOT, include_missing=True
    )
    after = json.dumps(
        {
            "name": pack.name,
            "version": pack.version,
            "task_ids": [task.task_id for task in pack.tasks],
        }
    )
    assert snapshot == after


# --- regression ------------------------------------------------------------


def test_load_benchmark_pack_still_loads_python_bugfix_basic():
    pack = load_benchmark_pack(PACK_DIR)
    assert pack.name == "python_bugfix_basic"
    assert len(pack.tasks) >= 5
