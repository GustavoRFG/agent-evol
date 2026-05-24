"""Tests for per-agent claim analysis rollups."""

import pytest

from agenteval.agent_runs import (
    AgentClaimRollup,
    AgentRunArtifact,
    ClaimAnalysisReport,
    ClaimReportError,
    build_claim_analysis_report,
    build_claim_analysis_report_from_artifacts_and_results,
    build_claim_verification_summary,
    render_claim_analysis_report_markdown,
)
from agenteval.core.schemas import EvaluationResult


def _artifact(
    *,
    agent_name: str = "claude-code",
    task_id: str = "t1",
    run_id: str = "r1",
    claimed_public: bool | None = None,
    claimed_hidden: bool | None = None,
) -> AgentRunArtifact:
    return AgentRunArtifact(
        agent_name=agent_name,
        task_id=task_id,
        run_id=run_id,
        claimed_public_tests_passed=claimed_public,
        claimed_hidden_tests_passed=claimed_hidden,
    )


def _result(
    *,
    task_id: str = "t1",
    run_id: str = "r1",
    passed_public: bool = True,
    passed_hidden: bool = True,
) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=run_id,
        score=1.0 if passed_public and passed_hidden else 0.0,
        passed_public_tests=passed_public,
        passed_hidden_tests=passed_hidden,
        weaknesses=[],
        rationale="",
    )


def _summary(**kwargs):
    return build_claim_verification_summary(
        _artifact(**{k: v for k, v in kwargs.items() if k in {
            "agent_name", "task_id", "run_id", "claimed_public", "claimed_hidden",
        }}),
        _result(**{k: v for k, v in kwargs.items() if k in {
            "task_id", "run_id", "passed_public", "passed_hidden",
        }}),
    )


# ---- build_claim_analysis_report -------------------------------------------


def test_empty_summaries_yields_empty_report():
    report = build_claim_analysis_report([])
    assert isinstance(report, ClaimAnalysisReport)
    assert report.summaries == []
    assert report.rollups_by_agent == {}
    assert report.total_summaries == 0
    assert report.total_mismatches == 0
    assert report.total_overclaims == 0
    assert report.total_underclaims == 0


def test_one_agent_with_no_claims_is_counted():
    report = build_claim_analysis_report([
        _summary(agent_name="claude-code", task_id="t1", run_id="r1"),
        _summary(agent_name="claude-code", task_id="t2", run_id="r2"),
    ])
    rollup = report.rollups_by_agent["claude-code"]
    assert rollup.total_results == 2
    assert rollup.results_with_any_claim == 0
    assert rollup.results_with_no_claim == 2
    assert rollup.matching_claims == 0
    assert rollup.mismatching_claims == 0
    assert rollup.mismatch_run_ids == []
    assert report.total_mismatches == 0


def test_matching_public_and_hidden_claims_are_counted():
    report = build_claim_analysis_report([
        _summary(
            agent_name="claude-code",
            run_id="r1",
            claimed_public=True,
            claimed_hidden=True,
            passed_public=True,
            passed_hidden=True,
        ),
    ])
    rollup = report.rollups_by_agent["claude-code"]
    assert rollup.results_with_any_claim == 1
    assert rollup.matching_claims == 2  # public + hidden each match
    assert rollup.mismatching_claims == 0
    assert rollup.public_mismatches == 0
    assert rollup.hidden_mismatches == 0


def test_public_overclaim_is_counted():
    report = build_claim_analysis_report([
        _summary(
            run_id="r1",
            claimed_public=True,
            passed_public=False,
            passed_hidden=True,
        ),
    ])
    rollup = next(iter(report.rollups_by_agent.values()))
    assert rollup.public_mismatches == 1
    assert rollup.hidden_mismatches == 0
    assert rollup.overclaims == 1
    assert rollup.underclaims == 0
    assert rollup.mismatching_claims == 1
    assert report.total_overclaims == 1
    assert report.total_underclaims == 0
    assert report.total_mismatches == 1


def test_hidden_overclaim_is_counted():
    report = build_claim_analysis_report([
        _summary(
            run_id="r1",
            claimed_hidden=True,
            passed_public=True,
            passed_hidden=False,
        ),
    ])
    rollup = next(iter(report.rollups_by_agent.values()))
    assert rollup.public_mismatches == 0
    assert rollup.hidden_mismatches == 1
    assert rollup.overclaims == 1
    assert rollup.underclaims == 0


def test_public_underclaim_is_counted():
    report = build_claim_analysis_report([
        _summary(
            run_id="r1",
            claimed_public=False,
            passed_public=True,
            passed_hidden=True,
        ),
    ])
    rollup = next(iter(report.rollups_by_agent.values()))
    assert rollup.public_mismatches == 1
    assert rollup.overclaims == 0
    assert rollup.underclaims == 1
    assert report.total_underclaims == 1


