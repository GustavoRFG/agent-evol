"""Discover and validate the on-disk layout of a benchmark task's repo fixture.

A benchmark task ships as a directory tree on disk (see ``benchmarks/`` in the
repository). A *fixture layout* is a structured, validated snapshot of where
that directory lives and which files inside it serve which role — the README,
the source files an agent is expected to edit, and the public and hidden test
files declared by the task's :class:`TaskSpec`.

This module discovers and validates fixture layouts. It performs **no**
execution: nothing is imported, no pytest is invoked, no patches are applied.
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agenteval.core.schemas import BenchmarkPack, TaskSpec


class FixtureLayoutError(ValueError):
    """Raised when a task's repo fixture cannot be located or is malformed.

    Subclasses :class:`ValueError` so callers may catch either type.
    """


@dataclass
class TaskFixtureLayout:
    """The validated on-disk layout of one benchmark task's repo fixture.

    Every path is resolved relative to the caller's ``project_root`` and is
    guaranteed to exist when this layout is returned by
    :func:`resolve_task_fixture_layout`. ``source_files``,
    ``public_test_files``, and ``hidden_test_files`` are deterministically
    ordered (sorted by string path) and contain no duplicates.
    """

    task_id: str
    repo_path: Path
    readme_path: Path
    source_files: list[Path] = field(default_factory=list)
    public_test_files: list[Path] = field(default_factory=list)
    hidden_test_files: list[Path] = field(default_factory=list)


def resolve_task_fixture_layout(
    task: TaskSpec,
    *,
    project_root: str | Path = ".",
) -> TaskFixtureLayout:
    """Resolve and validate the on-disk fixture layout for one task.

    The task's ``repo_path`` is interpreted relative to ``project_root``. The
    function checks that the repo directory and its ``README.md`` exist,
    discovers top-level Python source files (excluding the ``tests``
    directory and dunder files), and maps every node ID in
    ``task.public_tests`` / ``task.hidden_tests`` to a real test file inside
    the fixture.

    Args:
        task: The :class:`TaskSpec` whose fixture should be resolved.
        project_root: Root directory used to resolve ``task.repo_path``.
            Defaults to the current directory.

    Returns:
        A fully populated :class:`TaskFixtureLayout`.

    Raises:
        FixtureLayoutError: If ``task.repo_path`` is empty, the repo
            directory does not exist, the README is missing, a declared
            test node ID is malformed, or a declared public/hidden test
            file does not exist.
    """
    if not task.repo_path:
        raise FixtureLayoutError(
            f"Task '{task.task_id}' has no repo_path; cannot resolve fixture."
        )

    root = Path(project_root)
    repo_path = (root / task.repo_path).resolve()

    if not repo_path.is_dir():
        raise FixtureLayoutError(
            f"Repo fixture for task '{task.task_id}' is missing: {repo_path}"
        )

    readme_path = repo_path / "README.md"
    if not readme_path.is_file():
        raise FixtureLayoutError(
            f"Fixture for task '{task.task_id}' is missing README.md: "
            f"{readme_path}"
        )

    source_files = _discover_source_files(repo_path)
    public_test_files = _resolve_test_files(
        task.public_tests, repo_path, task.task_id, kind="public"
    )
    hidden_test_files = _resolve_test_files(
        task.hidden_tests, repo_path, task.task_id, kind="hidden"
    )

    return TaskFixtureLayout(
        task_id=task.task_id,
        repo_path=repo_path,
        readme_path=readme_path,
        source_files=source_files,
        public_test_files=public_test_files,
        hidden_test_files=hidden_test_files,
    )


def resolve_pack_fixture_layouts(
    pack: BenchmarkPack,
    *,
    project_root: str | Path = ".",
    include_missing: bool = False,
) -> list[TaskFixtureLayout]:
    """Resolve every task fixture in a benchmark pack.

    Iterates ``pack.tasks`` in order, resolving each fixture via
    :func:`resolve_task_fixture_layout`. The pack is never mutated.

    Args:
        pack: The benchmark pack whose tasks should be resolved.
        project_root: Root directory used to resolve every task's
            ``repo_path``. Defaults to the current directory.
        include_missing: When ``False`` (the default), any
            :class:`FixtureLayoutError` from a task propagates. When
            ``True``, tasks whose fixtures are missing or malformed are
            skipped silently and the remaining layouts are returned in
            task order.

    Returns:
        A list of :class:`TaskFixtureLayout` in ``pack.tasks`` order; tasks
        that could not be resolved are omitted when ``include_missing`` is
        ``True``.

    Raises:
        FixtureLayoutError: Propagated from any individual task when
            ``include_missing`` is ``False``.
    """
    layouts: list[TaskFixtureLayout] = []
    for task in pack.tasks:
        try:
            layouts.append(
                resolve_task_fixture_layout(task, project_root=project_root)
            )
        except FixtureLayoutError:
            if not include_missing:
                raise
            # Otherwise, silently skip the missing fixture.
    return layouts


# --- internals -------------------------------------------------------------


def _discover_source_files(repo_path: Path) -> list[Path]:
    """Return top-level ``.py`` source files in a fixture, deterministically.

    Top-level only — the ``tests`` directory is excluded so test files are
    never mistaken for source files. Dunder files like ``__init__.py`` are
    also excluded. The list is sorted by string path so the order does not
    depend on filesystem iteration order.
    """
    sources = [
        candidate
        for candidate in repo_path.iterdir()
        if candidate.is_file()
        and candidate.suffix == ".py"
        and not (
            candidate.name.startswith("__") and candidate.name.endswith("__.py")
        )
    ]
    return sorted(sources, key=lambda path: path.as_posix())


def _resolve_test_files(
    node_ids: list[str],
    repo_path: Path,
    task_id: str,
    *,
    kind: str,
) -> list[Path]:
    """Map a list of pytest node IDs to deterministic, unique, real files.

    Each node ID is split on ``::`` into ``(file_path, test_name)``; only the
    file part is used here. Files are checked for existence inside
    ``repo_path`` and de-duplicated while preserving deterministic ordering
    (sorted by string path).

    Args:
        node_ids: Pytest-style node IDs from ``task.public_tests`` or
            ``task.hidden_tests``.
        repo_path: The resolved fixture root the files must live inside.
        task_id: The task's ID, used only for error messages.
        kind: ``"public"`` or ``"hidden"``, used only for error messages.

    Raises:
        FixtureLayoutError: If a node ID is malformed (no ``::`` separator)
            or its declared file does not exist inside ``repo_path``.
    """
    seen: set[Path] = set()
    ordered: list[Path] = []
    for node_id in node_ids:
        if "::" not in node_id:
            raise FixtureLayoutError(
                f"Task '{task_id}' has a malformed {kind} test node id "
                f"'{node_id}'; expected the form 'file.py::test_name'."
            )
        file_part = node_id.split("::", 1)[0]
        candidate = (repo_path / file_part).resolve()
        if not candidate.is_file():
            raise FixtureLayoutError(
                f"{kind.capitalize()} test file declared by task "
                f"'{task_id}' is missing: {candidate}"
            )
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return sorted(ordered, key=lambda path: path.as_posix())
