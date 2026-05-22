"""Cross-agent comparison for AgentEval Forge."""

from agenteval.comparison.comparison_report import (
    ComparisonReportError,
    build_comparison_report,
)
from agenteval.comparison.divergence import (
    TaskDivergence,
    build_task_divergence_report,
    top_divergent_tasks,
)
from agenteval.comparison.markdown import (
    render_comparison_report_markdown,
    save_comparison_report_markdown,
)
from agenteval.comparison.persistence import (
    ComparisonPersistenceError,
    comparison_report_from_dict,
    comparison_report_to_dict,
    load_comparison_report,
    save_comparison_report,
)
from agenteval.comparison.task_matrix import (
    ComparisonMatrixError,
    TaskScoreRow,
    build_task_score_matrix,
)

__all__ = [
    "ComparisonMatrixError",
    "ComparisonPersistenceError",
    "ComparisonReportError",
    "TaskDivergence",
    "TaskScoreRow",
    "build_comparison_report",
    "build_task_divergence_report",
    "build_task_score_matrix",
    "comparison_report_from_dict",
    "comparison_report_to_dict",
    "load_comparison_report",
    "render_comparison_report_markdown",
    "save_comparison_report",
    "save_comparison_report_markdown",
    "top_divergent_tasks",
]
