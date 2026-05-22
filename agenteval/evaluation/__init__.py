"""Evidence-attachment, result-building, and batch helpers for AgentEval Forge."""

from agenteval.evaluation.batch_builder import (
    BatchEvaluationError,
    TaskEvidence,
    build_pack_evaluation_results,
)
from agenteval.evaluation.pack_report import (
    evaluate_pack_to_json_report,
    evaluate_pack_to_markdown_report,
    evaluate_pack_to_report,
)
from agenteval.evaluation.patch_evidence import (
    attach_patch_summary_to_result,
    attach_patch_to_result,
)
from agenteval.evaluation.result_builder import (
    build_evaluation_result,
    build_unverified_result,
)

__all__ = [
    "BatchEvaluationError",
    "TaskEvidence",
    "attach_patch_summary_to_result",
    "attach_patch_to_result",
    "build_evaluation_result",
    "build_pack_evaluation_results",
    "build_unverified_result",
    "evaluate_pack_to_json_report",
    "evaluate_pack_to_markdown_report",
    "evaluate_pack_to_report",
]
