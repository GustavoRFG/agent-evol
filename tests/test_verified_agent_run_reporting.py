"""Tests for verified per-agent RunReport generation from external artifacts."""

from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    VerifiedAgentRunReportingError,
    build_verified_run_report_from_agent_artifacts,
    build_verified_run_reports_from_agent_artifact_dir,
    build_verified_run_reports_from_agent_artifacts,
    save_agent_run_artifact_folder,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import RunReport, WeaknessCode
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
    agent_name: str = "claude-code",
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


# ---- happy path: one correct artifact --------------------------------------


def test_one_correct_artifact_produces_run_report(tmp_path: Path):
    pack = _pack()
    layouts = _layouts_for_pack(pack)
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        layouts,
        workspace_root=tmp_path,
    )

    assert isinstance(report, RunReport)
    assert report.pack_name == "python_bugfix_basic"
    assert report.pack_version == "1.0"
    assert report.agent_name == "claude-code"
    assert report.total_tasks == len(pack.tasks)


def test_attempted_bugfix_005_passes_public_tests(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    assert by_task["bugfix_005"].passed_public_tests is True


def test_attempted_bugfix_005_passes_hidden_tests(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    assert by_task["bugfix_005"].passed_hidden_tests is True


def test_attempted_bugfix_005_has_no_verify_weakness(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    assert WeaknessCode.VERIFY not in by_task["bugfix_005"].weaknesses


def test_attempted_bugfix_005_has_high_score(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    assert by_task["bugfix_005"].score >= 0.9


def test_attempted_result_carries_patch_summary(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    result = by_task["bugfix_005"]
    assert result.patch_summary is not None
    assert "is_within_range.py" in result.patch_summary.changed_files


# ---- coverage of pack -------------------------------------------------------


def test_missing_pack_tasks_become_unverified_results(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    # Everything other than bugfix_005 is unattempted-unverified.
    for task in pack.tasks:
        if task.task_id == "bugfix_005":
            continue
        result = by_task[task.task_id]
        assert result.passed_public_tests is False
        assert result.passed_hidden_tests is False
        assert WeaknessCode.VERIFY in result.weaknesses
        assert "no external agent artifact" in result.rationale.lower()


def test_run_report_covers_every_task_in_pack(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    assert [r.task_id for r in report.results] == [t.task_id for t in pack.tasks]


def test_mean_score_is_positive_when_one_task_verifies(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    # 1/N tasks at score >= 0.9, rest at 0.0 — mean must be > 0.
    assert report.mean_score > 0.0


def test_pack_task_order_is_preserved(tmp_path: Path):
    pack = _pack()
    expected_order = [t.task_id for t in pack.tasks]
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    assert [r.task_id for r in report.results] == expected_order


# ---- claim non-trust + agent isolation --------------------------------------


def test_agent_claims_do_not_determine_verified_outcomes(tmp_path: Path):
    pack = _pack()
    # Claims that the wrong patch passed should not override real test results.
    wrong_patch = '''\
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
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [
            _artifact(
                diff_text=wrong_patch,
                claimed_public_tests_passed=True,
                claimed_hidden_tests_passed=True,
            )
        ],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    result = by_task["bugfix_005"]
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False


def test_artifacts_for_other_agents_are_ignored(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [
            _artifact(agent_name="codex"),  # not for this agent
        ],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    by_task = {r.task_id: r for r in report.results}
    # bugfix_005 is unattempted for claude-code.
    assert "no external agent artifact" in by_task["bugfix_005"].rationale.lower()
    assert WeaknessCode.VERIFY in by_task["bugfix_005"].weaknesses


# ---- argument-shape errors --------------------------------------------------


def test_unknown_task_id_raises(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunReportingError, match="not in pack"):
        build_verified_run_report_from_agent_artifacts(
            pack,
            "claude-code",
            [_artifact(task_id="bugfix_999")],
            _layouts_for_pack(pack),
            workspace_root=tmp_path,
        )


def test_duplicate_artifacts_raise(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(run_id="r1"),
        _artifact(run_id="r2"),
    ]
    with pytest.raises(VerifiedAgentRunReportingError, match="duplicate"):
        build_verified_run_report_from_agent_artifacts(
            pack,
            "claude-code",
            artifacts,
            _layouts_for_pack(pack),
            workspace_root=tmp_path,
        )


def test_empty_agent_name_raises(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunReportingError, match="agent_name"):
        build_verified_run_report_from_agent_artifacts(
            pack, "", [_artifact()], _layouts_for_pack(pack),
            workspace_root=tmp_path,
        )


def test_non_list_artifacts_raises(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunReportingError, match="artifacts"):
        build_verified_run_report_from_agent_artifacts(
            pack,
            "claude-code",
            _artifact(),  # type: ignore[arg-type]
            _layouts_for_pack(pack),
            workspace_root=tmp_path,
        )


def test_non_dict_layouts_raises(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunReportingError, match="layouts_by_task_id"):
        build_verified_run_report_from_agent_artifacts(
            pack,
            "claude-code",
            [_artifact()],
            [("bugfix_005", None)],  # type: ignore[arg-type]
            workspace_root=tmp_path,
        )


# ---- failure modes during verification --------------------------------------


def test_invalid_patch_becomes_failed_result_when_lenient(tmp_path: Path):
    pack = _pack()
    report = build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact(diff_text=BUGFIX_005_INVALID_PATCH)],
        _layouts_for_pack(pack),
        workspace_root=tmp_path,
        continue_on_error=True,
    )
    by_task = {r.task_id: r for r in report.results}
    result = by_task["bugfix_005"]
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert "verification failed" in result.rationale.lower()


def test_invalid_patch_propagates_when_strict(tmp_path: Path):
    pack = _pack()
    with pytest.raises(VerifiedAgentRunReportingError, match="verification failed"):
        build_verified_run_report_from_agent_artifacts(
            pack,
            "claude-code",
            [_artifact(diff_text=BUGFIX_005_INVALID_PATCH)],
            _layouts_for_pack(pack),
            workspace_root=tmp_path,
            continue_on_error=False,
        )


# ---- per-agent workspace isolation -----------------------------------------


def test_each_agent_uses_its_own_workspace_subdir(tmp_path: Path):
    pack = _pack()
    layouts = _layouts_for_pack(pack)

    build_verified_run_report_from_agent_artifacts(
        pack, "claude-code", [_artifact(agent_name="claude-code")],
        layouts, workspace_root=tmp_path,
    )
    build_verified_run_report_from_agent_artifacts(
        pack, "codex", [_artifact(agent_name="codex")],
        layouts, workspace_root=tmp_path,
    )

    subdirs = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert "claude-code" in subdirs
    assert "codex" in subdirs


# ---- batch helpers ---------------------------------------------------------


def test_batch_helper_returns_one_report_per_agent(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="claude-code"),
        _artifact(agent_name="codex"),
    ]
    reports = build_verified_run_reports_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    assert len(reports) == 2
    by_agent = {r.agent_name: r for r in reports}
    assert set(by_agent) == {"claude-code", "codex"}
    for report in reports:
        assert report.total_tasks == len(pack.tasks)


def test_batch_helper_deterministic_agent_ordering(tmp_path: Path):
    pack = _pack()
    artifacts = [
        _artifact(agent_name="zeta-agent"),
        _artifact(agent_name="alpha-agent"),
        _artifact(agent_name="mu-agent"),
    ]
    reports = build_verified_run_reports_from_agent_artifacts(
        pack, artifacts, _layouts_for_pack(pack),
        workspace_root=tmp_path,
    )
    assert [r.agent_name for r in reports] == [
        "alpha-agent", "mu-agent", "zeta-agent",
    ]


def test_batch_helper_empty_artifacts_returns_empty_list(tmp_path: Path):
    pack = _pack()
    assert (
        build_verified_run_reports_from_agent_artifacts(
            pack, [], _layouts_for_pack(pack), workspace_root=tmp_path,
        )
        == []
    )


def test_dir_helper_loads_and_builds_verified_reports(tmp_path: Path):
    pack = _pack()
    layouts = _layouts_for_pack(pack)
    runs_root = tmp_path / "runs"
    workspace = tmp_path / "ws"

    save_agent_run_artifact_folder(
        _artifact(agent_name="claude-code"),
        runs_root / "claude-code" / "bugfix_005",
    )
    save_agent_run_artifact_folder(
        _artifact(agent_name="codex", task_id="bugfix_001", diff_text=""),
        runs_root / "codex" / "bugfix_001",
    )

    reports = build_verified_run_reports_from_agent_artifact_dir(
        pack, runs_root, layouts, workspace_root=workspace,
    )

    assert [r.agent_name for r in reports] == ["claude-code", "codex"]
    claude_results = {r.task_id: r for r in reports[0].results}
    # Claude actually verified bugfix_005.
    assert claude_results["bugfix_005"].passed_public_tests is True
    assert WeaknessCode.VERIFY not in claude_results["bugfix_005"].weaknesses
    # Codex's empty-diff artifact failed verification leniently.
    codex_results = {r.task_id: r for r in reports[1].results}
    assert WeaknessCode.VERIFY in codex_results["bugfix_001"].weaknesses


# ---- side-effect boundary ---------------------------------------------------


def test_original_fixture_is_not_mutated(tmp_path: Path):
    pack = _pack()
    layouts = _layouts_for_pack(pack)
    target_task = next(t for t in pack.tasks if t.task_id == "bugfix_005")
    original_file = REPO_ROOT / target_task.repo_path / "is_within_range.py"
    snapshot = original_file.read_bytes()

    build_verified_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [_artifact()],
        layouts,
        workspace_root=tmp_path,
    )
    assert original_file.read_bytes() == snapshot
    assert "low < value < high" in snapshot.decode("utf-8")
