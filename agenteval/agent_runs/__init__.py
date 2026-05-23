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
from agenteval.agent_runs.evaluation import (
    AgentRunEvaluationError,
    build_evaluation_result_from_ingested_run,
    build_evaluation_results_from_agent_artifacts,
    build_evaluation_results_from_ingested_runs,
)
from agenteval.agent_runs.ingestion import (
    AgentRunIngestionError,
    IngestedAgentRun,
    build_preliminary_task_evidence_from_artifact,
    ingest_agent_run_artifact,
    ingest_agent_run_artifacts,
    parse_patch_summary_from_artifact,
)
from agenteval.agent_runs.persistence import (
    AgentRunPersistenceError,
    load_agent_run_artifact,
    save_agent_run_artifact,
    save_agent_run_artifact_folder,
)
from agenteval.agent_runs.reporting import (
    AgentRunReportingError,
    build_run_report_from_agent_artifacts,
    build_run_reports_from_agent_artifact_dir,
    build_run_reports_from_agent_artifacts,
)
from agenteval.agent_runs.verification import (
    AgentRunVerificationError,
    verify_agent_run_artifact,
    verify_agent_run_artifacts,
    verify_ingested_agent_run,
    verify_ingested_agent_runs,
)

__all__ = [
    "AgentRunArtifact",
    "AgentRunArtifactError",
    "AgentRunDiscoveryError",
    "AgentRunEvaluationError",
    "AgentRunIngestionError",
    "AgentRunPersistenceError",
    "AgentRunReportingError",
    "AgentRunVerificationError",
    "IngestedAgentRun",
    "agent_run_artifact_from_dict",
    "agent_run_artifact_to_dict",
    "build_evaluation_result_from_ingested_run",
    "build_evaluation_results_from_agent_artifacts",
    "build_evaluation_results_from_ingested_runs",
    "build_preliminary_task_evidence_from_artifact",
    "build_run_report_from_agent_artifacts",
    "build_run_reports_from_agent_artifact_dir",
    "build_run_reports_from_agent_artifacts",
    "discover_agent_run_artifact_paths",
    "ingest_agent_run_artifact",
    "ingest_agent_run_artifacts",
    "load_agent_run_artifact",
    "load_agent_run_artifacts_from_dir",
    "load_agent_run_artifacts_with_paths",
    "make_agent_run_id",
    "parse_patch_summary_from_artifact",
    "save_agent_run_artifact",
    "save_agent_run_artifact_folder",
    "validate_agent_run_artifact",
    "verify_agent_run_artifact",
    "verify_agent_run_artifacts",
    "verify_ingested_agent_run",
    "verify_ingested_agent_runs",
]
