"""Evidence-attachment and result-building helpers for AgentEval Forge."""

from agenteval.evaluation.patch_evidence import (
    attach_patch_summary_to_result,
    attach_patch_to_result,
)
from agenteval.evaluation.result_builder import (
    build_evaluation_result,
    build_unverified_result,
)

__all__ = [
    "attach_patch_summary_to_result",
    "attach_patch_to_result",
    "build_evaluation_result",
    "build_unverified_result",
]
