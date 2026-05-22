"""Tests for ComparisonReport JSON persistence."""

import json

import pytest

from agenteval.comparison.comparison_report import build_comparison_report
from agenteval.comparison.markdown import render_comparison_report_markdown
from agenteval.comparison.persistence import (
    ComparisonPersistenceError,
    comparison_report_from_dict,
    comparison_report_to_dict,
    load_comparison_report,
    save_comparison_report,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    ComparisonReport,
    EvaluationResult,
    RunReport,
    TaskSpec,
    WeaknessCode,
)
from agenteval.evaluation.pack_report import evaluate_pack_to_report
from agenteval.reports.run_report import build_run_report


def _result(
    task_id: str,
    score: float,
    weaknesses: list[WeaknessCode] | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=f"run:{task_id}",
        score=score,
        weaknesses=list(weaknesses or []),
    )


def _pack() -> BenchmarkPack:
    return BenchmarkPack(name="demo_pack", version="2.0")


def _run_report(
    agent_name: str,
    results: list[EvaluationResult],
) -> RunReport:
    return build_run_report(_pack(), agent_name, results)


def _comparison() -> ComparisonReport:
    """A comparison of three agents with nested results and weaknesses."""
    reports = [
        _run_report(
            "agent_alpha",
            [
                _result("t1", 1.0),
                _result("t2", 0.5, [WeaknessCode.VERIFY]),
                _result("t3", 0.0, [WeaknessCode.INST]),
            ],
        ),
        _run_report(
            "agent_beta",
            [
                _result("t1", 0.5),
                _result("t2", 0.5),
                _result("t3", 0.5, [WeaknessCode.LAZY]),
            ],
        ),
        _run_report(
            "agent_gamma",
            [
                _result("t1", 0.0),
                _result("t2", 1.0),
                _result("t3", 1.0),
            ],
        ),
    ]
    return build_comparison_report(reports)


def test_to_dict_is_json_friendly():
    data = comparison_report_to_dict(_comparison())
    # Must serialize cleanly with the standard json encoder.
    encoded = json.dumps(data)
    assert isinstance(encoded, str)
    assert isinstance(data, dict)


def test_to_dict_includes_pack_metadata():
    data = comparison_report_to_dict(_comparison())
    assert data["pack_name"] == "demo_pack"
    assert data["pack_version"] == "2.0"
    assert data["total_tasks"] == 3


def test_to_dict_includes_agents_ranking_scores_and_tallies():
    comparison = _comparison()
    data = comparison_report_to_dict(comparison)
    assert data["agents"] == ["agent_alpha", "agent_beta", "agent_gamma"]
    assert data["ranking"] == comparison.ranking
    assert data["mean_scores_by_agent"] == comparison.mean_scores_by_agent
    assert (
        data["weakness_tally_by_agent"]
        == comparison.weakness_tally_by_agent
    )
    assert data["weakness_tally_by_agent"]["agent_alpha"] == {
        "VERIFY": 1,
        "INST": 1,
    }


def test_to_dict_includes_nested_reports():
    data = comparison_report_to_dict(_comparison())
    assert len(data["reports"]) == 3
    first = data["reports"][0]
    assert first["agent_name"] == "agent_alpha"
    assert first["pack_name"] == "demo_pack"
    assert len(first["results"]) == 3
    # Nested weakness codes serialize to plain strings.
    assert first["results"][1]["weaknesses"] == ["VERIFY"]


def test_to_dict_does_not_mutate_input():
    comparison = _comparison()
    original_agents = list(comparison.agents)
    original_ranking = list(comparison.ranking)
    data = comparison_report_to_dict(comparison)
    data["agents"].append("intruder")
    data["ranking"].append("intruder")
    data["mean_scores_by_agent"]["intruder"] = 9.9
    assert comparison.agents == original_agents
    assert comparison.ranking == original_ranking
    assert "intruder" not in comparison.mean_scores_by_agent


def test_from_dict_reconstructs_comparison_report():
    comparison = _comparison()
    rebuilt = comparison_report_from_dict(
        comparison_report_to_dict(comparison)
    )
    assert isinstance(rebuilt, ComparisonReport)
    assert rebuilt.pack_name == comparison.pack_name
    assert rebuilt.agents == comparison.agents
    assert rebuilt.ranking == comparison.ranking


def test_round_trip_preserves_all_fields():
    comparison = _comparison()
    rebuilt = comparison_report_from_dict(
        comparison_report_to_dict(comparison)
    )
    assert rebuilt.pack_name == comparison.pack_name
    assert rebuilt.pack_version == comparison.pack_version
    assert rebuilt.agents == comparison.agents
    assert rebuilt.total_tasks == comparison.total_tasks
    assert rebuilt.ranking == comparison.ranking
    assert rebuilt.mean_scores_by_agent == comparison.mean_scores_by_agent
    assert (
        rebuilt.weakness_tally_by_agent
        == comparison.weakness_tally_by_agent
    )
    assert len(rebuilt.reports) == len(comparison.reports)
    # Report order is preserved, and nested results survive the round trip.
    assert [r.agent_name for r in rebuilt.reports] == [
        r.agent_name for r in comparison.reports
    ]
    assert rebuilt.reports[0].results[1].weaknesses == [WeaknessCode.VERIFY]


