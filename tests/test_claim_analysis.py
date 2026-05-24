"""Tests for claim-vs-verified outcome analysis."""

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    ClaimAnalysisError,
    ClaimVerificationSummary,
    build_claim_verification_summaries,
    build_claim_verification_summary,
    render_claim_verification_summary_markdown,
)
from agenteval.core.schemas import EvaluationResult, WeaknessCode


def _artifact(
    *,
    agent_name: str = "claude-code",
    task_id: str = "bugfix_005",
    run_id: str = "claude-code:bugfix_005:001",
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
    task_id: str = "bugfix_005",
    run_id: str = "claude-code:bugfix_005:001",
    passed_public: bool = True,
    passed_hidden: bool = True,
    weaknesses: list[WeaknessCode] | None = None,
    score: float = 1.0,
) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=run_id,
        score=score,
        passed_public_tests=passed_public,
        passed_hidden_tests=passed_hidden,
        weaknesses=list(weaknesses) if weaknesses is not None else [],
        rationale="",
    )


# ---- single-summary semantics ----------------------------------------------


def test_no_claims_yields_no_mismatch_and_no_claim_flag():
    summary = build_claim_verification_summary(_artifact(), _result())

    assert isinstance(summary, ClaimVerificationSummary)
    assert summary.has_any_claim is False
    assert summary.has_mismatch is False
    assert summary.mismatch_labels == []
    assert summary.public_claim_matches is None
    assert summary.hidden_claim_matches is None
    assert "no claims" in summary.rationale.lower()


def test_matching_public_claim_marks_match():
    summary = build_claim_verification_summary(
        _artifact(claimed_public=True),
        _result(passed_public=True),
    )
    assert summary.public_claim_matches is True
    assert summary.has_any_claim is True
    assert summary.has_mismatch is False
    assert "match" in summary.rationale.lower()


def test_mismatching_public_claim_marks_mismatch():
    summary = build_claim_verification_summary(
        _artifact(claimed_public=True),
        _result(passed_public=False, passed_hidden=False),
    )
    assert summary.public_claim_matches is False
    assert summary.has_mismatch is True
    assert "public" in summary.mismatch_labels
    assert "public claim differs" in summary.rationale


def test_matching_hidden_claim_marks_match():
    summary = build_claim_verification_summary(
        _artifact(claimed_hidden=False),
        _result(passed_public=True, passed_hidden=False),
    )
    assert summary.hidden_claim_matches is True
    assert summary.has_any_claim is True
    assert summary.has_mismatch is False


def test_mismatching_hidden_claim_marks_mismatch():
    summary = build_claim_verification_summary(
        _artifact(claimed_hidden=True),
        _result(passed_public=True, passed_hidden=False),
    )
    assert summary.hidden_claim_matches is False
    assert summary.has_mismatch is True
    assert "hidden" in summary.mismatch_labels


def test_both_buckets_mismatch_produces_both_labels():
    summary = build_claim_verification_summary(
        _artifact(claimed_public=True, claimed_hidden=True),
        _result(passed_public=False, passed_hidden=False),
    )
    assert summary.has_mismatch is True
    assert summary.mismatch_labels == ["public", "hidden"]
    assert summary.public_claim_matches is False
    assert summary.hidden_claim_matches is False


def test_partial_claim_only_compares_the_supplied_bucket():
    summary = build_claim_verification_summary(
        _artifact(claimed_public=True),
        _result(passed_public=True, passed_hidden=False),
    )
    # No hidden claim -> hidden_claim_matches is None, no mismatch from hidden.
    assert summary.public_claim_matches is True
    assert summary.hidden_claim_matches is None
    assert summary.has_mismatch is False
    assert summary.mismatch_labels == []


def test_claim_true_does_not_override_verified_false():
    summary = build_claim_verification_summary(
        _artifact(claimed_public=True, claimed_hidden=True),
        _result(passed_public=False, passed_hidden=False),
    )
    # Verified outcomes remain authoritative.
    assert summary.verified_public_tests_passed is False
    assert summary.verified_hidden_tests_passed is False
    # And the mismatch is recorded so callers can surface false success.
    assert summary.has_mismatch is True
    assert summary.mismatch_labels == ["public", "hidden"]


def test_claim_false_does_not_override_verified_true():
    summary = build_claim_verification_summary(
        _artifact(claimed_public=False, claimed_hidden=False),
        _result(passed_public=True, passed_hidden=True),
    )
    assert summary.verified_public_tests_passed is True
    assert summary.verified_hidden_tests_passed is True
    assert summary.has_mismatch is True
    assert summary.mismatch_labels == ["public", "hidden"]


def test_summary_carries_artifact_identity():
    summary = build_claim_verification_summary(
        _artifact(agent_name="codex", task_id="t1", run_id="r1"),
        _result(task_id="t1", run_id="r1"),
    )
    assert summary.agent_name == "codex"
    assert summary.task_id == "t1"
    assert summary.run_id == "r1"


