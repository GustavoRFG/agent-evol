"""Tests for the Markdown run report renderer."""

from pathlib import Path

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import BenchmarkPack, EvaluationResult, WeaknessCode
from agenteval.reports.markdown import (
    render_run_report_markdown,
    save_run_report_markdown,
)
from agenteval.reports.run_report import build_run_report
from agenteval.runs.scaffold import evaluate_pack_placeholder

REPO_ROOT = Path(__file__).resolve().parent.parent


def _result(
    task_id: str,
    score: float,
    weaknesses: list[WeaknessCode] | None = None,
    rationale: str = "A rationale.",
) -> EvaluationResult:
    return EvaluationResult(
        task_id=task_id,
        run_id=f"claude-code:{task_id}:placeholder",
        score=score,
        weaknesses=list(weaknesses or []),
        rationale=rationale,
    )


def _report(results: list[EvaluationResult]):
    pack = BenchmarkPack(name="demo_pack", version="1.2")
    return build_run_report(pack, "claude-code", results)


def test_markdown_includes_report_metadata():
    md = render_run_report_markdown(_report([_result("a", 0.5)]))
    assert "demo_pack" in md
    assert "1.2" in md
    assert "claude-code" in md
    assert "Total tasks" in md
    assert "Mean score" in md


def test_markdown_includes_weakness_tally():
    report = _report(
        [
            _result("a", 0.0, [WeaknessCode.VERIFY]),
            _result("b", 0.0, [WeaknessCode.VERIFY, WeaknessCode.INST]),
        ]
    )
    md = render_run_report_markdown(report)
    assert "Weakness tally" in md
    assert "VERIFY" in md
    assert "INST" in md


def test_markdown_includes_per_task_table():
    md = render_run_report_markdown(_report([_result("a", 0.5)]))
    assert "Per-task results" in md
    # A Markdown table header separator row is present.
    assert "| --- |" in md


def test_markdown_includes_task_ids_and_run_ids():
    md = render_run_report_markdown(_report([_result("bugfix_042", 0.5)]))
    assert "bugfix_042" in md
    assert "claude-code:bugfix_042:placeholder" in md


def test_markdown_includes_rationales():
    md = render_run_report_markdown(
        _report([_result("a", 0.5, rationale="Root cause was X.")])
    )
    assert "Per-task rationale" in md
    assert "Root cause was X." in md


def test_markdown_handles_empty_results_gracefully():
    md = render_run_report_markdown(_report([]))
    assert isinstance(md, str)
    assert "Total tasks" in md
    assert "No tasks were evaluated" in md
    assert "No weaknesses recorded" in md


def test_markdown_is_deterministic():
    report = _report(
        [
            _result("a", 0.0, [WeaknessCode.VERIFY]),
            _result("b", 0.0, [WeaknessCode.INST]),
        ]
    )
    assert render_run_report_markdown(report) == render_run_report_markdown(
        report
    )


def test_save_run_report_markdown_writes_utf8_file(tmp_path):
    report = _report(
        [_result("a", 0.5, rationale="Café déjà vu — ünïcode.")]
    )
    # A nested path also exercises parent-directory creation.
    path = tmp_path / "nested" / "report.md"
    save_run_report_markdown(report, path)
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "Café déjà vu — ünïcode." in content
    assert content.startswith("# ")


def test_shipped_pack_renders_markdown_report():
    pack_dir = REPO_ROOT / "benchmarks" / "python_bugfix_basic"
    pack = load_benchmark_pack(pack_dir)
    results = evaluate_pack_placeholder(pack, "claude-code")
    report = build_run_report(pack, "claude-code", results)
    md = render_run_report_markdown(report)
    assert "python_bugfix_basic" in md
    assert "bugfix_001" in md
    assert "VERIFY" in md
