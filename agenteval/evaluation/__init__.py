"""Evidence-attachment helpers for AgentEval Forge evaluations."""

from agenteval.evaluation.patch_evidence import (
    attach_patch_summary_to_result,
    attach_patch_to_result,
)

__all__ = [
    "attach_patch_summary_to_result",
    "attach_patch_to_result",
]
