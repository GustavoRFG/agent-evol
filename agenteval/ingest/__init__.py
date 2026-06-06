"""Generic evidence ingestion adapters for AgentEval Forge."""

from agenteval.ingest.generic_adapter import (
    EVIDENCE_LEVEL_HASH_BOUND,
    EVIDENCE_LEVEL_PATCH_ONLY,
    EVIDENCE_LEVEL_SELF_REPORTED,
    EVIDENCE_LEVEL_VERIFIED_RESERVED,
    GenericAgentRunAdapter,
    GenericAgentRunAdapterError,
    GenericAgentRunNormalization,
    evaluate_generic_agent_run,
)

__all__ = [
    "EVIDENCE_LEVEL_HASH_BOUND",
    "EVIDENCE_LEVEL_PATCH_ONLY",
    "EVIDENCE_LEVEL_SELF_REPORTED",
    "EVIDENCE_LEVEL_VERIFIED_RESERVED",
    "GenericAgentRunAdapter",
    "GenericAgentRunAdapterError",
    "GenericAgentRunNormalization",
    "evaluate_generic_agent_run",
]
