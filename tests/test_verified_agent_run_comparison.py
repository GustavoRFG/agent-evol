"""Tests for verified cross-agent ComparisonReports from external artifacts."""

from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    VerifiedAgentRunComparisonError,
    build_verified_comparison_report_from_agent_artifact_dir,
    build_verified_comparison_report_from_agent_artifacts,
    render_verified_comparison_markdown_from_agent_artifacts,
    save_agent_run_artifact_folder,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import ComparisonReport, WeaknessCode
from agenteval.fixtures import resolve_task_fixture_layout

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

BUGFIX_005_GOOD_PATCH = '''\
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

BUGFIX_005_WRONG_PATCH = '''\
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

BUGFIX_005_INVALID_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -999,1 +999,1 @@
-this line does not exist
+this line will never apply
'''


def _pack():
    return load_benchmark_pack(PACK_DIR)


def _layouts_for_pack(pack):
    return {
        task.task_id: resolve_task_fixture_layout(task, project_root=REPO_ROOT)
        for task in pack.tasks
    }


def _artifact(
    *,
    agent_name: str,
    task_id: str = "bugfix_005",
    run_id: str | None = None,
    diff_text: str = BUGFIX_005_GOOD_PATCH,
    **overrides,
) -> AgentRunArtifact:
    return AgentRunArtifact(
        agent_name=agent_name,
        task_id=task_id,
        run_id=run_id or f"{agent_name}:{task_id}:001",
        diff_text=diff_text,
        **overrides,
    )


# ---- happy path: two agents -------------------------------------------------


def test_two_agents_produce_verified_comparison_report(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(agent_name="beta-agent", diff_text=BUGFIX_005_WRONG_PATCH),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )

    assert isinstance(comparison, ComparisonReport)
    assert comparison.pack_name == "python_bugfix_basic"
    assert comparison.pack_version == "1.0"
    assert set(comparison.agents) == {"alpha-agent", "beta-agent"}
    assert comparison.total_tasks == len(pack.tasks)


def test_correct_patch_beats_wrong_patch(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(agent_name="beta-agent", diff_text=BUGFIX_005_WRONG_PATCH),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    means = comparison.mean_scores_by_agent
    assert means["alpha-agent"] > means["beta-agent"]
    # And the alpha agent's mean is genuinely positive.
    assert means["alpha-agent"] > 0.0


def test_correct_patch_beats_missing_artifact(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        # beta-agent has no artifact at all.
        _artifact(
            agent_name="beta-agent",
            task_id="bugfix_001",
            diff_text="",  # empty -> verification failure (lenient)
        ),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    means = comparison.mean_scores_by_agent
    assert means["alpha-agent"] > means["beta-agent"]
    assert means["beta-agent"] == 0.0


def test_ranking_is_non_degenerate(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(agent_name="beta-agent", diff_text=BUGFIX_005_WRONG_PATCH),
        _artifact(
            agent_name="gamma-agent", diff_text=BUGFIX_005_INVALID_PATCH
        ),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    means = list(comparison.mean_scores_by_agent.values())
    # At least one agent has a different mean score from the others.
    assert len(set(means)) >= 2
    # Alpha is at the top.
    assert comparison.ranking[0] == "alpha-agent"


# ---- per-result evidence on the verified path ------------------------------


def test_verified_successful_task_has_no_verify_weakness(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(agent_name="beta-agent", diff_text=BUGFIX_005_WRONG_PATCH),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    alpha = next(r for r in comparison.reports if r.agent_name == "alpha-agent")
    by_task = {r.task_id: r for r in alpha.results}
    assert by_task["bugfix_005"].passed_public_tests is True
    assert by_task["bugfix_005"].passed_hidden_tests is True
    assert WeaknessCode.VERIFY not in by_task["bugfix_005"].weaknesses


def test_failed_and_missing_tasks_still_have_verify(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(
            agent_name="gamma-agent", diff_text=BUGFIX_005_INVALID_PATCH
        ),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    # gamma's bugfix_005 fails verification -> VERIFY recorded by the
    # verified-reporting failure path.
    gamma = next(r for r in comparison.reports if r.agent_name == "gamma-agent")
    by_task = {r.task_id: r for r in gamma.results}
    assert WeaknessCode.VERIFY in by_task["bugfix_005"].weaknesses
    # Tasks neither agent attempted are also VERIFY.
    for task in pack.tasks:
        if task.task_id == "bugfix_005":
            continue
        assert WeaknessCode.VERIFY in by_task[task.task_id].weaknesses


# ---- claim non-trust --------------------------------------------------------


def test_claimed_results_do_not_determine_ranking(tmp_path: Path):
    pack = _pack()
    artifacts = [
        # Modest: tells the truth poorly (claims fail) but actually succeeds.
        _artifact(
            agent_name="modest-agent",
            diff_text=BUGFIX_005_GOOD_PATCH,
            claimed_public_tests_passed=False,
            claimed_hidden_tests_passed=False,
        ),
        # Liar: claims success but its patch is semantically wrong.
        _artifact(
            agent_name="liar-agent",
            diff_text=BUGFIX_005_WRONG_PATCH,
            claimed_public_tests_passed=True,
            claimed_hidden_tests_passed=True,
        ),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    means = comparison.mean_scores_by_agent
    # Modest outranks liar because real tests beat claims.
    assert means["modest-agent"] > means["liar-agent"]
    assert comparison.ranking[0] == "modest-agent"


# ---- deterministic ordering ------------------------------------------------


def test_deterministic_agent_ordering_in_reports(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="zeta-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_WRONG_PATCH),
        _artifact(agent_name="mu-agent", diff_text=BUGFIX_005_INVALID_PATCH),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    # Reports come back in alphabetical agent order (inherited from
    # build_verified_run_reports_from_agent_artifacts).
    assert [r.agent_name for r in comparison.reports] == [
        "alpha-agent", "mu-agent", "zeta-agent",
    ]


# ---- error contract --------------------------------------------------------


def test_unknown_task_id_raises_verified_comparison_error(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunComparisonError, match="not in pack"):
        build_verified_comparison_report_from_agent_artifacts(
            pack,
            [_artifact(agent_name="x-agent", task_id="bugfix_999")],
            _layouts_for_pack(pack),
            workspace_root=tmp_path,
        )


def test_invalid_patch_propagates_in_strict_mode(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(
            agent_name="alpha-agent", diff_text=BUGFIX_005_INVALID_PATCH
        ),
    ]
    with pytest.raises(VerifiedAgentRunComparisonError):
        build_verified_comparison_report_from_agent_artifacts(
            pack, artifacts, _layouts_for_pack(pack),
            workspace_root=tmp_path, continue_on_error=False,
        )


def test_invalid_patch_kept_in_lenient_mode(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(
            agent_name="beta-agent", diff_text=BUGFIX_005_INVALID_PATCH
        ),
    ]
    comparison = build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack),
        workspace_root=tmp_path, continue_on_error=True,
    )
    assert set(comparison.agents) == {"alpha-agent", "beta-agent"}


def test_empty_artifacts_raises(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunComparisonError, match="at least one"):
        build_verified_comparison_report_from_agent_artifacts(
            pack, [], _layouts_for_pack(pack), workspace_root=tmp_path,
        )


def test_non_list_artifacts_raises(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunComparisonError, match="artifacts"):
        build_verified_comparison_report_from_agent_artifacts(
            pack,
            _artifact(agent_name="x"),  # type: ignore[arg-type]
            _layouts_for_pack(pack),
            workspace_root=tmp_path,
        )


def test_non_pack_raises(tmp_path: Path):
    with pytest.raises(VerifiedAgentRunComparisonError, match="pack"):
        build_verified_comparison_report_from_agent_artifacts(
            "not a pack",  # type: ignore[arg-type]
            [],
            {},
            workspace_root=tmp_path,
        )


# ---- Markdown helper -------------------------------------------------------


def test_markdown_helper_contains_all_sections(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(agent_name="beta-agent", diff_text=BUGFIX_005_WRONG_PATCH),
    ]
    md = render_verified_comparison_markdown_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    assert "# AgentEval Forge — Cross-Agent Comparison" in md
    assert "## Ranking" in md
    assert "## Pairwise summary" in md
    assert "## Per-task score matrix" in md
    assert "## Tasks where agents most disagree" in md
    assert "## Weakness tally by agent" in md
    for agent in ("alpha-agent", "beta-agent"):
        assert agent in md


# ---- directory helper ------------------------------------------------------


def test_dir_helper_loads_and_builds_verified_comparison(tmp_path: Path):
    pack = _pack()
    layouts = _layouts_for_pack(pack)
    runs_root = tmp_path / "runs"
    workspace = tmp_path / "ws"

    save_agent_run_artifact_folder(
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        runs_root / "alpha" / "bugfix_005",
    )
    save_agent_run_artifact_folder(
        _artifact(agent_name="beta-agent", diff_text=BUGFIX_005_WRONG_PATCH),
        runs_root / "beta" / "bugfix_005",
    )

    comparison = build_verified_comparison_report_from_agent_artifact_dir(
        pack, runs_root, layouts, workspace_root=workspace,
    )
    assert set(comparison.agents) == {"alpha-agent", "beta-agent"}
    means = comparison.mean_scores_by_agent
    assert means["alpha-agent"] > means["beta-agent"]


# ---- side-effect boundary --------------------------------------------------


def test_no_generated_files_are_written_during_test(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
    ]
    render_verified_comparison_markdown_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    capstone_marker = (
        REPO_ROOT / "reports" / "generated"
        / "week6_verified_comparison.md"
    )
    assert not capstone_marker.exists()


def test_original_fixture_is_not_mutated(tmp_path: Path):
    pack = _pack()
    target_task = next(t for t in pack.tasks if t.task_id == "bugfix_005")
    original_file = REPO_ROOT / target_task.repo_path / "is_within_range.py"
    snapshot = original_file.read_bytes()

    artifacts = [
        _artifact(agent_name="alpha-agent", diff_text=BUGFIX_005_GOOD_PATCH),
        _artifact(agent_name="beta-agent", diff_text=BUGFIX_005_WRONG_PATCH),
        _artifact(
            agent_name="gamma-agent", diff_text=BUGFIX_005_INVALID_PATCH
        ),
    ]
    build_verified_comparison_report_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack), workspace_root=tmp_path,
    )
    assert original_file.read_bytes() == snapshot
