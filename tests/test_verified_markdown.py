"""Tests for the integrated verified comparison + claim analysis Markdown helper."""

from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    ClaimAnalysisReport,
    VerifiedMarkdownError,
    build_and_render_verified_comparison_with_claims_markdown,
    build_verified_comparison_and_claim_report,
    extract_attempted_results_for_claim_analysis,
    render_verified_comparison_with_claims_markdown,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
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


def _pack():
    return load_benchmark_pack(PACK_DIR)


def _layouts(pack):
    return {
        layout.task_id: layout
        for layout in resolve_pack_fixture_layouts(pack, project_root=REPO_ROOT)
    }


def _three_agent_artifacts() -> list[AgentRunArtifact]:
    return [
        AgentRunArtifact(
            agent_name="alpha_correct",
            task_id="bugfix_005",
            run_id="alpha_correct:bugfix_005:001",
            diff_text=ALPHA_CORRECT_PATCH,
            final_message="Inclusive comparisons.",
            claimed_public_tests_passed=True,
            claimed_hidden_tests_passed=True,
        ),
        AgentRunArtifact(
            agent_name="beta_wrong_overclaim",
            task_id="bugfix_005",
            run_id="beta_wrong_overclaim:bugfix_005:001",
            diff_text=BETA_WRONG_PATCH,
            final_message="All passing!",  # lie
            claimed_public_tests_passed=True,
            claimed_hidden_tests_passed=True,
        ),
        AgentRunArtifact(
            agent_name="gamma_no_patch_or_invalid",
            task_id="bugfix_005",
            run_id="gamma_no_patch_or_invalid:bugfix_005:001",
            diff_text=GAMMA_INVALID_PATCH,
            final_message="Tried something.",
            claimed_public_tests_passed=True,
        ),
    ]


# ---- build_verified_comparison_and_claim_report ----------------------------


def test_helper_builds_both_reports(tmp_path: Path):
    pack = _pack()
    artifacts = _three_agent_artifacts()

    comparison, claim_report = build_verified_comparison_and_claim_report(
        pack, artifacts, _layouts(pack), workspace_root=tmp_path,
    )

    assert isinstance(comparison, ComparisonReport)
    assert isinstance(claim_report, ClaimAnalysisReport)
    assert set(comparison.agents) == {
        "alpha_correct",
        "beta_wrong_overclaim",
        "gamma_no_patch_or_invalid",
    }
    assert set(claim_report.rollups_by_agent) == set(comparison.agents)


