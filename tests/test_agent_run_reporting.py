"""Tests for building RunReports from external agent run artifacts."""

from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunReportingError,
    build_run_report_from_agent_artifacts,
    build_run_reports_from_agent_artifact_dir,
    build_run_reports_from_agent_artifacts,
    save_agent_run_artifact_folder,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    RunReport,
    TaskSpec,
    WeaknessCode,
)

VALID_DIFF = """diff --git a/sum_range.py b/sum_range.py
index abc1234..def5678 100644
--- a/sum_range.py
+++ b/sum_range.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end))
+    return sum(range(start, end + 1))
"""


def _pack(*task_ids: str, name: str = "py-bugfix") -> BenchmarkPack:
    return BenchmarkPack(
        name=name,
        version="1.0",
        tasks=[TaskSpec(task_id=t, title=f"Task {t}") for t in task_ids],
    )


def _artifact(
    *,
    agent_name: str = "claude-code",
    task_id: str = "t1",
    run_id: str | None = None,
    diff_text: str = "",
    **overrides,
) -> AgentRunArtifact:
    return AgentRunArtifact(
        agent_name=agent_name,
        task_id=task_id,
        run_id=run_id or f"{agent_name}:{task_id}:001",
        diff_text=diff_text,
        **overrides,
    )


# ---- build_run_report_from_agent_artifacts ---------------------------------


def test_one_artifact_produces_run_report():
    pack = _pack("t1")
    report = build_run_report_from_agent_artifacts(
        pack, "claude-code", [_artifact(diff_text=VALID_DIFF)]
    )

    assert isinstance(report, RunReport)
    assert report.pack_name == "py-bugfix"
    assert report.pack_version == "1.0"
    assert report.total_tasks == 1
    assert len(report.results) == 1


def test_run_report_uses_requested_agent_name():
    pack = _pack("t1")
    report = build_run_report_from_agent_artifacts(
        pack, "claude-code", [_artifact()]
    )
    assert report.agent_name == "claude-code"


def test_run_report_covers_every_task_in_pack():
    pack = _pack("t1", "t2", "t3")
    report = build_run_report_from_agent_artifacts(
        pack, "claude-code", [_artifact(task_id="t1")]
    )

    assert report.total_tasks == 3
    assert [r.task_id for r in report.results] == ["t1", "t2", "t3"]


def test_attempted_task_has_patch_summary_when_diff_present():
    pack = _pack("t1")
    report = build_run_report_from_agent_artifacts(
        pack, "claude-code", [_artifact(diff_text=VALID_DIFF)]
    )

    result = report.results[0]
    assert result.patch_summary is not None
    assert result.patch_summary.changed_files == ["sum_range.py"]


def test_attempted_task_without_diff_has_no_patch_summary():
    pack = _pack("t1")
    report = build_run_report_from_agent_artifacts(
        pack, "claude-code", [_artifact()]
    )
    assert report.results[0].patch_summary is None


def test_missing_tasks_are_included_as_unverified_results():
    pack = _pack("t1", "t2")
    report = build_run_report_from_agent_artifacts(
        pack, "claude-code", [_artifact(task_id="t1")]
    )

    by_task = {r.task_id: r for r in report.results}
    assert WeaknessCode.VERIFY in by_task["t2"].weaknesses
    assert by_task["t2"].passed_public_tests is False
    assert by_task["t2"].passed_hidden_tests is False
    assert "no external agent artifact" in by_task["t2"].rationale.lower()


def test_every_result_remains_unverified():
    pack = _pack("t1", "t2", "t3")
    artifacts = [
        _artifact(task_id="t1", diff_text=VALID_DIFF),
        _artifact(task_id="t2", claimed_public_tests_passed=True),
    ]
    report = build_run_report_from_agent_artifacts(pack, "claude-code", artifacts)

    for result in report.results:
        assert result.passed_public_tests is False
        assert result.passed_hidden_tests is False
        assert WeaknessCode.VERIFY in result.weaknesses
        assert result.score == 0.0
    assert report.mean_score == 0.0


def test_weakness_tally_counts_verify_for_all_tasks():
    pack = _pack("t1", "t2", "t3")
    artifacts = [_artifact(task_id="t1"), _artifact(task_id="t2")]
    report = build_run_report_from_agent_artifacts(pack, "claude-code", artifacts)

    assert report.weakness_tally.get("VERIFY") == 3


def test_agent_claims_do_not_make_tests_pass():
    pack = _pack("t1")
    report = build_run_report_from_agent_artifacts(
        pack,
        "claude-code",
        [
            _artifact(
                task_id="t1",
                claimed_public_tests_passed=True,
                claimed_hidden_tests_passed=True,
            )
        ],
    )

    result = report.results[0]
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses


def test_unknown_task_id_raises():
    pack = _pack("t1", "t2")
    with pytest.raises(AgentRunReportingError, match="not in pack"):
        build_run_report_from_agent_artifacts(
            pack, "claude-code", [_artifact(task_id="t99")]
        )


def test_duplicate_artifacts_for_same_task_raise():
    pack = _pack("t1")
    artifacts = [
        _artifact(task_id="t1", run_id="run-a"),
        _artifact(task_id="t1", run_id="run-b"),
    ]
    with pytest.raises(AgentRunReportingError, match="duplicate"):
        build_run_report_from_agent_artifacts(pack, "claude-code", artifacts)


