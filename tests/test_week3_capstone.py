"""Tests for the Week 3 capstone simulated multi-agent comparison.

These tests exercise the full Week 3 pipeline end-to-end: building simulated
RunReports, building a ComparisonReport, rendering Markdown, persisting to
JSON, and reloading. The capstone is fully simulated — no agent is run.
"""

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.comparison import (
    build_comparison_report,
    build_task_divergence_report,
    build_task_score_matrix,
    compare_all_agent_pairs,
    load_comparison_report,
    render_comparison_report_markdown,
    save_comparison_report,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    ComparisonReport,
    RunReport,
    TaskSpec,
)
from agenteval.evaluation import TaskEvidence, evaluate_pack_to_report
from examples.week3_capstone_simulated_comparison import (
    PACK_DIR,
    build_simulated_week3_capstone_comparison,
    build_simulated_week3_capstone_reports,
    render_simulated_week3_capstone_markdown,
)


# --- RunReports ------------------------------------------------------------


def test_capstone_reports_returns_multiple_run_reports():
    reports = build_simulated_week3_capstone_reports()
    assert all(isinstance(report, RunReport) for report in reports)
    assert len(reports) >= 5


def test_capstone_reports_share_pack_metadata():
    pack = load_benchmark_pack(PACK_DIR)
    reports = build_simulated_week3_capstone_reports()
    for report in reports:
        assert report.pack_name == pack.name
        assert report.pack_version == pack.version


def test_capstone_reports_have_unique_agent_names():
    reports = build_simulated_week3_capstone_reports()
    agent_names = [report.agent_name for report in reports]
    assert len(set(agent_names)) == len(agent_names)


def test_capstone_includes_strong_symptom_unverified_and_diff_profiles():
    reports = {r.agent_name: r for r in build_simulated_week3_capstone_reports()}

    # At least one agent passes both public and hidden tests.
    assert any(
        result.passed_public_tests and result.passed_hidden_tests
        for report in reports.values()
        for result in report.results
    )

    # At least one agent passes public but fails hidden.
    assert any(
        result.passed_public_tests and not result.passed_hidden_tests
        for report in reports.values()
        for result in report.results
    )

    # At least one agent is unverified (VERIFY weakness).
    assert any(
        "VERIFY" in report.weakness_tally
        and report.weakness_tally["VERIFY"] >= 1
        for report in reports.values()
    )

    # At least one agent surfaces patch evidence via diff_text.
    assert any(
        result.patch_summary is not None
        and result.patch_summary.changed_files
        for report in reports.values()
        for result in report.results
    )


# --- ComparisonReport ------------------------------------------------------


def test_capstone_comparison_returns_comparison_report():
    comparison = build_simulated_week3_capstone_comparison()
    assert isinstance(comparison, ComparisonReport)


def test_capstone_comparison_has_at_least_five_agents():
    comparison = build_simulated_week3_capstone_comparison()
    assert len(comparison.agents) >= 5


def test_capstone_ranking_is_non_empty_and_covers_every_agent():
    comparison = build_simulated_week3_capstone_comparison()
    assert comparison.ranking
    assert set(comparison.ranking) == set(comparison.agents)


def test_capstone_comparison_builds_task_score_matrix():
    comparison = build_simulated_week3_capstone_comparison()
    matrix = build_task_score_matrix(comparison)
    assert matrix
    for row in matrix:
        # Every compared agent has a score for every task in the matrix.
        assert set(row.scores_by_agent) == set(comparison.agents)


def test_capstone_comparison_builds_divergence_data():
    comparison = build_simulated_week3_capstone_comparison()
    divergences = build_task_divergence_report(comparison)
    assert divergences
    # Agents in the capstone deliberately disagree, so spread is positive.
    assert any(d.score_spread > 0.0 for d in divergences)


def test_capstone_compare_all_agent_pairs_returns_pairwise_comparisons():
    comparison = build_simulated_week3_capstone_comparison()
    pairs = compare_all_agent_pairs(comparison)
    agent_count = len(comparison.agents)
    expected = agent_count * (agent_count - 1) // 2
    assert len(pairs) == expected
    for pair in pairs:
        assert pair.agent_a in comparison.agents
        assert pair.agent_b in comparison.agents
        assert pair.agent_a != pair.agent_b


# --- Markdown rendering ----------------------------------------------------


def test_capstone_markdown_contains_every_week3_section():
    md = render_simulated_week3_capstone_markdown()
    # Ranking, pairwise summary, per-task score matrix, divergence,
    # weakness tally — each Week 3 milestone surfaces in the document.
    assert "## Ranking" in md
    assert "## Pairwise summary" in md
    assert "## Per-task score matrix" in md
    assert "## Tasks where agents most disagree" in md
    assert "## Weakness tally by agent" in md


def test_capstone_markdown_lists_every_simulated_agent():
    comparison = build_simulated_week3_capstone_comparison()
    md = render_simulated_week3_capstone_markdown()
    for agent in comparison.agents:
        assert agent in md


# --- JSON persistence ------------------------------------------------------


def test_capstone_comparison_round_trips_through_json(tmp_path):
    comparison = build_simulated_week3_capstone_comparison()
    path = tmp_path / "week3_capstone_comparison.json"

    save_comparison_report(comparison, path)
    assert path.is_file()

    loaded = load_comparison_report(path)
    assert isinstance(loaded, ComparisonReport)
    assert loaded.pack_name == comparison.pack_name
    assert loaded.pack_version == comparison.pack_version
    assert loaded.agents == comparison.agents
    assert loaded.ranking == comparison.ranking
    assert loaded.mean_scores_by_agent == comparison.mean_scores_by_agent
    assert loaded.weakness_tally_by_agent == comparison.weakness_tally_by_agent


def test_loaded_capstone_comparison_still_renders_markdown(tmp_path):
    comparison = build_simulated_week3_capstone_comparison()
    path = tmp_path / "week3_capstone_comparison.json"
    save_comparison_report(comparison, path)

    loaded = load_comparison_report(path)
    md = render_comparison_report_markdown(loaded)
    assert "Cross-Agent Comparison" in md
    for agent in loaded.agents:
        assert agent in md


# --- Regression: existing Week 2 and Week 3 pipelines ----------------------


def test_week2_and_week3_pipelines_still_work_unchanged(tmp_path):
    # Week 2: assemble a RunReport from a pack via evaluate_pack_to_report.
    pack = BenchmarkPack(
        name="regression_pack",
        version="1.0",
        tasks=[TaskSpec(task_id="t1", title="A task")],
    )
    report = evaluate_pack_to_report(
        pack,
        "regression_agent_simulated",
        {"t1": TaskEvidence(passed_public_tests=True)},
    )
    assert isinstance(report, RunReport)
    assert report.results[0].passed_public_tests is True

    # Week 3: comparison, divergence, pairwise, persistence, Markdown.
    comparison = build_comparison_report([report])
    assert isinstance(comparison, ComparisonReport)
    assert comparison.agents == ["regression_agent_simulated"]
    assert build_task_score_matrix(comparison)
    assert build_task_divergence_report(comparison)
    assert compare_all_agent_pairs(comparison) == []  # only one agent

    path = tmp_path / "regression_comparison.json"
    save_comparison_report(comparison, path)
    loaded = load_comparison_report(path)
    assert loaded.agents == ["regression_agent_simulated"]
    md = render_comparison_report_markdown(loaded)
    assert "regression_pack" in md