def test_claimed_results_do_not_determine_ranking(tmp_path: Path):
    pack = _pack()
    comparison, _ = build_verified_comparison_and_claim_report(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    means = comparison.mean_scores_by_agent
    # All three claimed pass; only the correct patch actually passes tests.
    assert means["alpha_correct"] > means["beta_wrong_overclaim"]
    assert means["alpha_correct"] > means["gamma_no_patch_or_invalid"]
    assert comparison.ranking[0] == "alpha_correct"


def test_claim_report_flags_overclaimer(tmp_path: Path):
    pack = _pack()
    _, claim_report = build_verified_comparison_and_claim_report(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    beta = claim_report.rollups_by_agent["beta_wrong_overclaim"]
    assert beta.overclaims >= 1
    assert beta.mismatching_claims >= 1
    assert "beta_wrong_overclaim:bugfix_005:001" in beta.mismatch_run_ids

    # Alpha's claims match the verified outcome.
    alpha = claim_report.rollups_by_agent["alpha_correct"]
    assert alpha.mismatching_claims == 0
    assert alpha.claim_reliability == 1.0


def test_helper_non_list_artifacts_raises(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedMarkdownError, match="artifacts"):
        build_verified_comparison_and_claim_report(
            pack,
            _three_agent_artifacts()[0],  # type: ignore[arg-type]
            _layouts(pack),
            workspace_root=tmp_path,
        )


def test_helper_propagates_verified_comparison_error(tmp_path: Path):
    pack = _pack()
    bad = AgentRunArtifact(
        agent_name="x",
        task_id="bugfix_999",  # not in pack
        run_id="x:bugfix_999:001",
        diff_text=ALPHA_CORRECT_PATCH,
    )
    with pytest.raises(VerifiedMarkdownError, match="ComparisonReport"):
        build_verified_comparison_and_claim_report(
            pack, [bad], _layouts(pack), workspace_root=tmp_path,
        )


# ---- extract_attempted_results_for_claim_analysis --------------------------


def test_attempted_result_extraction_excludes_placeholders(tmp_path: Path):
    pack = _pack()
    artifacts = _three_agent_artifacts()
    comparison, _ = build_verified_comparison_and_claim_report(
        pack, artifacts, _layouts(pack), workspace_root=tmp_path,
    )
    attempted = extract_attempted_results_for_claim_analysis(
        comparison, artifacts
    )
    artifact_run_ids = {a.run_id for a in artifacts}
    # Every extracted result corresponds to an artifact.
    assert {r.run_id for r in attempted} == artifact_run_ids
    # No placeholder run_ids slipped through.
    assert not any(":placeholder" in r.run_id for r in attempted)


def test_attempted_result_extraction_preserves_ordering(tmp_path: Path):
    pack = _pack()
    artifacts = _three_agent_artifacts()
    comparison, _ = build_verified_comparison_and_claim_report(
        pack, artifacts, _layouts(pack), workspace_root=tmp_path,
    )
    attempted = extract_attempted_results_for_claim_analysis(
        comparison, artifacts
    )
    # Verified-reporting orders agents alphabetically.
    assert [r.run_id for r in attempted] == [
        "alpha_correct:bugfix_005:001",
        "beta_wrong_overclaim:bugfix_005:001",
        "gamma_no_patch_or_invalid:bugfix_005:001",
    ]


def test_attempted_result_extraction_rejects_non_comparison():
    with pytest.raises(VerifiedMarkdownError, match="ComparisonReport"):
        extract_attempted_results_for_claim_analysis(
            "not a comparison",  # type: ignore[arg-type]
            [],
        )


def test_attempted_result_extraction_rejects_non_list_artifacts():
    pack = _pack()
    # Build a small valid comparison just to have one to pass.
    with pytest.raises(VerifiedMarkdownError, match="artifacts"):
        extract_attempted_results_for_claim_analysis(
            ComparisonReport(pack_name=pack.name, pack_version=pack.version),
            "not a list",  # type: ignore[arg-type]
        )


# ---- render_verified_comparison_with_claims_markdown -----------------------


def test_combined_markdown_includes_comparison_sections(tmp_path: Path):
    pack = _pack()
    md = build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    assert "# AgentEval Forge — Cross-Agent Comparison" in md
    for section in (
        "## Ranking",
        "## Pairwise summary",
        "## Per-task score matrix",
        "## Tasks where agents most disagree",
        "## Weakness tally by agent",
    ):
        assert section in md


def test_combined_markdown_includes_claim_analysis_sections(tmp_path: Path):
    pack = _pack()
    md = build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    assert "# Agent claim analysis report" in md
    for section in (
        "## Totals",
        "## Per-agent rollup",
        "## Mismatch details",
    ):
        assert section in md


def test_combined_markdown_includes_reliability_columns(tmp_path: Path):
    pack = _pack()
    md = build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    for header in (
        "Reliability",
        "Mismatch rate",
        "Overclaim rate",
        "Underclaim rate",
        "No-claim rate",
    ):
        assert header in md


def test_combined_markdown_flags_overclaimer(tmp_path: Path):
    pack = _pack()
    md = build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    mismatch_section = md.split("## Mismatch details", 1)[1]
    assert "beta_wrong_overclaim" in mismatch_section


def test_combined_markdown_includes_reliability_note(tmp_path: Path):
    pack = _pack()
    md = build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    assert "informational" in md.lower()
    assert "score" in md.lower() and "ranking" in md.lower()


def test_combined_markdown_has_section_separator(tmp_path: Path):
    pack = _pack()
    md = build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    # The renderer joins the two sections with a horizontal-rule separator.
    assert "\n---\n" in md


def test_render_rejects_non_comparison():
    with pytest.raises(VerifiedMarkdownError, match="comparison"):
        render_verified_comparison_with_claims_markdown(
            "not a comparison",  # type: ignore[arg-type]
            ClaimAnalysisReport(),
        )


def test_render_rejects_non_claim_report():
    pack = _pack()
    with pytest.raises(VerifiedMarkdownError, match="claim_report"):
        render_verified_comparison_with_claims_markdown(
            ComparisonReport(pack_name=pack.name, pack_version=pack.version),
            "not a report",  # type: ignore[arg-type]
        )


# ---- side-effect boundary --------------------------------------------------


def test_no_reports_generated_files_are_written(tmp_path: Path):
    pack = _pack()
    build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    generated_dir = REPO_ROOT / "reports" / "generated"
    assert not (generated_dir / "week7_day2_verified_markdown.md").exists()


def test_original_fixture_is_not_mutated(tmp_path: Path):
    pack = _pack()
    target_task = next(t for t in pack.tasks if t.task_id == "bugfix_005")
    original_file = REPO_ROOT / target_task.repo_path / "is_within_range.py"
    snapshot = original_file.read_bytes()

    build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    assert original_file.read_bytes() == snapshot


# ---- one-call helper sanity ------------------------------------------------


def test_one_call_helper_returns_string(tmp_path: Path):
    pack = _pack()
    md = build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    assert isinstance(md, str)
    assert md.endswith("\n")


def test_verified_result_has_no_verify_weakness_for_alpha(tmp_path: Path):
    pack = _pack()
    comparison, _ = build_verified_comparison_and_claim_report(
        pack,
        _three_agent_artifacts(),
        _layouts(pack),
        workspace_root=tmp_path,
    )
    alpha = next(r for r in comparison.reports if r.agent_name == "alpha_correct")
    by_task = {r.task_id: r for r in alpha.results}
    assert by_task["bugfix_005"].passed_public_tests is True
    assert by_task["bugfix_005"].passed_hidden_tests is True
    assert WeaknessCode.VERIFY not in by_task["bugfix_005"].weaknesses
