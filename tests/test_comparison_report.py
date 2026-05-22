"""Tests for the cross-agent comparison report aggregator."""

import pytest

from agenteval.comparison.comparison_report import (
    ComparisonReportError,
    build_comparison_report,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    ComparisonReport,
    RunReport,
    TaskSpec,
)
from agenteval.evaluation.pack_report import evaluate_pack_to_report


def _report(
    agent_name: str,
    mean_score: float = 0.5,
    *,
    pack_name: str = "demo_pack",
    pack_version: str = "1.0",
    total_tasks: int = 3,
    weakness_tally: dict[str, int] | None = None,
) -> RunReport:
    return RunReport(
        pack_name=pack_name,
        pack_version=pack_version,
        agent_name=agent_name,
        total_tasks=total_tasks,
        mean_score=mean_score,
        weakness_tally=dict(weakness_tally or {}),
    )


def test_empty_reports_raises_error():
    with pytest.raises(ComparisonReportError):
        build_comparison_report([])


def test_different_pack_name_raises_error():
    reports = [
        _report("a", pack_name="pack_one"),
        _report("b", pack_name="pack_two"),
    ]
    with pytest.raises(ComparisonReportError) as exc_info:
        build_comparison_report(reports)
    assert "pack_name" in str(exc_info.value)


def test_different_pack_version_raises_error():
    reports = [
        _report("a", pack_version="1.0"),
        _report("b", pack_version="2.0"),
    ]
    with pytest.raises(ComparisonReportError) as exc_info:
        build_comparison_report(reports)
    assert "pack_version" in str(exc_info.value)


def test_different_total_tasks_raises_error():
    reports = [
        _report("a", total_tasks=3),
        _report("b", total_tasks=5),
    ]
    with pytest.raises(ComparisonReportError) as exc_info:
        build_comparison_report(reports)
    assert "total_tasks" in str(exc_info.value)


def test_duplicate_agent_name_raises_error():
    reports = [_report("same_agent"), _report("same_agent")]
    with pytest.raises(ComparisonReportError) as exc_info:
        build_comparison_report(reports)
    assert "same_agent" in str(exc_info.value)


def test_agents_preserve_input_order():
    reports = [
        _report("zeta", 0.1),
        _report("alpha", 0.2),
        _report("mike", 0.3),
    ]
    comparison = build_comparison_report(reports)
    assert isinstance(comparison, ComparisonReport)
    assert comparison.agents == ["zeta", "alpha", "mike"]


def test_mean_scores_by_agent_is_correct():
    reports = [_report("a", 0.25), _report("b", 0.75)]
    comparison = build_comparison_report(reports)
    assert comparison.mean_scores_by_agent == {"a": 0.25, "b": 0.75}


def test_ranking_sorts_by_mean_score_descending():
    reports = [_report("low", 0.1), _report("high", 0.9), _report("mid", 0.5)]
    comparison = build_comparison_report(reports)
    assert comparison.ranking == ["high", "mid", "low"]


def test_ranking_tie_breaks_alphabetically():
    reports = [
        _report("charlie", 0.5),
        _report("alpha", 0.5),
        _report("bravo", 0.5),
    ]
    comparison = build_comparison_report(reports)
    assert comparison.ranking == ["alpha", "bravo", "charlie"]


def test_weakness_tally_by_agent_is_correct():
    reports = [
        _report("a", weakness_tally={"VERIFY": 2}),
        _report("b", weakness_tally={"INST": 1, "LAZY": 3}),
    ]
    comparison = build_comparison_report(reports)
    assert comparison.weakness_tally_by_agent == {
        "a": {"VERIFY": 2},
        "b": {"INST": 1, "LAZY": 3},
    }


def test_reports_preserve_input_order():
    r1 = _report("first", 0.1)
    r2 = _report("second", 0.9)
    comparison = build_comparison_report([r1, r2])
    assert comparison.reports == [r1, r2]
    assert comparison.reports[0] is r1
    assert comparison.reports[1] is r2


def test_does_not_mutate_input_reports():
    original = _report("a", weakness_tally={"VERIFY": 1})
    comparison = build_comparison_report([original])
    # Mutating the comparison must not reach back into the input report.
    comparison.weakness_tally_by_agent["a"]["VERIFY"] = 99
    assert original.weakness_tally == {"VERIFY": 1}


def test_comparison_from_many_simulated_agents():
    # Agent-agnostic: these names are arbitrary test data, not framework values.
    agent_scores = {
        "claude_code_simulated": 0.90,
        "codex_simulated": 0.80,
        "forgeagent_simulated": 0.70,
        "dgm_original_simulated": 0.60,
        "dgm_modified_simulated": 0.65,
        "deepseek_simulated": 0.55,
        "grok_simulated": 0.50,
    }
    reports = [_report(name, score) for name, score in agent_scores.items()]
    comparison = build_comparison_report(reports)
    assert len(comparison.agents) == 7
    assert set(comparison.mean_scores_by_agent) == set(agent_scores)
    assert comparison.ranking[0] == "claude_code_simulated"
    assert comparison.ranking[-1] == "grok_simulated"


def test_week2_pack_report_pipeline_still_works():
    pack = BenchmarkPack(
        name="demo",
        version="1.0",
        tasks=[TaskSpec(task_id="t1", title="A task")],
    )
    report = evaluate_pack_to_report(pack, "agent_simulated", {})
    assert report.total_tasks == 1
    assert report.agent_name == "agent_simulated"
