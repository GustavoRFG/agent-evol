"""Tests for JSON file persistence of :class:`AgentRunArtifact`."""

import json
from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunPersistenceError,
    load_agent_run_artifact,
    save_agent_run_artifact,
    save_agent_run_artifact_folder,
)


def _sample_artifact(**overrides) -> AgentRunArtifact:
    defaults = {
        "agent_name": "claude-code",
        "task_id": "bugfix-001",
        "run_id": "claude-code:bugfix-001:001",
        "diff_text": "--- a/x\n+++ b/x\n@@\n-1\n+2\n",
        "final_message": "Done.",
        "transcript_text": "user: fix it\nassistant: ok",
        "claimed_commands": ["pytest", "ruff check"],
        "claimed_public_tests_passed": True,
        "claimed_hidden_tests_passed": False,
        "metadata": {"model": "claude-opus-4-7", "wall_time_s": "12.4"},
    }
    defaults.update(overrides)
    return AgentRunArtifact(**defaults)


def test_save_writes_a_json_file(tmp_path: Path):
    artifact = _sample_artifact()
    target = tmp_path / "run.json"

    save_agent_run_artifact(artifact, target)

    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["agent_name"] == "claude-code"
    assert data["task_id"] == "bugfix-001"
    assert data["claimed_commands"] == ["pytest", "ruff check"]
    assert data["metadata"] == {"model": "claude-opus-4-7", "wall_time_s": "12.4"}


def test_save_creates_parent_directories(tmp_path: Path):
    artifact = _sample_artifact()
    target = tmp_path / "nested" / "deeper" / "run.json"

    save_agent_run_artifact(artifact, target)

    assert target.is_file()


def test_save_accepts_string_path(tmp_path: Path):
    artifact = _sample_artifact()
    target = tmp_path / "run.json"

    save_agent_run_artifact(artifact, str(target))

    assert target.is_file()


def test_save_uses_readable_indentation(tmp_path: Path):
    artifact = _sample_artifact()
    target = tmp_path / "run.json"

    save_agent_run_artifact(artifact, target)
    text = target.read_text(encoding="utf-8")

    assert "\n" in text
    assert "  " in text


def test_load_returns_artifact_equivalent_to_original(tmp_path: Path):
    artifact = _sample_artifact()
    target = tmp_path / "run.json"
    save_agent_run_artifact(artifact, target)

    loaded = load_agent_run_artifact(target)

    assert loaded == artifact


def test_round_trip_preserves_all_fields(tmp_path: Path):
    artifact = _sample_artifact(
        claimed_public_tests_passed=None,
        claimed_hidden_tests_passed=None,
        metadata={"k1": "v1", "k2": "v2"},
    )
    target = tmp_path / "run.json"

    save_agent_run_artifact(artifact, target)
    loaded = load_agent_run_artifact(target)

    assert loaded == artifact
    assert loaded.claimed_public_tests_passed is None
    assert loaded.claimed_hidden_tests_passed is None


def test_loaded_artifact_validates(tmp_path: Path):
    from agenteval.agent_runs import validate_agent_run_artifact

    artifact = _sample_artifact()
    target = tmp_path / "run.json"
    save_agent_run_artifact(artifact, target)

    loaded = load_agent_run_artifact(target)
    validate_agent_run_artifact(loaded)


def test_save_does_not_mutate_artifact(tmp_path: Path):
    artifact = _sample_artifact()
    snapshot_commands = list(artifact.claimed_commands)
    snapshot_metadata = dict(artifact.metadata)
    target = tmp_path / "run.json"

    save_agent_run_artifact(artifact, target)

    assert artifact.claimed_commands == snapshot_commands
    assert artifact.metadata == snapshot_metadata


def test_save_rejects_invalid_artifact(tmp_path: Path):
    artifact = _sample_artifact(agent_name="")
    target = tmp_path / "run.json"

    with pytest.raises(AgentRunPersistenceError, match="agent_name"):
        save_agent_run_artifact(artifact, target)

    assert not target.exists()


def test_load_missing_file_raises(tmp_path: Path):
    target = tmp_path / "does_not_exist.json"

    with pytest.raises(AgentRunPersistenceError, match="not found"):
        load_agent_run_artifact(target)


def test_load_invalid_json_raises(tmp_path: Path):
    target = tmp_path / "broken.json"
    target.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(AgentRunPersistenceError, match="invalid JSON"):
        load_agent_run_artifact(target)


def test_load_non_object_json_raises(tmp_path: Path):
    target = tmp_path / "list.json"
    target.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(AgentRunPersistenceError, match="invalid agent run artifact"):
        load_agent_run_artifact(target)


def test_load_json_with_invalid_structure_raises(tmp_path: Path):
    target = tmp_path / "bad.json"
    target.write_text(
        json.dumps(
            {
                "agent_name": "",
                "task_id": "t",
                "run_id": "r",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AgentRunPersistenceError, match="agent_name"):
        load_agent_run_artifact(target)


def test_load_json_with_wrong_field_type_raises(tmp_path: Path):
    target = tmp_path / "bad.json"
    target.write_text(
        json.dumps(
            {
                "agent_name": "a",
                "task_id": "t",
                "run_id": "r",
                "claimed_commands": "pytest",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AgentRunPersistenceError, match="claimed_commands"):
        load_agent_run_artifact(target)


def test_save_to_folder_uses_default_filename(tmp_path: Path):
    artifact = _sample_artifact()
    folder = tmp_path / "run-folder"

    final_path = save_agent_run_artifact_folder(artifact, folder)

    assert final_path == folder / "agent_run.json"
    assert final_path.is_file()
    loaded = load_agent_run_artifact(final_path)
    assert loaded == artifact


def test_save_to_folder_accepts_custom_filename(tmp_path: Path):
    artifact = _sample_artifact()
    folder = tmp_path / "run-folder"

    final_path = save_agent_run_artifact_folder(
        artifact, folder, filename="claude.json"
    )

    assert final_path == folder / "claude.json"
    assert final_path.is_file()


def test_save_to_folder_rejects_empty_filename(tmp_path: Path):
    artifact = _sample_artifact()

    with pytest.raises(AgentRunPersistenceError, match="filename"):
        save_agent_run_artifact_folder(artifact, tmp_path, filename="")
    with pytest.raises(AgentRunPersistenceError, match="filename"):
        save_agent_run_artifact_folder(artifact, tmp_path, filename="   ")
