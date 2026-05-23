"""External agent run artifact ingestion for AgentEval Forge.

This package defines the standard in-memory format for artifacts produced by
external agent runs (Claude Code, Codex, ForgeAgent, DGM, etc.). AgentEval
Forge does not execute agents — it only ingests their artifacts.
"""

from agenteval.agent_runs.artifacts import (
    AgentRunArtifact,
    AgentRunArtifactError,
    agent_run_artifact_from_dict,
    agent_run_artifact_to_dict,
    make_agent_run_id,
    validate_agent_run_artifact,
)
from agenteval.agent_runs.discovery import (
    AgentRunDiscoveryError,
    discover_agent_run_artifact_paths,
    load_agent_run_artifacts_from_dir,
    load_agent_run_artifacts_with_paths,
)
from agenteval.agent_runs.persistence import (
    AgentRunPersistenceError,
    load_agent_run_artifact,
    save_agent_run_artifact,
    save_agent_run_artifact_folder,
)

__all__ = [
    "AgentRunArtifact",
    "AgentRunArtifactError",
    "AgentRunDiscoveryError",
    "AgentRunPersistenceError",
    "agent_run_artifact_from_dict",
    "agent_run_artifact_to_dict",
    "discover_agent_run_artifact_paths",
    "load_agent_run_artifact",
    "load_agent_run_artifacts_from_dir",
    "load_agent_run_artifacts_with_paths",
    "make_agent_run_id",
    "save_agent_run_artifact",
    "save_agent_run_artifact_folder",
    "validate_agent_run_artifact",
]
