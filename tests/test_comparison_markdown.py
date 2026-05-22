"""Tests for the cross-agent comparison Markdown renderer."""

from agenteval.comparison.comparison_report import build_comparison_report
from agenteval.comparison.markdown import (
    render_comparison_report_markdown,
    save_comparison_report_markdown,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    ComparisonReport,
    RunReport,
    TaskSpec,
)
from agenteval.evaluation.pack_report import evaluate_pack_to_report


def _run_report(
    agent_name: str,
    mean_score: float = 0.5,
    weakness_tally: dict[str, int] | None = None,
    *,
    total_tasks: int = 3,
) -> RunReport:
    return RunReport(
        pack_name="demo_pack",
        pack_version="1.0",
        agent_name=agent_name,
        total_tasks=total_tasks,
        mean_score=mean_score,
        weakness_tally=dict(weakness_tally or {}),
    )


def _comparison(reports: list[RunReport]) -> ComparisonReport:
    return build_comparison_report(reports)


def test_markdown_includes_header_metadata():
    md = render_comparison_report_markdown(
        _comparison([_run_report("agent_a", 0.5)])
    )
    assert "Cross-Agent Comparison" in md
    assert "demo_pack" in md
    assert "1.0" in md
    assert "Total tasks" in md
    assert "Agents compared" in md


def test_markdown_includes_ranking_table():
    md = render_comparison_report_markdown(
        _comparison([_run_report("agent_a", 0.5)])
    )
    assert "## Ranking" in md
    assert "| Rank | Agent | Mean score |" in md


def test_ranking_follows_comparison_ranking_order():
    comparison = _comparison(
        [
            _run_report("agent_low", 0.1),
            _run_report("agent_high", 0.9),
            _run_report("agent_mid", 0.5),
        ]
    )
    md = render_comparison_report_markdown(comparison)
    assert comparison.ranking == ["agent_high", "agent_mid", "agent_low"]
    assert "| 1 | agent_high |" in md
    assert "| 2 | agent_mid |" in md
    assert "| 3 | agent_low |" in md


def test_mean_scores_are_shown():
    md = render_comparison_report_markdown(
        _comparison([_run_report("agent_a", 0.75)])
    )
    assert "0.7500" in md


def test_weakness_tally_by_agent_is_shown():
    md = render_comparison_report_markdown(
        _comparison([_run_report("agent_a", weakness_tally={"VERIFY": 2})])
    )
    assert "Weakness tally by agent" in md
    assert "### agent_a" in md
    assert "VERIFY" in md


def test_weakness_keys_are_sorted_alphabetically():
    comparison = _comparison(
        [
            _run_report(
                "agent_a",
                weakness_tally={"VERIFY": 1, "INST": 1, "LAZY": 1},
            )
        ]
    )
    md = render_comparison_report_markdown(comparison)
    assert md.index("INST") < md.index("LAZY") < md.index("VERIFY")


def test_agent_with_no_weaknesses_handled_gracefully():
    md = render_comparison_report_markdown(
        _comparison([_run_report("clean_agent", 1.0, weakness_tally={})])
    )
    assert "### clean_agent" in md
    assert "No weaknesses recorded" in md


def test_notes_section_is_included():
    md = render_comparison_report_markdown(
        _comparison([_run_report("agent_a", 0.5)])
    )
    assert "## Notes" in md
    assert "same benchmark" in md


def test_output_is_deterministic():
    comparison = _comparison(
        [
            _run_report("agent_b", 0.5, {"INST": 1}),
            _run_report("agent_a", 0.5, {"LAZY": 2}),
        ]
    )
    assert render_comparison_report_markdown(
        comparison
    ) == render_comparison_report_markdown(comparison)


def test_save_writes_utf8_file_and_creates_parent_dirs(tmp_path):
    comparison = _comparison([_run_report("agent_a", 0.5, {"INST": 1})])
    # A nested path also exercises parent-directory creation.
    path = tmp_path / "nested" / "comparison.md"
    save_comparison_report_markdown(comparison, path)
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# ")
    assert "Cross-Agent Comparison" in content


def test_comparison_from_simulated_agents_renders():
    # Agent-agnostic: arbitrary simulated names, not framework values.
    reports = [
        _run_report("claude_code_simulated", 0.90, {"VERIFY": 1}),
        _run_report("codex_simulated", 0.80, {"INST": 2}),
        _run_report("forgeagent_simulated", 0.70, {}),
        _run_report("dgm_original_simulated", 0.60, {"LAZY": 1}),
        _run_report("dgm_modified_simulated", 0.65, {"LAZY": 1, "OVERENG": 1}),
        _run_report("deepseek_simulated", 0.55, {}),
        _run_report("grok_simulated", 0.50, {"TOOL": 1}),
    ]
    comparison = _comparison(reports)
    md = render_comparison_report_markdown(comparison)
    assert "Agents compared:** 7" in md
    for report in reports:
        assert report.agent_name in md
    assert "| 1 | claude_code_simulated |" in md


def test_week2_and_week3_day1_pipelines_still_work():
    pack = BenchmarkPack(
        name="demo",
        version="1.0",
        tasks=[TaskSpec(task_id="t1", title="A task")],
    )
    report = evaluate_pack_to_report(pack, "agent_simulated", {})
    comparison = build_comparison_report([report])
    assert isinstance(comparison, ComparisonReport)
    assert comparison.agents == ["agent_simulated"]
