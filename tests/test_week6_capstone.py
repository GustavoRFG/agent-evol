"""Week 6 capstone: external agent_run.json folders -> verified comparison.

Demonstrates the full Week 6 verified evaluation pipeline end-to-end against
the shipped ``python_bugfix_basic`` benchmark pack:

    write simulated agent_run.json artifacts under tmp_path
        -> discover + load (Week 5 Day 3)
        -> build verified ComparisonReport (Week 6 Day 4)
        -> build ClaimAnalysisReport (Week 6 Day 6)
        -> render combined Markdown (Week 3 + Week 6 Day 6)

This is the verified counterpart of the Week 5 Day 7 capstone: attempted-task
results are checked by applying the diff in an isolated fixture copy and
running public + hidden tests, so the ranking is real. Agent claims are
collected by the claim-analysis report but never trusted as evidence.

The test writes only inside ``tmp_path`` and must never touch
``reports/generated/``.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.agent_runs import (
    AgentRunArtifact,
    build_claim_analysis_report_from_artifacts_and_results,
    build_verified_comparison_report_from_agent_artifact_dir,
    load_agent_run_artifacts_from_dir,
    render_claim_analysis_report_markdown,
    save_agent_run_artifact_folder,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.comparison import render_comparison_report_markdown
from agenteval.core.schemas import ComparisonReport, WeaknessCode
from agenteval.fixtures import resolve_pack_fixture_layouts

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

ALPHA_CORRECT_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -12,4 +12,4 @@ def is_within_range(value, low, high):
     The function should be inclusive on both bounds, but currently uses
     strict inequalities.
     """
-    return low < value < high
+    return low <= value <= high
'''

BETA_WRONG_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -12,4 +12,4 @@ def is_within_range(value, low, high):
     The function should be inclusive on both bounds, but currently uses
     strict inequalities.
     """
-    return low < value < high
+    return low == value == high
'''

