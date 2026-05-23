"""Tests for the external agent run artifact data model."""

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunArtifactError,
    agent_run_artifact_from_dict,
    agent_run_artifact_to_dict,
    make_agent_run_id,
    validate_agent_run_artifact,
)


def _minimal_artifact(**overrides) -> AgentRunArtifact:
    defaults = {
        "agent_name": "claude-code",
        "task_id": "bugfix-001",
        "run_id": "claude-code:bugfix-001:001",
    }
    defaults.update(overrides)
    return AgentRunArtifact(**defaults)


def test_minimal_artifact_validates():
    artifact = _minimal_artifact()
    validate_agent_run_artifact(artifact)
    assert artifact.diff_text == ""
    assert artifact.final_message == ""
    assert artifact.transcript_text == ""
    assert artifact.claimed_commands == []
    assert artifact.claimed_public_tests_passed is None
    assert artifact.claimed_hidden_tests_passed is None
    assert artifact.metadata == {}


def test_artifact_with_diff_text_and_final_message_validates():
    artifact = _minimal_artifact(
        diff_text="--- a/x\n+++ b/x\n@@\n-1\n+2\n",
        final_message="Done. Patch applies cleanly.",
        transcript_text="user: fix the bug\nassistant: ok",
        claimed_commands=["pytest", "ruff check"],
        claimed_public_tests_passed=True,
        claimed_hidden_tests_passed=False,
        metadata={"model": "claude-opus-4-7", "wall_time_s": "12.4"},
    )
    validate_agent_run_artifact(artifact)


def test_empty_agent_name_raises():
    with pytest.raises(AgentRunArtifactError, match="agent_name"):
        validate_agent_run_artifact(_minimal_artifact(agent_name=""))


def test_whitespace_agent_name_raises():
    with pytest.raises(AgentRunArtifactError, match="agent_name"):
        validate_agent_run_artifact(_minimal_artifact(agent_name="   "))


def test_empty_task_id_raises():
    with pytest.raises(AgentRunArtifactError, match="task_id"):
        validate_agent_run_artifact(_minimal_artifact(task_id=""))


def test_empty_run_id_raises():
    with pytest.raises(AgentRunArtifactError, match="run_id"):
        validate_agent_run_artifact(_minimal_artifact(run_id=""))


def test_diff_text_may_be_empty():
    artifact = _minimal_artifact(diff_text="")
    validate_agent_run_artifact(artifact)


def test_claimed_commands_must_be_list():
    artifact = _minimal_artifact(claimed_commands="pytest")  # type: ignore[arg-type]
    with pytest.raises(AgentRunArtifactError, match="claimed_commands"):
        validate_agent_run_artifact(artifact)


def test_claimed_commands_must_be_list_of_strings():
    artifact = _minimal_artifact(claimed_commands=["pytest", 42])  # type: ignore[list-item]
    with pytest.raises(AgentRunArtifactError, match=r"claimed_commands\[1\]"):
        validate_agent_run_artifact(artifact)


def test_metadata_must_be_dict():
    artifact = _minimal_artifact(metadata=[("k", "v")])  # type: ignore[arg-type]
    with pytest.raises(AgentRunArtifactError, match="metadata"):
        validate_agent_run_artifact(artifact)


def test_metadata_keys_must_be_strings():
    artifact = _minimal_artifact(metadata={1: "v"})  # type: ignore[dict-item]
    with pytest.raises(AgentRunArtifactError, match="metadata keys"):
        validate_agent_run_artifact(artifact)


def test_metadata_values_must_be_strings():
    artifact = _minimal_artifact(metadata={"k": 1})  # type: ignore[dict-item]
    with pytest.raises(AgentRunArtifactError, match="metadata"):
        validate_agent_run_artifact(artifact)


@pytest.mark.parametrize("value", [True, False, None])
def test_claimed_public_tests_passed_accepts_true_false_none(value):
    artifact = _minimal_artifact(claimed_public_tests_passed=value)
    validate_agent_run_artifact(artifact)


@pytest.mark.parametrize("value", [True, False, None])
def test_claimed_hidden_tests_passed_accepts_true_false_none(value):
    artifact = _minimal_artifact(claimed_hidden_tests_passed=value)
    validate_agent_run_artifact(artifact)


def test_claimed_public_tests_passed_rejects_string():
    artifact = _minimal_artifact(claimed_public_tests_passed="yes")  # type: ignore[arg-type]
    with pytest.raises(AgentRunArtifactError, match="claimed_public_tests_passed"):
        validate_agent_run_artifact(artifact)


def test_claimed_hidden_tests_passed_rejects_int():
    artifact = _minimal_artifact(claimed_hidden_tests_passed=1)  # type: ignore[arg-type]
    with pytest.raises(AgentRunArtifactError, match="claimed_hidden_tests_passed"):
        validate_agent_run_artifact(artifact)


def test_validate_does_not_mutate_artifact():
    artifact = _minimal_artifact(
        claimed_commands=["pytest"],
        metadata={"k": "v"},
    )
    snapshot_commands = list(artifact.claimed_commands)
    snapshot_metadata = dict(artifact.metadata)
    validate_agent_run_artifact(artifact)
    assert artifact.claimed_commands == snapshot_commands
    assert artifact.metadata == snapshot_metadata