def test_hidden_underclaim_is_counted():
    report = build_claim_analysis_report([
        _summary(
            run_id="r1",
            claimed_hidden=False,
            passed_public=True,
            passed_hidden=True,
        ),
    ])
    rollup = next(iter(report.rollups_by_agent.values()))
    assert rollup.hidden_mismatches == 1
    assert rollup.overclaims == 0
    assert rollup.underclaims == 1


def test_dual_bucket_mismatch_counts_buckets_and_overclaims_per_bucket():
    report = build_claim_analysis_report([
        _summary(
            run_id="r1",
            claimed_public=True,
            claimed_hidden=True,
            passed_public=False,
            passed_hidden=False,
        ),
    ])
    rollup = next(iter(report.rollups_by_agent.values()))
    assert rollup.public_mismatches == 1
    assert rollup.hidden_mismatches == 1
    assert rollup.overclaims == 2
    # Both buckets mismatch on a single result -> mismatching_claims = 2.
    assert rollup.mismatching_claims == 2
    # But the result is counted only once in mismatch_run_ids and totals.
    assert rollup.mismatch_run_ids == ["r1"]
    assert report.total_mismatches == 1
    assert report.total_overclaims == 2


def test_mismatch_run_ids_lists_only_runs_with_mismatch():
    report = build_claim_analysis_report([
        _summary(
            agent_name="claude-code", run_id="ok",
            claimed_public=True, passed_public=True, passed_hidden=True,
        ),
        _summary(
            agent_name="claude-code", run_id="bad-public",
            claimed_public=True, passed_public=False, passed_hidden=True,
        ),
        _summary(
            agent_name="claude-code", run_id="bad-hidden",
            claimed_hidden=False, passed_public=True, passed_hidden=True,
        ),
    ])
    rollup = report.rollups_by_agent["claude-code"]
    assert rollup.mismatch_run_ids == ["bad-public", "bad-hidden"]


def test_multiple_agents_are_grouped_separately():
    report = build_claim_analysis_report([
        _summary(
            agent_name="alpha", run_id="r1",
            claimed_public=True, passed_public=True, passed_hidden=True,
        ),
        _summary(
            agent_name="beta", run_id="r2",
            claimed_public=True, passed_public=False, passed_hidden=False,
        ),
        _summary(
            agent_name="alpha", run_id="r3",
            claimed_hidden=True, passed_public=True, passed_hidden=False,
        ),
    ])
    assert set(report.rollups_by_agent) == {"alpha", "beta"}
    alpha = report.rollups_by_agent["alpha"]
    beta = report.rollups_by_agent["beta"]
    assert alpha.total_results == 2
    assert beta.total_results == 1
    assert beta.overclaims == 1
    assert alpha.overclaims == 1  # the hidden=True/false mismatch on r3


def test_rollup_agent_ordering_is_deterministic():
    report = build_claim_analysis_report([
        _summary(agent_name="zeta", run_id="rz"),
        _summary(agent_name="alpha", run_id="ra"),
        _summary(agent_name="mu", run_id="rm"),
    ])
    assert list(report.rollups_by_agent.keys()) == ["alpha", "mu", "zeta"]


def test_summaries_order_is_preserved():
    in_order = [
        _summary(agent_name="zeta", run_id="rz"),
        _summary(agent_name="alpha", run_id="ra"),
        _summary(agent_name="mu", run_id="rm"),
    ]
    report = build_claim_analysis_report(in_order)
    assert [s.run_id for s in report.summaries] == ["rz", "ra", "rm"]


def test_build_does_not_mutate_inputs():
    summaries = [
        _summary(
            agent_name="alpha", run_id="r1",
            claimed_public=True, passed_public=False, passed_hidden=False,
        ),
    ]
    snapshot = [
        (s.agent_name, s.run_id, list(s.mismatch_labels)) for s in summaries
    ]
    build_claim_analysis_report(summaries)
    after = [
        (s.agent_name, s.run_id, list(s.mismatch_labels)) for s in summaries
    ]
    assert snapshot == after


def test_non_list_input_raises():
    with pytest.raises(ClaimReportError, match="summaries"):
        build_claim_analysis_report({})  # type: ignore[arg-type]


def test_non_summary_entry_raises():
    with pytest.raises(ClaimReportError, match="ClaimVerificationSummary"):
        build_claim_analysis_report(["not a summary"])  # type: ignore[list-item]


# ---- build_claim_analysis_report_from_artifacts_and_results ----------------


def test_build_from_artifacts_and_results_pairs_by_run_id():
    artifacts = [
        _artifact(
            agent_name="alpha", task_id="t1", run_id="r1",
            claimed_public=True,
        ),
        _artifact(
            agent_name="beta", task_id="t2", run_id="r2",
            claimed_hidden=True,
        ),
    ]
    results = [
        _result(task_id="t1", run_id="r1", passed_public=True, passed_hidden=True),
        _result(task_id="t2", run_id="r2", passed_public=True, passed_hidden=False),
    ]
    report = build_claim_analysis_report_from_artifacts_and_results(
        artifacts, results
    )
    assert set(report.rollups_by_agent) == {"alpha", "beta"}
    alpha = report.rollups_by_agent["alpha"]
    beta = report.rollups_by_agent["beta"]
    assert alpha.matching_claims == 1
    assert beta.mismatching_claims == 1
    assert beta.overclaims == 1