GAMMA_INVALID_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -999,1 +999,1 @@
-this line does not exist
+this line will never apply
'''


def _write_capstone_artifacts(root: Path) -> list[Path]:
    """Lay out simulated external-agent artifacts under ``root``.

    Four agents with deliberately different combinations of correctness and
    claim honesty so the verified ranking and the claim-analysis rollup each
    surface something interesting.
    """
    artifacts: list[tuple[Path, AgentRunArtifact]] = [
        # A: correct patch, accurate claims (matches verified outcome).
        (
            root / "alpha_correct" / "bugfix_005",
            AgentRunArtifact(
                agent_name="alpha_correct",
                task_id="bugfix_005",
                run_id="alpha_correct:bugfix_005:001",
                diff_text=ALPHA_CORRECT_PATCH,
                final_message="Switched to inclusive comparisons.",
                claimed_commands=["pytest -q"],
                claimed_public_tests_passed=True,
                claimed_hidden_tests_passed=True,
                metadata={"agent": "alpha-simulated"},
            ),
        ),
        # B: wrong-but-clean patch, overclaims both buckets.
        (
            root / "beta_wrong_overclaim" / "bugfix_005",
            AgentRunArtifact(
                agent_name="beta_wrong_overclaim",
                task_id="bugfix_005",
                run_id="beta_wrong_overclaim:bugfix_005:001",
                diff_text=BETA_WRONG_PATCH,
                final_message="All passing!",  # lie
                claimed_commands=["pytest"],
                claimed_public_tests_passed=True,
                claimed_hidden_tests_passed=True,
                metadata={"agent": "beta-simulated"},
            ),
        ),
        # C: invalid patch, claims public pass anyway.
        (
            root / "gamma_no_patch_or_invalid" / "bugfix_005",
            AgentRunArtifact(
                agent_name="gamma_no_patch_or_invalid",
                task_id="bugfix_005",
                run_id="gamma_no_patch_or_invalid:bugfix_005:001",
                diff_text=GAMMA_INVALID_PATCH,
                final_message="Tried something.",
                claimed_commands=[],
                claimed_public_tests_passed=True,
                metadata={"agent": "gamma-simulated"},
            ),
        ),
        # D: empty patch, modestly claims failure (underclaim — verified
        # outcome will also be failure, so this is actually a *match*).
        (
            root / "delta_honest_failure" / "bugfix_005",
            AgentRunArtifact(
                agent_name="delta_honest_failure",
                task_id="bugfix_005",
                run_id="delta_honest_failure:bugfix_005:001",
                diff_text="",  # nothing to verify
                final_message="I couldn't fix it.",
                claimed_commands=[],
                claimed_public_tests_passed=False,
                claimed_hidden_tests_passed=False,
                metadata={"agent": "delta-simulated"},
            ),
        ),
    ]
    written: list[Path] = []
    for folder, artifact in artifacts:
        written.append(save_agent_run_artifact_folder(artifact, folder))
    return written


def _layouts_for_pack(pack):
    return {
        layout.task_id: layout
        for layout in resolve_pack_fixture_layouts(
            pack, project_root=REPO_ROOT
        )
    }


def test_week6_capstone_full_verified_pipeline(tmp_path: Path):
    runs_root = tmp_path / "agent_runs"
    workspace_root = tmp_path / "workspaces"

    written_paths = _write_capstone_artifacts(runs_root)
    assert len(written_paths) == 4

    # --- discovery + loading (Week 5 Day 3) ---------------------------------
    loaded = load_agent_run_artifacts_from_dir(runs_root)
    assert len(loaded) == 4
    assert {a.agent_name for a in loaded} == {
        "alpha_correct",
        "beta_wrong_overclaim",
        "gamma_no_patch_or_invalid",
        "delta_honest_failure",
    }

    pack = load_benchmark_pack(PACK_DIR)
    layouts = _layouts_for_pack(pack)

    # --- verified ComparisonReport (Week 6 Day 4) ---------------------------
    comparison = build_verified_comparison_report_from_agent_artifact_dir(
        pack, runs_root, layouts, workspace_root=workspace_root,
    )
    assert isinstance(comparison, ComparisonReport)
    assert comparison.pack_name == "python_bugfix_basic"
    assert set(comparison.agents) == {
        "alpha_correct",
        "beta_wrong_overclaim",
        "gamma_no_patch_or_invalid",
        "delta_honest_failure",
    }
    assert comparison.total_tasks == len(pack.tasks)

    means = comparison.mean_scores_by_agent
    # Ranking must be non-degenerate: at least one agent stands apart.
    assert len(set(means.values())) >= 2
    # Alpha has a positive mean (one task scored, rest unattempted/zero).
    assert means["alpha_correct"] > 0.0
    # Alpha outranks the others.
    assert means["alpha_correct"] > means["beta_wrong_overclaim"]
    assert means["alpha_correct"] > means["gamma_no_patch_or_invalid"]
    assert means["alpha_correct"] > means["delta_honest_failure"]
    # And the ranking puts alpha first.
    assert comparison.ranking[0] == "alpha_correct"

    # Alpha's bugfix_005 result is genuinely verified.
    alpha = next(r for r in comparison.reports if r.agent_name == "alpha_correct")
    alpha_by_task = {r.task_id: r for r in alpha.results}
    assert alpha_by_task["bugfix_005"].passed_public_tests is True
    assert alpha_by_task["bugfix_005"].passed_hidden_tests is True
    assert WeaknessCode.VERIFY not in alpha_by_task["bugfix_005"].weaknesses

    # Beta's bugfix_005 is a real failure (not blocked by exception).
    beta = next(
        r for r in comparison.reports if r.agent_name == "beta_wrong_overclaim"
    )
    beta_by_task = {r.task_id: r for r in beta.results}
    assert beta_by_task["bugfix_005"].passed_public_tests is False
    assert beta_by_task["bugfix_005"].passed_hidden_tests is False

    # --- claim non-trust (Week 6 Day 4 invariant) ---------------------------
    # Beta and gamma both claimed public pass, but real outcomes are false.
    # Their ranking must not benefit from those claims.
    assert means["beta_wrong_overclaim"] < means["alpha_correct"]
    assert means["gamma_no_patch_or_invalid"] < means["alpha_correct"]

    # --- ClaimAnalysisReport (Week 6 Day 6) ---------------------------------
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
    # Beta overclaimed both buckets — must be in rollup.
    beta_rollup = claim_report.rollups_by_agent["beta_wrong_overclaim"]
    assert beta_rollup.overclaims >= 1
    assert beta_rollup.mismatching_claims >= 1
    beta_wrong_runid = "beta_wrong_overclaim:bugfix_005:001"
    assert beta_wrong_runid in beta_rollup.mismatch_run_ids
    # Alpha's claims match the verified outcome — no mismatches.
    alpha_rollup = claim_report.rollups_by_agent["alpha_correct"]
    assert alpha_rollup.mismatching_claims == 0
    assert alpha_rollup.overclaims == 0
    # Delta's claims also match (claimed fail, verified fail).
    delta_rollup = claim_report.rollups_by_agent["delta_honest_failure"]
    assert delta_rollup.mismatching_claims == 0
    # Gamma overclaimed public.
    gamma_rollup = claim_report.rollups_by_agent[
        "gamma_no_patch_or_invalid"
    ]
    assert gamma_rollup.overclaims >= 1

    assert claim_report.total_overclaims >= 2
    assert claim_report.total_mismatches >= 2

    # --- combined Markdown --------------------------------------------------
    comparison_md = render_comparison_report_markdown(comparison)
    claim_md = render_claim_analysis_report_markdown(claim_report)
    combined_md = comparison_md + "\n\n" + claim_md

    # Comparison sections.
    assert "# AgentEval Forge — Cross-Agent Comparison" in combined_md
    assert "## Ranking" in combined_md
    assert "## Pairwise summary" in combined_md
    assert "## Per-task score matrix" in combined_md
    assert "## Tasks where agents most disagree" in combined_md
    assert "## Weakness tally by agent" in combined_md
    # Claim analysis sections.
    assert "# Agent claim analysis report" in combined_md
    assert "## Per-agent rollup" in combined_md
    assert "## Mismatch details" in combined_md
    # The overclaiming agent must appear in the mismatch section.
    mismatch_section = combined_md.split("## Mismatch details", 1)[1]
    assert "beta_wrong_overclaim" in mismatch_section
    # All four agent names appear in the combined output.
    for agent in (
        "alpha_correct",
        "beta_wrong_overclaim",
        "gamma_no_patch_or_invalid",
        "delta_honest_failure",
    ):
        assert agent in combined_md

    # --- side-effect boundary ----------------------------------------------
    generated_dir = REPO_ROOT / "reports" / "generated"
    for marker in (
        generated_dir / "week6_verified_capstone.md",
        generated_dir / "week6_verified_capstone.json",
    ):
        assert not marker.exists(), (
            f"capstone test must not write to {marker}"
        )

    # --- original fixture immutability -------------------------------------
    target_task = next(t for t in pack.tasks if t.task_id == "bugfix_005")
    original_file = REPO_ROOT / target_task.repo_path / "is_within_range.py"
    assert "low < value < high" in original_file.read_text(encoding="utf-8")