def test_does_not_mutate_inputs():
    artifact = _artifact(claimed_public=True, claimed_hidden=False)
    result = _result(passed_public=False, passed_hidden=True)
    artifact_snapshot = (
        artifact.agent_name,
        artifact.claimed_public_tests_passed,
        artifact.claimed_hidden_tests_passed,
    )
    result_snapshot = (
        result.passed_public_tests,
        result.passed_hidden_tests,
        list(result.weaknesses),
    )

    build_claim_verification_summary(artifact, result)

    assert (
        artifact.agent_name,
        artifact.claimed_public_tests_passed,
        artifact.claimed_hidden_tests_passed,
    ) == artifact_snapshot
    assert (
        result.passed_public_tests,
        result.passed_hidden_tests,
        list(result.weaknesses),
    ) == result_snapshot


# ---- error contract --------------------------------------------------------


def test_task_id_mismatch_raises():
    artifact = _artifact(task_id="t1", run_id="r1")
    result = _result(task_id="t2", run_id="r1")
    with pytest.raises(ClaimAnalysisError, match="task_id mismatch"):
        build_claim_verification_summary(artifact, result)


def test_run_id_mismatch_raises():
    artifact = _artifact(task_id="t1", run_id="r1")
    result = _result(task_id="t1", run_id="r2")
    with pytest.raises(ClaimAnalysisError, match="run_id mismatch"):
        build_claim_verification_summary(artifact, result)


def test_non_artifact_input_raises():
    with pytest.raises(ClaimAnalysisError, match="AgentRunArtifact"):
        build_claim_verification_summary("not an artifact", _result())  # type: ignore[arg-type]


def test_non_result_input_raises():
    with pytest.raises(ClaimAnalysisError, match="EvaluationResult"):
        build_claim_verification_summary(_artifact(), "not a result")  # type: ignore[arg-type]


# ---- batch helper ----------------------------------------------------------


def test_batch_preserves_results_order():
    artifacts = {
        f"r{i}": _artifact(task_id=f"t{i}", run_id=f"r{i}") for i in (1, 2, 3)
    }
    results = [
        _result(task_id="t3", run_id="r3"),
        _result(task_id="t1", run_id="r1"),
        _result(task_id="t2", run_id="r2"),
    ]
    summaries = build_claim_verification_summaries(artifacts, results)
    assert [s.run_id for s in summaries] == ["r3", "r1", "r2"]
    assert [s.task_id for s in summaries] == ["t3", "t1", "t2"]


def test_batch_missing_artifact_raises_with_context():
    artifacts = {"r1": _artifact(task_id="t1", run_id="r1")}
    results = [
        _result(task_id="t1", run_id="r1"),
        _result(task_id="t2", run_id="r-missing"),
    ]
    with pytest.raises(ClaimAnalysisError, match="r-missing"):
        build_claim_verification_summaries(artifacts, results)


def test_batch_rejects_non_dict_artifacts():
    with pytest.raises(ClaimAnalysisError, match="artifacts_by_run_id"):
        build_claim_verification_summaries([], [])  # type: ignore[arg-type]


def test_batch_rejects_non_list_results():
    with pytest.raises(ClaimAnalysisError, match="results must be a list"):
        build_claim_verification_summaries({}, _result())  # type: ignore[arg-type]


def test_batch_rejects_non_result_entry():
    artifacts = {"r1": _artifact(run_id="r1")}
    with pytest.raises(ClaimAnalysisError, match="EvaluationResult"):
        build_claim_verification_summaries(
            artifacts, [_result(run_id="r1"), "not a result"]  # type: ignore[list-item]
        )


def test_batch_empty_returns_empty_list():
    assert build_claim_verification_summaries({}, []) == []


# ---- Markdown helper -------------------------------------------------------


def test_markdown_helper_includes_mismatch_information():
    summaries = [
        build_claim_verification_summary(
            _artifact(
                agent_name="liar",
                task_id="t1",
                run_id="r1",
                claimed_public=True,
                claimed_hidden=True,
            ),
            _result(task_id="t1", run_id="r1", passed_public=False, passed_hidden=False),
        ),
        build_claim_verification_summary(
            _artifact(
                agent_name="honest",
                task_id="t2",
                run_id="r2",
                claimed_public=True,
            ),
            _result(task_id="t2", run_id="r2", passed_public=True, passed_hidden=True),
        ),
    ]
    md = render_claim_verification_summary_markdown(summaries)
    assert "# Agent claims vs verified outcomes" in md
    assert "## Mismatches" in md
    # The liar's mismatch row should appear.
    assert "liar" in md
    assert "t1" in md
    assert "MISMATCH" in md
    # The honest agent has no mismatch; it appears in the table but not in the
    # mismatch section.
    assert "honest" in md


def test_markdown_helper_no_mismatch_section_text():
    summaries = [
        build_claim_verification_summary(
            _artifact(
                agent_name="honest",
                task_id="t1",
                run_id="r1",
                claimed_public=True,
                claimed_hidden=True,
            ),
            _result(task_id="t1", run_id="r1", passed_public=True, passed_hidden=True),
        ),
    ]
    md = render_claim_verification_summary_markdown(summaries)
    assert "No mismatches" in md


def test_markdown_helper_empty_input():
    md = render_claim_verification_summary_markdown([])
    assert "# Agent claims vs verified outcomes" in md
    assert "No summaries" in md


def test_markdown_helper_rejects_non_list():
    with pytest.raises(ClaimAnalysisError, match="summaries"):
        render_claim_verification_summary_markdown(
            build_claim_verification_summary(  # type: ignore[arg-type]
                _artifact(), _result()
            )
        )
