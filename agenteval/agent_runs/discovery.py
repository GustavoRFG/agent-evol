"""Deterministic directory scanning for agent run artifact files.

External agents drop their artifacts somewhere on disk, typically as folders
containing an ``agent_run.json`` file (and, in the future, sidecar files such
as a patch or transcript). This module walks a root directory, finds those
JSON files in a deterministic order, and optionally loads them.

It performs no patch application, no test execution, no evaluation, and no
network calls. Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.persistence import (
    AgentRunPersistenceError,
    load_agent_run_artifact,
)


class AgentRunDiscoveryError(ValueError):
    """Raised when agent run artifact discovery or batch loading fails."""


def _check_filename(filename: str) -> None:
    if not isinstance(filename, str) or not filename.strip():
        raise AgentRunDiscoveryError("filename must be a non-empty string")


def discover_agent_run_artifact_paths(
    root: str | Path,
    *,
    filename: str = "agent_run.json",
) -> list[Path]:
    """Recursively find files named ``filename`` under ``root``.

    Paths are returned sorted by their POSIX-style string form so that ordering
    is stable across operating systems.

    Raises:
        AgentRunDiscoveryError: If ``root`` does not exist or is not a
            directory, or if ``filename`` is not a non-empty string.
    """
    _check_filename(filename)

    root_path = Path(root)
    if not root_path.exists():
        raise AgentRunDiscoveryError(f"discovery root does not exist: {root_path}")
    if not root_path.is_dir():
        raise AgentRunDiscoveryError(
            f"discovery root is not a directory: {root_path}"
        )

    matches = [p for p in root_path.rglob(filename) if p.is_file()]
    matches.sort(key=lambda p: p.as_posix())
    return matches


def load_agent_run_artifacts_from_dir(
    root: str | Path,
    *,
    filename: str = "agent_run.json",
    skip_invalid: bool = False,
) -> list[AgentRunArtifact]:
    """Discover and load every agent run artifact under ``root``.

    The returned artifacts preserve the deterministic path order produced by
    :func:`discover_agent_run_artifact_paths`.

    Args:
        root: Directory to search.
        filename: Artifact filename to look for.
        skip_invalid: If ``True``, files that fail to load are silently
            skipped. If ``False`` (the default), the first failure is
            re-raised as :class:`AgentRunDiscoveryError` with path context.

    Raises:
        AgentRunDiscoveryError: For invalid roots, or for invalid artifacts
            when ``skip_invalid`` is ``False``.
    """
    return [
        artifact
        for _, artifact in load_agent_run_artifacts_with_paths(
            root, filename=filename, skip_invalid=skip_invalid
        )
    ]


def load_agent_run_artifacts_with_paths(
    root: str | Path,
    *,
    filename: str = "agent_run.json",
    skip_invalid: bool = False,
) -> list[tuple[Path, AgentRunArtifact]]:
    """Like :func:`load_agent_run_artifacts_from_dir`, but keep source paths.

    The returned list preserves the deterministic path order. Each entry is a
    ``(path, artifact)`` tuple, useful for diagnostics and future reporting.
    """
    paths = discover_agent_run_artifact_paths(root, filename=filename)

    loaded: list[tuple[Path, AgentRunArtifact]] = []
    for path in paths:
        try:
            artifact = load_agent_run_artifact(path)
        except AgentRunPersistenceError as exc:
            if skip_invalid:
                continue
            raise AgentRunDiscoveryError(
                f"failed to load agent run artifact at {path}: {exc}"
            ) from exc
        loaded.append((path, artifact))
    return loaded


__all__ = [
    "AgentRunDiscoveryError",
    "discover_agent_run_artifact_paths",
    "load_agent_run_artifacts_from_dir",
    "load_agent_run_artifacts_with_paths",
]
