"""Tests for the per-task cross-agent score matrix."""

import pytest

from agenteval.comparison.comparison_report import build_comparison_report
from agenteval.comparison.markdown import render_comparison_report_markdown
from agenteval.comparison.task_matrix import (
    ComparisonMatrixError,
    TaskScoreRow,
    build_task_score_matrix,
)
from agenteval.core.schemas import EvaluationResult, RunReport, WeaknessCode


def _result(
    task_id: str,
    agent: str,
    score: float,
    *,
    public: bool = False,
    hidden: bool = False,
    weaknesses: list[WeaknessCode] | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=f"{agent}:{task_id}",
        score=score,
        passed_public_tests=public,
        passed_hidden_tests=hidden,
        weaknesses=list(weaknesses or []),
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


def test_matrix_has_one_row_per_task():
    reports = [
        _report(
            "agent_a",
            [
                _result("t1", "agent_a", 0.5),
                _result("t2", "agent_a", 0.7),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("t1", "agent_b", 0.9),
                _result("t2", "agent_b", 0.1),
            ],
        ),
    ]
    matrix = build_task_score_matrix(_comparison(reports))
    assert len(matrix) == 2
    assert all(isinstance(row, TaskScoreRow) for row in matrix)


def test_task_order_follows_first_report():
    reports = [
        _report(
            "agent_a",
            [
                _result("third", "agent_a", 0.1),
                _result("first", "agent_a", 0.2),
                _result("second", "agent_a", 0.3),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("third", "agent_b", 0.4),
                _result("first", "agent_b", 0.5),
                _result("second", "agent_b", 0.6),
            ],
        ),
    ]
    matrix = build_task_score_matrix(_comparison(reports))
    assert [row.task_id for row in matrix] == ["third", "first", "second"]


def test_agent_order_follows_comparison_agents():
    reports = [
        _report("zeta", [_result("t1", "zeta", 0.1)]),
        _report("alpha", [_result("t1", "alpha", 0.2)]),
        _report("mike", [_result("t1", "mike", 0.3)]),
    ]
    comparison = _comparison(reports)
    matrix = build_task_score_matrix(comparison)
    assert comparison.agents == ["zeta", "alpha", "mike"]
    assert list(matrix[0].scores_by_agent.keys()) == comparison.agents


def test_scores_by_agent_is_correct():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.25)]),
        _report("agent_b", [_result("t1", "agent_b", 0.75)]),
    ]
    matrix = build_task_score_matrix(_comparison(reports))
    assert matrix[0].scores_by_agent == {"agent_a": 0.25, "agent_b": 0.75}


def test_public_and_hidden_pass_flags_are_correct():
    reports = [
        _report(
            "agent_a",
            [_result("t1", "agent_a", 1.0, public=True, hidden=True)],
        ),
        _report(
            "agent_b",
            [_result("t1", "agent_b", 0.5, public=True, hidden=False)],
        ),
    ]
    row = build_task_score_matrix(_comparison(reports))[0]
    assert row.public_pass_by_agent == {"agent_a": True, "agent_b": True}
    assert row.hidden_pass_by_agent == {"agent_a": True, "agent_b": False}


def test_weaknesses_by_agent_stores_string_codes():
    reports = [
        _report(
            "agent_a",
            [
                _result(
                    "t1",
                    "agent_a",
                    0.0,
                    weaknesses=[WeaknessCode.VERIFY, WeaknessCode.INST],
                )
            ],
        ),
    ]
    row = build_task_score_matrix(_comparison(reports))[0]
    codes = row.weaknesses_by_agent["agent_a"]
    assert codes == ["VERIFY", "INST"]
    assert all(isinstance(code, str) for code in codes)


def test_mismatched_task_ids_raise_error():
    reports = [
        _report(
            "agent_a",
            [
                _result("t1", "agent_a", 0.5),
                _result("t2", "agent_a", 0.5),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("t1", "agent_b", 0.5),
                _result("t9", "agent_b", 0.5),
            ],
        ),
    ]
    with pytest.raises(ComparisonMatrixError) as exc_info:
        build_task_score_matrix(_comparison(reports))
    assert "agent_b" in str(exc_info.value)


def test_mismatched_task_order_raises_error():
    reports = [
        _report(
            "agent_a",
            [
                _result("t1", "agent_a", 0.5),
                _result("t2", "agent_a", 0.5),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("t2", "agent_b", 0.5),
                _result("t1", "agent_b", 0.5),
            ],
        ),
    ]
    with pytest.raises(ComparisonMatrixError):
        build_task_score_matrix(_comparison(reports))


def test_input_reports_are_not_mutated():
    weaknesses = [WeaknessCode.LAZY]
    result = _result("t1", "agent_a", 0.5, weaknesses=weaknesses)
    report = _report("agent_a", [result])
    matrix = build_task_score_matrix(_comparison([report]))
    # Mutating the matrix row must not reach back into the input result.
    matrix[0].weaknesses_by_agent["agent_a"].append("EXTRA")
    assert result.weaknesses == [WeaknessCode.LAZY]
    assert [r.task_id for r in report.results] == ["t1"]


def test_markdown_includes_per_task_score_matrix_section():
    reports = [
        _report("agent_a", [_result("bugfix_001", "agent_a", 0.9)]),
        _report("agent_b", [_result("bugfix_001", "agent_b", 0.4)]),
    ]
    md = render_comparison_report_markdown(_comparison(reports))
    assert "## Per-task score matrix" in md


def test_markdown_matrix_includes_task_ids():
    reports = [
        _report(
            "agent_a",
            [
                _result("bugfix_001", "agent_a", 0.9),
                _result("bugfix_002", "agent_a", 0.3),
            ],
        ),
        _report(
            "agent_b",
            [
                _result("bugfix_001", "agent_b", 0.4),
                _result("bugfix_002", "agent_b", 0.8),
            ],
        ),
    ]
    md = render_comparison_report_markdown(_comparison(reports))
    assert "bugfix_001" in md
    assert "bugfix_002" in md


def test_markdown_matrix_includes_one_column_per_agent():
    reports = [
        _report("agent_a", [_result("t1", "agent_a", 0.5)]),
        _report("agent_b", [_result("t1", "agent_b", 0.6)]),
        _report("agent_c", [_result("t1", "agent_c", 0.7)]),
    ]
    md = render_comparison_report_markdown(_comparison(reports))
    # The matrix header row carries every agent as a column.
    assert "| Task ID | agent_a | agent_b | agent_c |" in md
