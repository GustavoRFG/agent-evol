"""Tests for per-task divergence analysis."""

import pytest

from agenteval.comparison.comparison_report import build_comparison_report
from agenteval.comparison.divergence import (
    TaskDivergence,
    build_task_divergence_report,
    top_divergent_tasks,
)
from agenteval.comparison.markdown import render_comparison_report_markdown
from agenteval.core.schemas import EvaluationResult, RunReport


def _result(task_id: str, agent: str, score: float) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id, run_id=f"{agent}:{task_id}", score=score
    )


def _report(agent: str, results: list[EvaluationResult]) -> RunReport:
    return RunReport(
        pack_name="demo_pack",
        pack_version="1.0",
        agent_name=agent,
        total_tasks=len(results),
        mean_score=(
            sum(r.score for r in results) / len(results) if results else 0.0
        ),
        results=results,
    )


def _comparison(reports: list[RunReport]):
    return build_comparison_report(reports)


def test_one_row_per_task():
    reports = [
        _report(
            "agent_a",
            [_result("t1", "agent_a", 0.5), _result("t2", "agent_a", 0.6)],
        ),
        _report(
            "agent_b",
            [_result("t1", "agent_b", 0.9), _result("t2", "agent_b", 0.1)],
        ),
    ]
    divergences = build_task_divergence_report(_comparison(reports))
    assert len(divergences) == 2
    assert all(isinstance(d, TaskDivergence) for d in divergences)
    assert [d.task_id for d in divergences] == ["t1", "t2"]


def test_best_score_is_correct():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.3)]),
        _report("agent_b", [_result("t1", "agent_b", 0.8)]),
        _report("agent_c", [_result("t1", "agent_c", 0.5)]),
    ]
    divergence = build_task_divergence_report(_comparison(reports))[0]
    assert divergence.best_score == 0.8


def test_worst_score_is_correct():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.3)]),
        _report("agent_b", [_result("t1", "agent_b", 0.8)]),
    ]
    divergence = build_task_divergence_report(_comparison(reports))[0]
    assert divergence.worst_score == 0.3


def test_score_spread_is_correct():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.2)]),
        _report("agent_b", [_result("t1", "agent_b", 0.9)]),
    ]
    divergence = build_task_divergence_report(_comparison(reports))[0]
    assert divergence.score_spread == pytest.approx(0.7)


def test_best_agents_supports_ties():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.9)]),
        _report("agent_b", [_result("t1", "agent_b", 0.9)]),
        _report("agent_c", [_result("t1", "agent_c", 0.4)]),
    ]
    divergence = build_task_divergence_report(_comparison(reports))[0]
    assert divergence.best_agents == ["agent_a", "agent_b"]
    assert divergence.best_score == 0.9


def test_worst_agents_supports_ties():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.9)]),
        _report("agent_b", [_result("t1", "agent_b", 0.2)]),
        _report("agent_c", [_result("t1", "agent_c", 0.2)]),
    ]
    divergence = build_task_divergence_report(_comparison(reports))[0]
    assert divergence.worst_agents == ["agent_b", "agent_c"]


def test_agent_order_follows_comparison_agents():
    # Input order zeta, alpha, mike; all tied -> all are best and worst.
    reports = [
        _report("zeta", [_result("t1", "zeta", 0.5)]),
        _report("alpha", [_result("t1", "alpha", 0.5)]),
        _report("mike", [_result("t1", "mike", 0.5)]),
    ]
    comparison = _comparison(reports)
    divergence = build_task_divergence_report(comparison)[0]
    assert comparison.agents == ["zeta", "alpha", "mike"]
    assert divergence.best_agents == ["zeta", "alpha", "mike"]
    assert divergence.worst_agents == ["zeta", "alpha", "mike"]


def test_top_divergent_tasks_sorts_by_spread_descending():
    reports = [
        _report(
            "agent_a",
            [
                _result("low_div", "agent_a", 0.5),
                _result("high_div", "agent_a", 0.0),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("low_div", "agent_b", 0.6),
                _result("high_div", "agent_b", 1.0),
            ],
        ),
    ]
    top = top_divergent_tasks(_comparison(reports))
    assert [d.task_id for d in top] == ["high_div", "low_div"]


def test_top_divergent_tasks_tie_breaks_by_task_id():
    # Both tasks have an identical spread; alphabetical task_id breaks the tie.
    reports = [
        _report(
            "agent_a",
            [
                _result("zebra", "agent_a", 0.0),
                _result("apple", "agent_a", 0.0),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("zebra", "agent_b", 0.5),
                _result("apple", "agent_b", 0.5),
            ],
        ),
    ]
    top = top_divergent_tasks(_comparison(reports))
    assert [d.task_id for d in top] == ["apple", "zebra"]


def test_top_divergent_tasks_respects_limit():
    reports = [
        _report(
            "agent_a",
            [
                _result("t1", "agent_a", 0.0),
                _result("t2", "agent_a", 0.0),
                _result("t3", "agent_a", 0.0),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("t1", "agent_b", 0.9),
                _result("t2", "agent_b", 0.5),
                _result("t3", "agent_b", 0.1),
            ],
        ),
    ]
    comparison = _comparison(reports)
    assert len(top_divergent_tasks(comparison, limit=2)) == 2
    assert len(top_divergent_tasks(comparison, limit=None)) == 3


def test_negative_limit_raises_value_error():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.5)]),
        _report("agent_b", [_result("t1", "agent_b", 0.5)]),
    ]
    with pytest.raises(ValueError):
        top_divergent_tasks(_comparison(reports), limit=-1)


def test_markdown_includes_divergence_section():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.1)]),
        _report("agent_b", [_result("t1", "agent_b", 0.9)]),
    ]
    md = render_comparison_report_markdown(_comparison(reports))
    assert "## Tasks where agents most disagree" in md


def test_markdown_divergence_section_shows_score_spread():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.0)]),
        _report("agent_b", [_result("t1", "agent_b", 1.0)]),
    ]
    md = render_comparison_report_markdown(_comparison(reports))
    assert "Score spread" in md
    assert "1.0000" in md
