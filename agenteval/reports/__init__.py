"""Run report aggregation, JSON persistence, and Markdown rendering."""

from agenteval.reports.markdown import (
    render_run_report_markdown,
    save_run_report_markdown,
)
from agenteval.reports.run_report import (
    RunReportError,
    build_run_report,
    load_run_report,
    run_report_from_dict,
    run_report_to_dict,
    save_run_report,
)

__all__ = [
    "RunReportError",
    "build_run_report",
    "load_run_report",
    "render_run_report_markdown",
    "run_report_from_dict",
    "run_report_to_dict",
    "save_run_report",
    "save_run_report_markdown",
]
