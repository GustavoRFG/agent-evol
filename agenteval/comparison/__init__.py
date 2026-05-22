"""Cross-agent comparison for AgentEval Forge."""

from agenteval.comparison.comparison_report import (
    ComparisonReportError,
    build_comparison_report,
)
from agenteval.comparison.markdown import (
    render_comparison_report_markdown,
    save_comparison_report_markdown,
)
from agenteval.comparison.task_matrix import (
    ComparisonMatrixError,
    TaskScoreRow,
    build_task_score_matrix,
)

__all__ = [
    "ComparisonMatrixError",
    "ComparisonReportError",
    "TaskScoreRow",
    "build_comparison_report",
    "build_task_score_matrix",
    "render_comparison_report_markdown",
    "save_comparison_report_markdown",
]
