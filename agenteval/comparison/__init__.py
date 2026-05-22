"""Cross-agent comparison for AgentEval Forge."""

from agenteval.comparison.comparison_report import (
    ComparisonReportError,
    build_comparison_report,
)
from agenteval.comparison.markdown import (
    render_comparison_report_markdown,
    save_comparison_report_markdown,
)

__all__ = [
    "ComparisonReportError",
    "build_comparison_report",
    "render_comparison_report_markdown",
    "save_comparison_report_markdown",
]