def test_from_dict_tolerates_missing_optional_fields():
    # Only the required pack identity is supplied.
    rebuilt = comparison_report_from_dict(
        {"pack_name": "p", "pack_version": "1.0"}
    )
    assert isinstance(rebuilt, ComparisonReport)
    assert rebuilt.agents == []
    assert rebuilt.ranking == []
    assert rebuilt.mean_scores_by_agent == {}
    assert rebuilt.weakness_tally_by_agent == {}
    assert rebuilt.reports == []
    assert rebuilt.total_tasks == 0


def test_save_writes_utf8_json_and_creates_parent_dirs(tmp_path):
    comparison = _comparison()
    # A nested path exercises parent-directory creation.
    path = tmp_path / "nested" / "deep" / "comparison.json"
    save_comparison_report(comparison, path)
    assert path.is_file()

    content = path.read_text(encoding="utf-8")
    # Indented JSON that parses back to an object.
    assert "\n" in content
    parsed = json.loads(content)
    assert parsed["pack_name"] == "demo_pack"


def test_load_reads_saved_file_correctly(tmp_path):
    comparison = _comparison()
    path = tmp_path / "comparison.json"
    save_comparison_report(comparison, path)

    loaded = load_comparison_report(path)
    assert isinstance(loaded, ComparisonReport)
    assert loaded.pack_name == comparison.pack_name
    assert loaded.pack_version == comparison.pack_version
    assert loaded.agents == comparison.agents
    assert loaded.ranking == comparison.ranking
    assert loaded.mean_scores_by_agent == comparison.mean_scores_by_agent
    assert (
        loaded.weakness_tally_by_agent
        == comparison.weakness_tally_by_agent
    )
    assert len(loaded.reports) == len(comparison.reports)


def test_from_dict_rejects_non_dict_data():
    with pytest.raises(ComparisonPersistenceError) as exc_info:
        comparison_report_from_dict(["not", "a", "dict"])
    assert "JSON object" in str(exc_info.value)


def test_from_dict_missing_required_field_raises_clear_error():
    with pytest.raises(ComparisonPersistenceError) as exc_info:
        comparison_report_from_dict({"pack_name": "demo"})  # no pack_version
    assert "missing required field" in str(exc_info.value)
    assert "pack_version" in str(exc_info.value)


def test_from_dict_invalid_nested_report_raises_clear_error():
    data = {
        "pack_name": "demo",
        "pack_version": "1.0",
        "reports": [{"pack_name": "demo"}],  # nested report missing fields
    }
    with pytest.raises(ComparisonPersistenceError) as exc_info:
        comparison_report_from_dict(data)
    assert "nested report" in str(exc_info.value)


def test_load_invalid_json_raises_clear_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ComparisonPersistenceError) as exc_info:
        load_comparison_report(path)
    assert "Invalid JSON" in str(exc_info.value)


def test_load_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(ComparisonPersistenceError) as exc_info:
        load_comparison_report(tmp_path / "no_such_comparison.json")
    assert "not found" in str(exc_info.value)


def test_load_non_object_json_raises_clear_error(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ComparisonPersistenceError):
        load_comparison_report(path)


def test_markdown_renderer_works_with_loaded_comparison(tmp_path):
    comparison = _comparison()
    path = tmp_path / "comparison.json"
    save_comparison_report(comparison, path)
    loaded = load_comparison_report(path)

    md = render_comparison_report_markdown(loaded)
    assert "Cross-Agent Comparison" in md
    assert "demo_pack" in md
    for agent in loaded.agents:
        assert agent in md


def test_persistence_is_agent_agnostic():
    # Arbitrary simulated agent names must round-trip unchanged; no provider
    # name is special-cased anywhere in the persistence layer.
    reports = [
        _run_report("simulated_agent_one", [_result("t1", 0.9)]),
        _run_report("simulated_agent_two", [_result("t1", 0.4)]),
    ]
    comparison = build_comparison_report(reports)
    rebuilt = comparison_report_from_dict(
        comparison_report_to_dict(comparison)
    )
    assert rebuilt.agents == ["simulated_agent_one", "simulated_agent_two"]
    assert rebuilt.ranking == comparison.ranking


def test_week2_and_week3_pipelines_still_work(tmp_path):
    # Week 2: build a run report from a pack via the evaluation pipeline.
    pack = BenchmarkPack(
        name="pipeline_pack",
        version="1.0",
        tasks=[TaskSpec(task_id="t1", title="A task")],
    )
    report = evaluate_pack_to_report(pack, "agent_simulated", {})

    # Week 3: comparison, Markdown rendering, then persistence round trip.
    comparison = build_comparison_report([report])
    assert isinstance(comparison, ComparisonReport)

    path = tmp_path / "pipeline_comparison.json"
    save_comparison_report(comparison, path)
    loaded = load_comparison_report(path)

    assert loaded.agents == ["agent_simulated"]
    assert loaded.pack_name == "pipeline_pack"
    md = render_comparison_report_markdown(loaded)
    assert "Cross-Agent Comparison" in md
