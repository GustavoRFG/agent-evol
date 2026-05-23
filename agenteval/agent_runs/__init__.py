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

__all__ = [
    "AgentRunArtifact",
    "AgentRunArtifactError",
    "agent_run_artifact_from_dict",
    "agent_run_artifact_to_dict",
    "make_agent_run_id",
    "validate_agent_run_artifact",
]
