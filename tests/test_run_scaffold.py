"""Tests for the placeholder evaluation run scaffold."""

from pathlib import Path

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.core.schemas import (
    AgentRun,
    BenchmarkPack,
    EvaluationResult,
    TaskSpec,
    WeaknessCode,
)
from agenteval.runs.scaffold import (
    create_placeholder_run,
    evaluate_pack_placeholder,
    evaluate_placeholder_run,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _task(task_id: str = "t1", title: str = "A task") -> TaskSpec:
    return TaskSpec(task_id=task_id, title=title)


def test_create_placeholder_run_is_deterministic():
    task = _task("bugfix_001")
    run_a = create_placeholder_run(task, "claude-code")
    run_b = create_placeholder_run(task, "claude-code")
    assert isinstance(run_a, AgentRun)
    assert run_a.run_id == "claude-code:bugfix_001:placeholder"
    assert run_a.run_id == run_b.run_id
    assert run_a.agent_name == "claude-code"
    assert run_a.task_id == "bugfix_001"
    assert run_a.transcript_path == ""
    assert run_a.commands_run == []
    assert run_a.final_message != ""


def test_placeholder_run_final_message_states_no_execution():
    run = create_placeholder_run(_task(), "codex")
    assert "placeholder" in run.final_message.lower()


def test_evaluate_placeholder_run_records_verify_weakness():
    task = _task("bugfix_001")
    run = create_placeholder_run(task, "claude-code")
    result = evaluate_placeholder_run(task, run)
    assert isinstance(result, EvaluationResult)
    assert result.task_id == "bugfix_001"
    assert result.run_id == run.run_id
    assert WeaknessCode.VERIFY in result.weaknesses


def test_placeholder_evaluation_does_not_pretend_tests_passed():
    task = _task()
    run = create_placeholder_run(task, "forge-agent")
    result = evaluate_placeholder_run(task, run)
    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    # No tests passed plus a VERIFY weakness -> score clamps to 0.0.
    assert result.score == 0.0
    assert result.rationale != ""


def test_evaluate_pack_placeholder_returns_one_result_per_task():
    pack = BenchmarkPack(
        name="demo",
        tasks=[_task("a"), _task("b"), _task("c")],
    )
    results = evaluate_pack_placeholder(pack, "claude-code")
    assert len(results) == 3
    assert all(isinstance(result, EvaluationResult) for result in results)


def test_evaluate_pack_placeholder_preserves_task_order():
    pack = BenchmarkPack(
        name="demo",
        tasks=[_task("first"), _task("second"), _task("third")],
    )
    results = evaluate_pack_placeholder(pack, "codex")
    assert [result.task_id for result in results] == [
        "first",
        "second",
        "third",
    ]


def test_evaluate_pack_placeholder_empty_pack_returns_empty_list():
    pack = BenchmarkPack(name="empty")
    assert evaluate_pack_placeholder(pack, "claude-code") == []


def test_shipped_pack_runs_through_placeholder_pipeline():
    pack_dir = REPO_ROOT / "benchmarks" / "python_bugfix_basic"
    pack = load_benchmark_pack(pack_dir)
    results = evaluate_pack_placeholder(pack, "claude-code")
    assert len(results) == len(pack.tasks)
    assert len(results) >= 1
    for result in results:
        assert WeaknessCode.VERIFY in result.weaknesses
        assert result.passed_public_tests is False
        assert result.passed_hidden_tests is False
        assert result.score == 0.0