def test_duplicate_run_id_artifacts_raise():
    artifacts = [
        _artifact(agent_name="alpha", run_id="r-dup"),
        _artifact(agent_name="beta", run_id="r-dup"),
    ]
    results = [_result(run_id="r-dup")]
    with pytest.raises(ClaimReportError, match="duplicate run_id"):
        build_claim_analysis_report_from_artifacts_and_results(
            artifacts, results
        )


def test_non_list_artifacts_raises():
    with pytest.raises(ClaimReportError, match="artifacts"):
        build_claim_analysis_report_from_artifacts_and_results(
            _artifact(),  # type: ignore[arg-type]
            [_result()],
        )


def test_non_list_results_raises():
    with pytest.raises(ClaimReportError, match="results"):
        build_claim_analysis_report_from_artifacts_and_results(
            [_artifact()],
            _result(),  # type: ignore[arg-type]
        )


def test_non_artifact_entry_raises():
    with pytest.raises(ClaimReportError, match="AgentRunArtifact"):
        build_claim_analysis_report_from_artifacts_and_results(
            ["not an artifact"],  # type: ignore[list-item]
            [_result()],
        )


def test_missing_artifact_for_result_raises():
    artifacts = [_artifact(run_id="r1")]
    results = [_result(run_id="r1"), _result(run_id="r-missing")]
    # The inner build_claim_verification_summaries raises, which we wrap.
    with pytest.raises(ClaimReportError, match="r-missing"):
        build_claim_analysis_report_from_artifacts_and_results(
            artifacts, results
        )


# ---- Markdown rendering ----------------------------------------------------


def test_markdown_includes_global_totals():
    report = build_claim_analysis_report([
        _summary(
            agent_name="alpha", run_id="r1",
            claimed_public=True, passed_public=False, passed_hidden=True,
        ),
    ])
    md = render_claim_analysis_report_markdown(report)
    assert "# Agent claim analysis report" in md
    assert "## Totals" in md
    assert "Total summaries: 1" in md
    assert "Overclaims (claimed pass, verified fail): 1" in md


def test_markdown_includes_per_agent_table():
    report = build_claim_analysis_report([
        _summary(
            agent_name="alpha", run_id="r1",
            claimed_public=True, passed_public=True, passed_hidden=True,
        ),
        _summary(
            agent_name="beta", run_id="r2",
            claimed_public=True, passed_public=False, passed_hidden=False,
        ),
    ])
    md = render_claim_analysis_report_markdown(report)
    assert "## Per-agent rollup" in md
    assert "| Agent |" in md
    assert "alpha" in md
    assert "beta" in md


def test_markdown_includes_mismatch_details_section():
    report = build_claim_analysis_report([
        _summary(
            agent_name="liar", run_id="r-liar",
            claimed_public=True, passed_public=False, passed_hidden=False,
        ),
        _summary(
            agent_name="honest", run_id="r-honest",
            claimed_public=True, passed_public=True, passed_hidden=True,
        ),
    ])
    md = render_claim_analysis_report_markdown(report)
    assert "## Mismatch details" in md
    assert "liar" in md
    assert "r-liar" in md
    # The honest agent has no mismatches; mismatch section should not list it.
    mismatch_section = md.split("## Mismatch details", 1)[1]
    assert "r-honest" not in mismatch_section


def test_markdown_no_mismatches_message():
    report = build_claim_analysis_report([
        _summary(
            agent_name="honest", run_id="r1",
            claimed_public=True, passed_public=True, passed_hidden=True,
        ),
    ])
    md = render_claim_analysis_report_markdown(report)
    assert "No mismatches recorded" in md


def test_markdown_includes_informational_note():
    md = render_claim_analysis_report_markdown(
        build_claim_analysis_report([])
    )
    assert "does not affect" in md.lower() or "informational" in md.lower()


def test_markdown_empty_report_has_no_agents_note():
    md = render_claim_analysis_report_markdown(
        build_claim_analysis_report([])
    )
    assert "No agents in this report" in md


def test_markdown_rejects_non_report_input():
    with pytest.raises(ClaimReportError, match="ClaimAnalysisReport"):
        render_claim_analysis_report_markdown("not a report")  # type: ignore[arg-type]


# ---- dataclass shape sanity ------------------------------------------------


def test_agent_claim_rollup_defaults():
    rollup = AgentClaimRollup(agent_name="x")
    assert rollup.total_results == 0
    assert rollup.results_with_any_claim == 0
    assert rollup.results_with_no_claim == 0
    assert rollup.matching_claims == 0
    assert rollup.mismatching_claims == 0
    assert rollup.public_mismatches == 0
    assert rollup.hidden_mismatches == 0
    assert rollup.overclaims == 0
    assert rollup.underclaims == 0
    assert rollup.mismatch_run_ids == []