def test_artifacts_for_other_agents_are_ignored():
    pack = _pack("t1", "t2")
    artifacts = [
        _artifact(agent_name="claude-code", task_id="t1"),
        _artifact(agent_name="codex", task_id="t2"),
    ]
    report = build_run_report_from_agent_artifacts(pack, "claude-code", artifacts)

    by_task = {r.task_id: r for r in report.results}
    # t1 attempted by claude-code; t2 unattempted by claude-code.
    assert "no external agent artifact" in by_task["t2"].rationale.lower()
    assert "no external agent artifact" not in by_task["t1"].rationale.lower()


def test_empty_artifacts_yields_all_unverified_report():
    pack = _pack("t1", "t2")
    report = build_run_report_from_agent_artifacts(pack, "claude-code", [])

    assert report.total_tasks == 2
    assert report.weakness_tally.get("VERIFY") == 2
    for result in report.results:
        assert "no external agent artifact" in result.rationale.lower()


def test_empty_agent_name_raises():
    pack = _pack("t1")
    with pytest.raises(AgentRunReportingError, match="agent_name"):
        build_run_report_from_agent_artifacts(pack, "", [_artifact()])
    with pytest.raises(AgentRunReportingError, match="agent_name"):
        build_run_report_from_agent_artifacts(pack, "   ", [_artifact()])


def test_non_list_artifacts_raises():
    pack = _pack("t1")
    with pytest.raises(AgentRunReportingError, match="artifacts must be a list"):
        build_run_report_from_agent_artifacts(
            pack, "claude-code", _artifact()  # type: ignore[arg-type]
        )


def test_non_artifact_in_list_raises():
    pack = _pack("t1")
    with pytest.raises(AgentRunReportingError, match="AgentRunArtifact"):
        build_run_report_from_agent_artifacts(
            pack, "claude-code", [{"agent_name": "x"}]  # type: ignore[list-item]
        )


def test_pack_task_order_is_preserved():
    pack = _pack("t-z", "t-a", "t-m")
    artifacts = [
        _artifact(task_id="t-a"),
        _artifact(task_id="t-m"),
        _artifact(task_id="t-z"),
    ]
    report = build_run_report_from_agent_artifacts(pack, "claude-code", artifacts)
    assert [r.task_id for r in report.results] == ["t-z", "t-a", "t-m"]


def test_does_not_mutate_inputs():
    pack = _pack("t1", "t2")
    pack_tasks_snapshot = [t.task_id for t in pack.tasks]
    artifacts = [
        _artifact(task_id="t1", diff_text=VALID_DIFF, metadata={"k": "v"})
    ]
    metadata_snapshot = dict(artifacts[0].metadata)
    artifacts_snapshot = list(artifacts)

    build_run_report_from_agent_artifacts(pack, "claude-code", artifacts)

    assert [t.task_id for t in pack.tasks] == pack_tasks_snapshot
    assert artifacts == artifacts_snapshot
    assert artifacts[0].metadata == metadata_snapshot


# ---- build_run_reports_from_agent_artifacts --------------------------------


def test_batch_builds_one_report_per_agent():
    pack = _pack("t1", "t2")
    artifacts = [
        _artifact(agent_name="claude-code", task_id="t1"),
        _artifact(agent_name="codex", task_id="t1"),
        _artifact(agent_name="codex", task_id="t2"),
    ]

    reports = build_run_reports_from_agent_artifacts(pack, artifacts)

    assert len(reports) == 2
    by_agent = {r.agent_name: r for r in reports}
    assert set(by_agent) == {"claude-code", "codex"}
    # Each report still covers every task in the pack.
    assert by_agent["claude-code"].total_tasks == 2
    assert by_agent["codex"].total_tasks == 2


def test_batch_uses_deterministic_agent_ordering():
    pack = _pack("t1")
    artifacts = [
        _artifact(agent_name="zeta-agent", task_id="t1"),
        _artifact(agent_name="alpha-agent", task_id="t1"),
        _artifact(agent_name="mu-agent", task_id="t1"),
    ]

    reports = build_run_reports_from_agent_artifacts(pack, artifacts)

    assert [r.agent_name for r in reports] == [
        "alpha-agent",
        "mu-agent",
        "zeta-agent",
    ]


def test_batch_empty_artifacts_returns_empty_list():
    assert build_run_reports_from_agent_artifacts(_pack("t1"), []) == []


def test_batch_propagates_reporting_errors():
    pack = _pack("t1")
    artifacts = [
        _artifact(agent_name="codex", task_id="t1", run_id="r1"),
        _artifact(agent_name="codex", task_id="t1", run_id="r2"),
    ]
    with pytest.raises(AgentRunReportingError, match="duplicate"):
        build_run_reports_from_agent_artifacts(pack, artifacts)


# ---- build_run_reports_from_agent_artifact_dir -----------------------------


def test_dir_helper_loads_and_builds_reports(tmp_path: Path):
    pack = _pack("t1", "t2")
    save_agent_run_artifact_folder(
        _artifact(agent_name="claude-code", task_id="t1", diff_text=VALID_DIFF),
        tmp_path / "claude-code" / "t1",
    )
    save_agent_run_artifact_folder(
        _artifact(agent_name="codex", task_id="t1"),
        tmp_path / "codex" / "t1",
    )

    reports = build_run_reports_from_agent_artifact_dir(pack, tmp_path)

    assert [r.agent_name for r in reports] == ["claude-code", "codex"]
    for report in reports:
        assert report.total_tasks == 2
        for result in report.results:
            assert WeaknessCode.VERIFY in result.weaknesses
            assert result.passed_public_tests is False
            assert result.passed_hidden_tests is False


def test_dir_helper_empty_dir_returns_empty_list(tmp_path: Path):
    assert build_run_reports_from_agent_artifact_dir(_pack("t1"), tmp_path) == []
