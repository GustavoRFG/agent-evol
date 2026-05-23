"""Week 5 capstone: external agent_run.json folders -> ComparisonReport.

End-to-end demonstration of the Week 5 ingestion pipeline against the shipped
``python_bugfix_basic`` benchmark pack:

    write simulated agent_run.json artifacts under a temporary directory
        -> discover + load (Week 5 Day 3)
        -> build per-agent RunReports (Week 5 Day 6)
        -> build_comparison_report (Week 3)
        -> render Markdown (Week 3)
        -> persist JSON + Markdown to reports/generated/ (only via __main__)

It performs **no** real agent execution: no Claude Code, Codex, ForgeAgent,
DGM, external APIs, or network calls; no patches are applied; no target tests
are run. The agent's ``claimed_*`` flags are surfaced in rationale text but
never trusted as verified outcomes. Standard library only.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agenteval.agent_runs import (
    build_run_reports_from_agent_artifact_dir,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.comparison import (
    build_comparison_report,
    render_comparison_report_markdown,
    save_comparison_report,
    save_comparison_report_markdown,
)
from agenteval.core.schemas import ComparisonReport, RunReport

# Re-use the artifact-writing helper from the capstone test so the example and
# the test exercise exactly the same simulated layout.
from tests.test_week5_capstone import _write_capstone_artifacts

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"


def build_simulated_week5_capstone_reports(runs_root: Path) -> list[RunReport]:
    """Lay out simulated artifacts under ``runs_root`` and build RunReports.

    ``runs_root`` is created if needed. Existing files are not removed —
    callers typically pass a fresh ``tmp_path`` or temporary directory.
    """
    runs_root.mkdir(parents=True, exist_ok=True)
    _write_capstone_artifacts(runs_root)
    pack = load_benchmark_pack(PACK_DIR)
    return build_run_reports_from_agent_artifact_dir(pack, runs_root)


def build_simulated_week5_capstone_comparison(runs_root: Path) -> ComparisonReport:
    """Build the simulated Week 5 capstone :class:`ComparisonReport`."""
    return build_comparison_report(
        build_simulated_week5_capstone_reports(runs_root)
    )


def render_simulated_week5_capstone_markdown(runs_root: Path) -> str:
    """Render the simulated Week 5 capstone comparison as Markdown."""
    return render_comparison_report_markdown(
        build_simulated_week5_capstone_comparison(runs_root)
    )


def main() -> None:
    """Save the simulated Week 5 capstone comparison to ``reports/generated/``.

    Tests must not call this helper — it writes to a path outside any
    ``tmp_path`` fixture. The directory is gitignored.
    """
    out_dir = REPO_ROOT / "reports" / "generated"
    json_path = out_dir / "week5_external_artifact_comparison.json"
    md_path = out_dir / "week5_external_artifact_comparison.md"

    with tempfile.TemporaryDirectory(prefix="agenteval_week5_capstone_") as tmp:
        runs_root = Path(tmp) / "agent_runs"
        comparison = build_simulated_week5_capstone_comparison(runs_root)

    save_comparison_report(comparison, json_path)
    save_comparison_report_markdown(comparison, md_path)

    print(f"Saved JSON to {json_path}")
    print(f"Saved Markdown to {md_path}")


if __name__ == "__main__":
    main()
