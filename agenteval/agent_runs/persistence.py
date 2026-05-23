"""JSON file persistence for :class:`AgentRunArtifact`.

External agents run outside AgentEval Forge and produce artifacts. This module
lets the framework save and load those artifacts as JSON files. It performs no
patch application, no test execution, no scoring, and no network calls.
Standard library only.
"""

from __future__ import annotations

import json
from pathlib import Path

from agenteval.agent_runs.artifacts import (
    AgentRunArtifact,
    AgentRunArtifactError,
    agent_run_artifact_from_dict,
    agent_run_artifact_to_dict,
    validate_agent_run_artifact,
)


class AgentRunPersistenceError(ValueError):
    """Raised when saving or loading an :class:`AgentRunArtifact` fails."""


def save_agent_run_artifact(
    artifact: AgentRunArtifact,
    path: str | Path,
) -> None:
    """Validate ``artifact`` and write it as UTF-8 JSON to ``path``.

    Parent directories are created if they do not already exist. The artifact
    is not mutated.

    Raises:
        AgentRunPersistenceError: If validation fails or the file cannot be
            written.
    """
    try:
        data = agent_run_artifact_to_dict(artifact)
    except AgentRunArtifactError as exc:
        raise AgentRunPersistenceError(
            f"cannot save invalid agent run artifact: {exc}"
        ) from exc

    target = Path(path)
    try:
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise AgentRunPersistenceError(
            f"failed to write agent run artifact to {target}: {exc}"
        ) from exc


def load_agent_run_artifact(path: str | Path) -> AgentRunArtifact:
    """Load and validate an :class:`AgentRunArtifact` from a JSON file.

    Raises:
        AgentRunPersistenceError: If the file is missing, contains invalid
            JSON, has the wrong structure, or fails validation.
    """
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AgentRunPersistenceError(
            f"agent run artifact file not found: {source}"
        ) from exc
    except OSError as exc:
        raise AgentRunPersistenceError(
            f"failed to read agent run artifact from {source}: {exc}"
        ) from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentRunPersistenceError(
            f"invalid JSON in agent run artifact {source}: {exc}"
        ) from exc

    try:
        return agent_run_artifact_from_dict(data)
    except AgentRunArtifactError as exc:
        raise AgentRunPersistenceError(
            f"invalid agent run artifact in {source}: {exc}"
        ) from exc


def save_agent_run_artifact_folder(
    artifact: AgentRunArtifact,
    folder: str | Path,
    filename: str = "agent_run.json",
) -> Path:
    """Save ``artifact`` to ``folder / filename`` and return the final path.

    The folder is created if it does not already exist.
    """
    if not isinstance(filename, str) or not filename.strip():
        raise AgentRunPersistenceError("filename must be a non-empty string")

    target = Path(folder) / filename
    save_agent_run_artifact(artifact, target)
    return target


# Re-export validate so callers can import it from this module if they prefer.
__all__ = [
    "AgentRunPersistenceError",
    "load_agent_run_artifact",
    "save_agent_run_artifact",
    "save_agent_run_artifact_folder",
    "validate_agent_run_artifact",
]
