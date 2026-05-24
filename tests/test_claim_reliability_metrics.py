"""Tests for claim-aware reliability metrics on :class:`AgentClaimRollup`."""

from dataclasses import replace

import pytest

from agenteval.agent_runs import (
    AgentClaimRollup,
    AgentRunArtifact,
    build_claim_analysis_report,
    build_claim_verification_summary,
    render_claim_analysis_report_markdown,
    summarize_agent_claim_reliability,
)
from agenteval.agent_runs.claim_report import (
    ClaimReportError,
    format_optional_rate,
)
from agenteval.core.schemas import EvaluationResult


# ---------------------------------------------------------------------------
# Helpers for building summaries / rollups without touching subprocess code.
# ---------------------------------------------------------------------------


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
    summary_keys = {
        "agent_name", "task_id", "run_id", "claimed_public", "claimed_hidden",
    }
    result_keys = {
        "task_id", "run_id", "passed_public", "passed_hidden",
    }
    return build_claim_verification_summary(
        _artifact(**{k: v for k, v in kwargs.items() if k in summary_keys}),
        _result(**{k: v for k, v in kwargs.items() if k in result_keys}),
    )


def _rollup_from_summaries(summaries):
    """Return the single agent's rollup from a list of summaries."""
    report = build_claim_analysis_report(summaries)
    assert len(report.rollups_by_agent) == 1
    return next(iter(report.rollups_by_agent.values()))


# ---- explicit_claims -------------------------------------------------------


def test_explicit_claims_equals_matching_plus_mismatching():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=True, passed_hidden=False,
        ),  # public match, hidden mismatch
        _summary(
            run_id="r2",
            claimed_public=True,
            passed_public=False, passed_hidden=True,
        ),  # public mismatch
    ])
    # public match=1, hidden mismatch=1, public mismatch=1 -> matching=1, mismatching=2.
    assert rollup.matching_claims == 1
    assert rollup.mismatching_claims == 2
    assert rollup.explicit_claims == 3


def test_explicit_claims_zero_when_no_claims():
    rollup = _rollup_from_summaries([_summary(run_id="r1")])
    assert rollup.explicit_claims == 0


# ---- claim_reliability -----------------------------------------------------


def test_reliability_none_when_no_explicit_claims():
    rollup = _rollup_from_summaries([_summary(run_id="r1")])
    assert rollup.claim_reliability is None


def test_reliability_one_when_all_explicit_claims_match():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=True, passed_hidden=True,
        ),
    ])
    assert rollup.claim_reliability == 1.0
    assert rollup.mismatch_rate == 0.0


def test_reliability_zero_when_all_explicit_claims_mismatch():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=False, passed_hidden=False,
        ),
    ])
    assert rollup.claim_reliability == 0.0
    assert rollup.mismatch_rate == 1.0


def test_mismatch_rate_complementary_to_reliability():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=True, passed_hidden=False,
        ),  # public match, hidden mismatch -> 1 match, 1 mismatch
    ])
    assert rollup.claim_reliability == 0.5
    assert rollup.mismatch_rate == 0.5
    assert (
        rollup.claim_reliability + rollup.mismatch_rate == pytest.approx(1.0)
    )


# ---- overclaim / underclaim / no-claim rates -------------------------------


def test_overclaim_rate_is_computed_correctly():
    # 4 explicit claims, 3 of them overclaims, 1 match.
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=False, passed_hidden=False,
        ),  # 2 overclaims
        _summary(
            run_id="r2",
            claimed_public=True, claimed_hidden=True,
            passed_public=False, passed_hidden=True,
        ),  # 1 overclaim, 1 match
    ])
    assert rollup.overclaims == 3
    assert rollup.matching_claims == 1
    assert rollup.explicit_claims == 4
    assert rollup.overclaim_rate == 0.75
    assert rollup.underclaim_rate == 0.0


def test_underclaim_rate_is_computed_correctly():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=False, claimed_hidden=False,
            passed_public=True, passed_hidden=True,
        ),  # 2 underclaims
        _summary(
            run_id="r2",
            claimed_public=False,
            passed_public=False, passed_hidden=True,
        ),  # 1 match (no underclaim)
    ])
    assert rollup.underclaims == 2
    assert rollup.matching_claims == 1
    assert rollup.explicit_claims == 3
    assert rollup.underclaim_rate == pytest.approx(2 / 3)
    assert rollup.overclaim_rate == 0.0


def test_no_claim_rate_is_computed_correctly():
    rollup = _rollup_from_summaries([
        _summary(run_id="r1"),  # no claims
        _summary(run_id="r2", claimed_public=True, passed_public=True),
        _summary(run_id="r3"),  # no claims
        _summary(run_id="r4"),  # no claims
    ])
    assert rollup.total_results == 4
    assert rollup.results_with_no_claim == 3
    assert rollup.no_claim_rate == 0.75


def test_no_claim_rate_none_when_no_results():
    rollup = AgentClaimRollup(agent_name="x")
    assert rollup.no_claim_rate is None


