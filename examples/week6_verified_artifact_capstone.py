"""Week 6 capstone: external agent_run.json folders -> verified comparison.

End-to-end demonstration of the Week 6 verified evaluation pipeline against
the shipped ``python_bugfix_basic`` benchmark pack:

    write simulated agent_run.json artifacts under a temporary directory
        -> discover + load (Week 5 Day 3)
        -> build verified ComparisonReport (Week 6 Day 4)
        -> build ClaimAnalysisReport (Week 6 Day 6)
        -> render combined Markdown (Week 3 + Week 6 Day 6)
        -> persist Markdown to reports/generated/ (only via __main__)

It performs **no** real agent execution: no Claude Code, Codex, ForgeAgent,
DGM, external APIs, or network calls. The original fixture is never patched —
each verification copies the fixture into a temporary workspace first. Agent
``claimed_*`` flags are surfaced in the claim-analysis report but never
trusted as verified evidence. Standard library only.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agenteval.agent_runs import (
    build_claim_analysis_report_from_artifacts_and_results,
    build_verified_comparison_report_from_agent_artifact_dir,
    load_agent_run_artifacts_from_dir,
    render_claim_analysis_report_markdown,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.comparison import render_comparison_report_markdown
from agenteval.core.schemas import ComparisonReport
from agenteval.fixtures import resolve_pack_fixture_layouts

# Re-use the test's artifact-writer so the example and the capstone test
# exercise exactly the same simulated layout.
from tests.test_week6_capstone import _write_capstone_artifacts

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"


def _layouts_for_pack(pack):
    return {
        layout.task_id: layout
        for layout in resolve_pack_fixture_layouts(
            pack, project_root=REPO_ROOT
        )
    }


def build_simulated_week6_capstone(
    runs_root: Path, workspace_root: Path
) -> tuple[ComparisonReport, str]:
    """Lay out artifacts, run the full verified pipeline, return Markdown.

    Both ``runs_root`` and ``workspace_root`` are created if needed. Callers
    typically pass fresh temporary directories so neither persists across runs.
    """
    runs_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    _write_capstone_artifacts(runs_root)
    pack = load_benchmark_pack(PACK_DIR)
    layouts = _layouts_for_pack(pack)

    comparison = build_verified_comparison_report_from_agent_artifact_dir(
        pack, runs_root, layouts, workspace_root=workspace_root,
    )

    loaded = load_agent_run_artifacts_from_dir(runs_root)
    # Only attempted-task results have run_ids that match an artifact;
    # unattempted-task placeholders are excluded from claim analysis.
    artifact_run_ids = {a.run_id for a in loaded}
    flat_results = [
        r
        for report in comparison.reports
        for r in report.results
        if r.run_id in artifact_run_ids
    ]
    claim_report = build_claim_analysis_report_from_artifacts_and_results(
        loaded, flat_results,
    )

    combined_md = (
        render_comparison_report_markdown(comparison)
        + "\n\n"
        + render_claim_analysis_report_markdown(claim_report)
    )
    return comparison, combined_md


def main() -> None:
    """Build the capstone and save Markdown to ``reports/generated/``.

    Tests must not call this helper — it writes outside any ``tmp_path``
    fixture. The directory is gitignored.
    """
    out_dir = REPO_ROOT / "reports" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "week6_verified_capstone.md"

    with tempfile.TemporaryDirectory(prefix="agenteval_week6_capstone_") as tmp:
        tmp_path = Path(tmp)
        runs_root = tmp_path / "agent_runs"
        workspace_root = tmp_path / "workspaces"
        comparison, combined_md = build_simulated_week6_capstone(
            runs_root, workspace_root
        )

    md_path.write_text(combined_md, encoding="utf-8")

    print(f"Saved Markdown to {md_path}")
    print("Verified ranking:")
    for position, agent in enumerate(comparison.ranking, start=1):
        mean = comparison.mean_scores_by_agent[agent]
        print(f"  {position}. {agent}  (mean score {mean:.3f})")


if __name__ == "__main__":
    main()
