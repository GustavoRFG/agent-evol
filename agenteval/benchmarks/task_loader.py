"""Load benchmark :class:`TaskSpec` definitions from on-disk JSON files.

A benchmark task lives in a single JSON object on disk. This module reads such a
file, checks that the required fields are present, fills optional fields with
their defaults, and returns a validated :class:`~agenteval.core.schemas.TaskSpec`.

All failure cases raise :class:`TaskLoadError` with a clear, actionable message.
Standard library only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from agenteval.core.schemas import TaskSpec

# Fields a task JSON file must contain.
REQUIRED_FIELDS: tuple[str, ...] = ("task_id", "title")

# Optional fields and their defaults. These mirror the TaskSpec dataclass
# defaults so an on-disk task behaves identically to one built in code.
OPTIONAL_FIELD_DEFAULTS: dict[str, Any] = {
    "version": "1.0",
    "description": "",
    "repo_path": "",
    "public_tests": [],
    "hidden_tests": [],
}

# Fields expected to hold a list of strings.
_LIST_FIELDS: tuple[str, ...] = ("public_tests", "hidden_tests")


class TaskLoadError(Exception):
    """Raised when a benchmark task file is missing, unreadable, or invalid."""


def load_task(path: str | Path) -> TaskSpec:
    """Load a single benchmark task from a JSON file.

    Args:
        path: Path to a JSON file describing one task.

    Returns:
        A validated :class:`TaskSpec`.

    Raises:
        TaskLoadError: If the file is missing, unreadable, not valid JSON, not a
            JSON object, or missing a required field.
    """
    task_path = Path(path)

    if not task_path.is_file():
        raise TaskLoadError(f"Task file not found: {task_path}")

    try:
        raw = task_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - rare I/O failure
        raise TaskLoadError(f"Could not read task file {task_path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TaskLoadError(
            f"Invalid JSON in task file {task_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise TaskLoadError(
            f"Task file {task_path} must contain a JSON object, "
            f"got {type(data).__name__}"
        )

    missing = [name for name in REQUIRED_FIELDS if name not in data]
    if missing:
        raise TaskLoadError(
            f"Task file {task_path} is missing required field(s): "
            f"{', '.join(missing)}"
        )

    return _build_task_spec(data, task_path)


def _build_task_spec(data: dict[str, Any], task_path: Path) -> TaskSpec:
    """Construct a :class:`TaskSpec` from validated task data."""
    kwargs: dict[str, Any] = {name: data[name] for name in REQUIRED_FIELDS}

    for name, default in OPTIONAL_FIELD_DEFAULTS.items():
        # deepcopy so list defaults are never shared between loaded tasks.
        kwargs[name] = data[name] if name in data else copy.deepcopy(default)

    for name in _LIST_FIELDS:
        if not isinstance(kwargs[name], list):
            raise TaskLoadError(
                f"Task file {task_path} field '{name}' must be a list, "
                f"got {type(kwargs[name]).__name__}"
            )

    return TaskSpec(**kwargs)
