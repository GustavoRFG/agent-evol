"""Tests for pairwise (head-to-head) agent comparison."""

import copy

import pytest

from agenteval.comparison.comparison_report import build_comparison_report
from agenteval.comparison.markdown import render_comparison_report_markdown
from agenteval.comparison.pairwise import (
    PairwiseComparison,
    PairwiseComparisonError,
    compare_agents_pairwise,
    compare_all_agent_pairs,
)
from agenteval.core.schemas import EvaluationResult, RunReport


def _result(task_id: str, agent: str, score: float) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id, run_id=f"{agent}:{task_id}", score=score
    )


def _report(
    agent: str,
    mean_score: float = 0.5,
    weakness_tally: dict[str, int] | None = None,
    results: list[EvaluationResult] | None = None,
) -> RunReport:
    return RunReport(
        pack_name="demo_pack",
        pack_version="1.0",
        agent_name=agent,
        total_tasks=len(results) if results else 0,
        mean_score=mean_score,
        weakness_tally=dict(weakness_tally or {}),
        results=list(results or []),
    )


def _comparison(reports: list[RunReport]):
    return build_comparison_report(reports)


def test_comparing_known_agents_returns_pairwise_comparison():
    comparison = _comparison(
        [_report("agent_a", 0.7), _report("agent_b", 0.4)]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert isinstance(pair, PairwiseComparison)
    assert pair.agent_a == "agent_a"
    assert pair.agent_b == "agent_b"
    assert pair.rationale  # a non-empty explanation is always produced


def test_missing_agent_raises_pairwise_comparison_error():
    comparison = _comparison(
        [_report("agent_a", 0.7), _report("agent_b", 0.4)]
    )
    with pytest.raises(PairwiseComparisonError):
        compare_agents_pairwise(comparison, "agent_a", "ghost")
    with pytest.raises(PairwiseComparisonError):
        compare_agents_pairwise(comparison, "ghost", "agent_b")


def test_comparing_same_agent_raises_pairwise_comparison_error():
    comparison = _comparison(
        [_report("agent_a", 0.7), _report("agent_b", 0.4)]
    )
    with pytest.raises(PairwiseComparisonError):
        compare_agents_pairwise(comparison, "agent_a", "agent_a")


def test_winner_is_agent_a_when_agent_a_scores_higher():
    comparison = _comparison(
        [_report("agent_a", 0.8), _report("agent_b", 0.3)]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert pair.winner == "agent_a"


def test_winner_is_agent_b_when_agent_b_scores_higher():
    comparison = _comparison(
        [_report("agent_a", 0.2), _report("agent_b", 0.9)]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert pair.winner == "agent_b"


def test_winner_is_tie_when_scores_match():
    comparison = _comparison(
        [_report("agent_a", 0.5), _report("agent_b", 0.5)]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert pair.winner == "tie"
    assert pair.score_delta == pytest.approx(0.0)


def test_score_delta_is_mean_score_a_minus_mean_score_b():
    comparison = _comparison(
        [_report("agent_a", 0.75), _report("agent_b", 0.25)]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert pair.mean_score_a == pytest.approx(0.75)
    assert pair.mean_score_b == pytest.approx(0.25)
    assert pair.score_delta == pytest.approx(0.5)


def test_weakness_delta_includes_all_keys_from_both_agents():
    comparison = _comparison(
        [
            _report("agent_a", 0.6, weakness_tally={"INST": 3, "LAZY": 1}),
            _report("agent_b", 0.4, weakness_tally={"LAZY": 2, "VERIFY": 4}),
        ]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert set(pair.weakness_delta) == {"INST", "LAZY", "VERIFY"}
    # Delta is agent_a count minus agent_b count, missing keys treated as 0.
    assert pair.weakness_delta["INST"] == 3
    assert pair.weakness_delta["LAZY"] == -1
    assert pair.weakness_delta["VERIFY"] == -4
    assert pair.weaknesses_a == {"INST": 3, "LAZY": 1}
    assert pair.weaknesses_b == {"LAZY": 2, "VERIFY": 4}


def test_task_score_delta_by_task_is_correct():
    comparison = _comparison(
        [
            _report(
                "agent_a",
                0.4,
                results=[
                    _result("t1", "agent_a", 0.6),
                    _result("t2", "agent_a", 0.2),
                ],
            ),
            _report(
                "agent_b",
                0.5,
                results=[
                    _result("t1", "agent_b", 0.1),
                    _result("t2", "agent_b", 0.9),
                ],
            ),
        ]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert set(pair.task_score_delta_by_task) == {"t1", "t2"}
    assert pair.task_score_delta_by_task["t1"] == pytest.approx(0.5)
    assert pair.task_score_delta_by_task["t2"] == pytest.approx(-0.7)


def test_input_comparison_is_not_mutated():
    comparison = _comparison(
        [
            _report("agent_a", 0.7, weakness_tally={"INST": 1}),
            _report("agent_b", 0.4, weakness_tally={"LAZY": 2}),
        ]
    )
    snapshot = copy.deepcopy(comparison)
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")

    # Mutating the result must not leak back into the input comparison.
    pair.weaknesses_a["INJECTED"] = 99
    pair.weakness_delta["INJECTED"] = 99
    pair.task_score_delta_by_task["INJECTED"] = 1.0

    assert comparison == snapshot


def test_compare_all_agent_pairs_returns_deterministic_unique_pairs():
    comparison = _comparison(
        [
            _report("agent_a", 0.9),
            _report("agent_b", 0.5),
            _report("agent_c", 0.1),
        ]
    )
    pairs = compare_all_agent_pairs(comparison)
    assert all(isinstance(p, PairwiseComparison) for p in pairs)
    assert [(p.agent_a, p.agent_b) for p in pairs] == [
        ("agent_a", "agent_b"),
        ("agent_a", "agent_c"),
        ("agent_b", "agent_c"),
    ]
    # Deterministic: a second call yields the identical pair ordering.
    again = compare_all_agent_pairs(comparison)
    assert [(p.agent_a, p.agent_b) for p in again] == [
        (p.agent_a, p.agent_b) for p in pairs
    ]


def test_compare_all_agent_pairs_empty_for_single_agent():
    comparison = _comparison([_report("agent_a", 0.5)])
    assert compare_all_agent_pairs(comparison) == []


def test_rationale_explains_the_winner():
    comparison = _comparison(
        [_report("agent_a", 0.8), _report("agent_b", 0.3)]
    )
    pair = compare_agents_pairwise(comparison, "agent_a", "agent_b")
    assert "agent_a" in pair.rationale
    assert "outperforms" in pair.rationale


def test_markdown_includes_pairwise_summary_section():
    comparison = _comparison(
        [_report("agent_high", 0.9), _report("agent_low", 0.1)]
    )
    md = render_comparison_report_markdown(comparison)
    assert "## Pairwise summary" in md
    assert "| Agent A | Agent B | Winner | Score delta |" in md
    assert "agent_high" in md
    assert "agent_low" in md


def test_markdown_pairwise_summary_handles_single_agent():
    comparison = _comparison([_report("agent_a", 0.5)])
    md = render_comparison_report_markdown(comparison)
    assert "## Pairwise summary" in md
    assert "Need at least two agents" in md


def test_pairwise_is_agent_agnostic_with_simulated_names():
    # Arbitrary simulated agent names, not framework/provider constants.
    comparison = _comparison(
        [
            _report("model_x_simulated", 0.82, weakness_tally={"VERIFY": 1}),
            _report("model_y_simulated", 0.61, weakness_tally={"INST": 2}),
        ]
    )
    pair = compare_agents_pairwise(
        comparison, "model_x_simulated", "model_y_simulated"
    )
    assert pair.winner == "model_x_simulated"
    assert pair.score_delta == pytest.approx(0.21)
