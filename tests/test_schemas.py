"""Tests for the core dataclasses and enums."""

from agenteval.core.schemas import (
    AgentRun,
    EvaluationResult,
    PatchSummary,
    TaskSpec,
    WeaknessCode,
)


def test_task_spec_instantiation():
    task = TaskSpec(task_id="t1", title="Fix the off-by-one bug")
    assert task.task_id == "t1"
    assert task.title == "Fix the off-by-one bug"
    # Mutable defaults are independent per instance.
    assert task.public_tests == []
    assert task.hidden_tests == []


def test_agent_run_instantiation():
    run = AgentRun(run_id="r1", agent_name="claude-code", task_id="t1")
    assert run.agent_name == "claude-code"
    assert run.commands_run == []


def test_patch_summary_instantiation():
    patch = PatchSummary(changed_files=["agenteval/core/scoring.py"])
    assert patch.changed_files == ["agenteval/core/scoring.py"]
    assert patch.added_files == []
    assert patch.deleted_files == []
    assert patch.diff_text == ""


def test_evaluation_result_instantiation():
    result = EvaluationResult(
        task_id="t1",
        run_id="r1",
        score=0.5,
        passed_public_tests=True,
        weaknesses=[WeaknessCode.LAZY],
        rationale="Partial solution.",
    )
    assert result.score == 0.5
    assert result.passed_public_tests is True
    assert result.passed_hidden_tests is False
    assert result.weaknesses == [WeaknessCode.LAZY]


def test_evaluation_result_default_weaknesses_are_independent():
    a = EvaluationResult(task_id="t1", run_id="r1")
    b = EvaluationResult(task_id="t2", run_id="r2")
    a.weaknesses.append(WeaknessCode.INST)
    assert a.weaknesses == [WeaknessCode.INST]
    assert b.weaknesses == []


def test_weakness_codes_available():
    expected = {
        "INST",
        "OVERENG",
        "TOOL",
        "LAZY",
        "VERIFY",
        "FALSE",
        "ROOT",
        "DESTRUCT",
        "FILE",
        "HALLUC",
        "DOCS",
        "VERBOSE",
    }
    assert {code.name for code in WeaknessCode} == expected


def test_weakness_code_is_str_enum():
    # Inheriting from str makes values serialization-friendly.
    assert WeaknessCode.FALSE == "FALSE"
    assert WeaknessCode.FALSE.value == "FALSE"