def test_all_rates_none_for_empty_rollup():
    rollup = AgentClaimRollup(agent_name="x")
    assert rollup.claim_reliability is None
    assert rollup.mismatch_rate is None
    assert rollup.overclaim_rate is None
    assert rollup.underclaim_rate is None
    assert rollup.no_claim_rate is None
    assert rollup.explicit_claims == 0


# ---- immutability ----------------------------------------------------------


def test_rates_do_not_mutate_rollup():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True,
            passed_public=False, passed_hidden=True,
        ),
    ])
    snapshot = replace(rollup, mismatch_run_ids=list(rollup.mismatch_run_ids))
    # Touch every property.
    _ = (
        rollup.explicit_claims,
        rollup.claim_reliability,
        rollup.mismatch_rate,
        rollup.overclaim_rate,
        rollup.underclaim_rate,
        rollup.no_claim_rate,
    )
    assert rollup == snapshot


# ---- format_optional_rate --------------------------------------------------


def test_format_optional_rate_none_is_na():
    assert format_optional_rate(None) == "n/a"


def test_format_optional_rate_renders_percentage():
    assert format_optional_rate(0.0) == "0.0%"
    assert format_optional_rate(1.0) == "100.0%"
    assert format_optional_rate(0.5) == "50.0%"
    assert format_optional_rate(0.75) == "75.0%"
    assert format_optional_rate(1 / 3) == "33.3%"


# ---- Markdown rendering ----------------------------------------------------


def test_markdown_includes_reliability_columns():
    report = build_claim_analysis_report([
        _summary(
            agent_name="alpha", run_id="r1",
            claimed_public=True, passed_public=True, passed_hidden=True,
        ),
    ])
    md = render_claim_analysis_report_markdown(report)
    for header in (
        "Reliability",
        "Mismatch rate",
        "Overclaim rate",
        "Underclaim rate",
        "No-claim rate",
    ):
        assert header in md


def test_markdown_renders_na_for_no_explicit_claims():
    report = build_claim_analysis_report([
        _summary(agent_name="silent", run_id="r1"),
    ])
    md = render_claim_analysis_report_markdown(report)
    silent_row = next(
        line for line in md.splitlines() if line.startswith("| silent ")
    )
    # The four claim-based rate cells (reliability, mismatch, over, under)
    # must be n/a. The fifth cell (no-claim rate) is 100.0% (the one result
    # had no claim).
    assert silent_row.count("n/a") == 4
    assert "100.0%" in silent_row


def test_markdown_renders_percentages_for_available_rates():
    report = build_claim_analysis_report([
        _summary(
            agent_name="liar", run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=False, passed_hidden=False,
        ),
    ])
    md = render_claim_analysis_report_markdown(report)
    liar_row = next(
        line for line in md.splitlines() if line.startswith("| liar ")
    )
    # 0/2 reliability, 2/2 mismatch, 2/2 overclaim, 0/2 underclaim.
    assert "0.0%" in liar_row
    assert "100.0%" in liar_row


def test_markdown_separator_row_widths_match():
    report = build_claim_analysis_report([
        _summary(agent_name="alpha", run_id="r1"),
    ])
    md = render_claim_analysis_report_markdown(report)
    header_line = next(
        line for line in md.splitlines() if line.startswith("| Agent |")
    )
    separator_line = next(
        line for line in md.splitlines() if line.startswith("| --- |")
    )
    # Both lines must have the same number of pipe-separated cells.
    assert header_line.count("|") == separator_line.count("|")


# ---- summarize_agent_claim_reliability -------------------------------------


def test_summary_no_explicit_claims():
    rollup = AgentClaimRollup(agent_name="x", total_results=2, results_with_no_claim=2)
    assert summarize_agent_claim_reliability(rollup) == (
        "No explicit claims were made."
    )


def test_summary_all_match():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=True, passed_hidden=True,
        ),
    ])
    msg = summarize_agent_claim_reliability(rollup)
    assert "matched verified outcomes" in msg
    assert "100.0%" in msg


def test_summary_with_mismatches_mentions_overclaims():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True, claimed_hidden=True,
            passed_public=False, passed_hidden=False,
        ),  # 2 overclaims
    ])
    msg = summarize_agent_claim_reliability(rollup)
    assert "mismatched verified outcomes" in msg
    assert "100.0%" in msg
    assert "2 overclaims" in msg


def test_summary_singular_overclaim_grammar():
    rollup = _rollup_from_summaries([
        _summary(
            run_id="r1",
            claimed_public=True,
            passed_public=False, passed_hidden=True,
        ),  # exactly 1 overclaim
    ])
    msg = summarize_agent_claim_reliability(rollup)
    assert "1 overclaim." in msg
    assert "1 overclaims" not in msg


def test_summary_rejects_non_rollup():
    with pytest.raises(ClaimReportError, match="AgentClaimRollup"):
        summarize_agent_claim_reliability("not a rollup")  # type: ignore[arg-type]
