"""Tests for run report aggregation and JSON persistence."""

import json
from pathlib import Path

import pytest

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import (
    BenchmarkPack,
    EvaluationResult,
    RunReport,
    WeaknessCode,
)
from agenteval.reports.run_report import (
    RunReportError,
    build_run_report,
    load_run_report,
    run_report_from_dict,
    run_report_to_dict,
    save_run_report,
)
from agenteval.runs.scaffold import evaluate_pack_placeholder

REPO_ROOT = Path(__file__).resolve().parent.parent


def _result(
    task_id: str,
    score: float,
    weaknesses: list[WeaknessCode] | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=f"agent:{task_id}:placeholder",
        score=score,
        weaknesses=list(weaknesses or []),
    )


def _pack() -> BenchmarkPack:
    return BenchmarkPack(name="demo_pack", version="1.0")


def test_build_run_report_counts_total_tasks():
    results = [_result("a", 0.5), _result("b", 1.0), _result("c", 0.0)]
    report = build_run_report(_pack(), "claude-code", results)
    assert isinstance(report, RunReport)
    assert report.total_tasks == 3
    assert report.pack_name == "demo_pack"
    assert report.pack_version == "1.0"
    assert report.agent_name == "claude-code"


def test_build_run_report_computes_mean_score():
    results = [_result("a", 0.0), _result("b", 0.5), _result("c", 1.0)]
    report = build_run_report(_pack(), "codex", results)
    assert report.mean_score == 0.5


def test_build_run_report_empty_results_mean_score_is_zero():
    report = build_run_report(_pack(), "codex", [])
    assert report.total_tasks == 0
    assert report.mean_score == 0.0
    assert report.results == []


def test_build_run_report_counts_weakness_tally():
    results = [
        _result("a", 0.0, [WeaknessCode.VERIFY, WeaknessCode.INST]),
        _result("b", 0.0, [WeaknessCode.VERIFY]),
    ]
    report = build_run_report(_pack(), "forge-agent", results)
    assert report.weakness_tally == {"VERIFY": 2, "INST": 1}
    # Tally keys must be plain strings for JSON friendliness.
    assert all(isinstance(key, str) for key in report.weakness_tally)


def test_build_run_report_preserves_results_order():
    results = [_result("first", 0.1), _result("second", 0.2)]
    report = build_run_report(_pack(), "codex", results)
    assert [r.task_id for r in report.results] == ["first", "second"]
    # The report holds a copy, not an alias of the input list.
    results.append(_result("third", 0.3))
    assert len(report.results) == 2


def test_run_report_to_dict_is_json_friendly():
    results = [_result("a", 0.5, [WeaknessCode.VERIFY])]
    report = build_run_report(_pack(), "claude-code", results)
    data = run_report_to_dict(report)
    # Must be serializable without error and contain string weakness codes.
    encoded = json.dumps(data)
    assert isinstance(encoded, str)
    assert data["results"][0]["weaknesses"] == ["VERIFY"]
    assert data["weakness_tally"] == {"VERIFY": 1}


def test_run_report_from_dict_reconstructs_report():
    results = [_result("a", 0.5, [WeaknessCode.VERIFY, WeaknessCode.LAZY])]
    report = build_run_report(_pack(), "codex", results)
    rebuilt = run_report_from_dict(run_report_to_dict(report))
    assert isinstance(rebuilt, RunReport)
    assert rebuilt.pack_name == report.pack_name
    assert rebuilt.agent_name == report.agent_name
    assert rebuilt.total_tasks == report.total_tasks
    assert rebuilt.mean_score == report.mean_score
    assert rebuilt.weakness_tally == report.weakness_tally
    assert rebuilt.results[0].task_id == "a"
    # Weakness codes are restored as WeaknessCode enum members.
    assert rebuilt.results[0].weaknesses == [
        WeaknessCode.VERIFY,
        WeaknessCode.LAZY,
    ]


def test_save_and_load_run_report_round_trip(tmp_path):
    results = [
        _result("a", 0.5, [WeaknessCode.VERIFY]),
        _result("b", 1.0, []),
    ]
    report = build_run_report(_pack(), "claude-code", results)
    path = tmp_path / "report.json"

    save_run_report(report, path)
    assert path.is_file()

    loaded = load_run_report(path)
    assert loaded.pack_name == report.pack_name
    assert loaded.total_tasks == report.total_tasks
    assert loaded.mean_score == report.mean_score
    assert loaded.weakness_tally == report.weakness_tally
    assert [r.task_id for r in loaded.results] == ["a", "b"]
    assert loaded.results[0].weaknesses == [WeaknessCode.VERIFY]


def test_load_run_report_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(RunReportError) as exc_info:
        load_run_report(tmp_path / "no_such_report.json")
    assert "not found" in str(exc_info.value)


def test_run_report_from_dict_missing_field_raises_clear_error():
    with pytest.raises(RunReportError) as exc_info:
        run_report_from_dict({"pack_name": "demo"})  # missing other fields
    assert "missing required field" in str(exc_info.value)


def test_shipped_pack_produces_run_report():
    pack_dir = REPO_ROOT / "benchmarks" / "python_bugfix_basic"
    pack = load_benchmark_pack(pack_dir)
    results = evaluate_pack_placeholder(pack, "claude-code")
    report = build_run_report(pack, "claude-code", results)
    assert report.pack_name == "python_bugfix_basic"
    assert report.agent_name == "claude-code"
    assert report.total_tasks == len(pack.tasks)
    assert report.total_tasks >= 1
    # Placeholder results all carry a VERIFY weakness.
    assert report.weakness_tally.get("VERIFY") == report.total_tasks