def test_to_dict_includes_all_fields():
    artifact = _minimal_artifact(
        diff_text="diff",
        final_message="final",
        transcript_text="t",
        claimed_commands=["pytest"],
        claimed_public_tests_passed=True,
        claimed_hidden_tests_passed=False,
        metadata={"model": "x"},
    )
    data = agent_run_artifact_to_dict(artifact)
    assert data == {
        "agent_name": "claude-code",
        "task_id": "bugfix-001",
        "run_id": "claude-code:bugfix-001:001",
        "diff_text": "diff",
        "final_message": "final",
        "transcript_text": "t",
        "claimed_commands": ["pytest"],
        "claimed_public_tests_passed": True,
        "claimed_hidden_tests_passed": False,
        "metadata": {"model": "x"},
    }


def test_to_dict_returns_copied_list_and_dict():
    artifact = _minimal_artifact(
        claimed_commands=["pytest"],
        metadata={"k": "v"},
    )
    data = agent_run_artifact_to_dict(artifact)
    data["claimed_commands"].append("mutated")
    data["metadata"]["k"] = "mutated"
    assert artifact.claimed_commands == ["pytest"]
    assert artifact.metadata == {"k": "v"}


def test_from_dict_reconstructs_equivalent_artifact():
    original = _minimal_artifact(
        diff_text="diff",
        final_message="final",
        transcript_text="t",
        claimed_commands=["pytest", "ruff"],
        claimed_public_tests_passed=True,
        claimed_hidden_tests_passed=None,
        metadata={"model": "x"},
    )
    data = agent_run_artifact_to_dict(original)
    rebuilt = agent_run_artifact_from_dict(data)
    assert rebuilt == original


def test_round_trip_preserves_fields():
    original = _minimal_artifact(
        diff_text="some diff",
        final_message="message",
        transcript_text="transcript",
        claimed_commands=["a", "b"],
        claimed_public_tests_passed=False,
        claimed_hidden_tests_passed=True,
        metadata={"k1": "v1", "k2": "v2"},
    )
    rebuilt = agent_run_artifact_from_dict(agent_run_artifact_to_dict(original))
    assert rebuilt == original
    rebuilt2 = agent_run_artifact_from_dict(agent_run_artifact_to_dict(rebuilt))
    assert rebuilt2 == original


def test_from_dict_rejects_non_dict_input():
    with pytest.raises(AgentRunArtifactError, match="data must be a dict"):
        agent_run_artifact_from_dict("not a dict")  # type: ignore[arg-type]
    with pytest.raises(AgentRunArtifactError, match="data must be a dict"):
        agent_run_artifact_from_dict(None)  # type: ignore[arg-type]
    with pytest.raises(AgentRunArtifactError, match="data must be a dict"):
        agent_run_artifact_from_dict([])  # type: ignore[arg-type]


def test_from_dict_applies_safe_defaults():
    artifact = agent_run_artifact_from_dict(
        {
            "agent_name": "codex",
            "task_id": "bugfix-002",
            "run_id": "codex:bugfix-002:001",
        }
    )
    assert artifact.diff_text == ""
    assert artifact.final_message == ""
    assert artifact.transcript_text == ""
    assert artifact.claimed_commands == []
    assert artifact.claimed_public_tests_passed is None
    assert artifact.claimed_hidden_tests_passed is None
    assert artifact.metadata == {}


def test_from_dict_validates_reconstructed_artifact():
    with pytest.raises(AgentRunArtifactError, match="agent_name"):
        agent_run_artifact_from_dict(
            {"agent_name": "", "task_id": "t", "run_id": "r"}
        )


def test_from_dict_rejects_invalid_metadata():
    with pytest.raises(AgentRunArtifactError, match="metadata"):
        agent_run_artifact_from_dict(
            {
                "agent_name": "a",
                "task_id": "t",
                "run_id": "r",
                "metadata": {"k": 5},
            }
        )


def test_make_agent_run_id_is_deterministic():
    a = make_agent_run_id("Claude Code", "Bugfix 001")
    b = make_agent_run_id("Claude Code", "Bugfix 001")
    assert a == b
    assert a == "claude_code:bugfix_001"


def test_make_agent_run_id_includes_suffix():
    run_id = make_agent_run_id("claude-code", "bugfix-001", suffix="attempt 2")
    assert run_id == "claude-code:bugfix-001:attempt_2"


def test_make_agent_run_id_omits_blank_suffix():
    assert make_agent_run_id("a", "b", suffix="") == "a:b"
    assert make_agent_run_id("a", "b", suffix="   ") == "a:b"


def test_make_agent_run_id_result_is_valid_run_id():
    run_id = make_agent_run_id("claude code", "bugfix 001", "v1")
    artifact = AgentRunArtifact(
        agent_name="claude code",
        task_id="bugfix 001",
        run_id=run_id,
    )
    validate_agent_run_artifact(artifact)
