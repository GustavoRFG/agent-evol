"""Tests for deterministic agent run artifact directory scanning."""

import json
from pathlib import Path

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunDiscoveryError,
    discover_agent_run_artifact_paths,
    load_agent_run_artifacts_from_dir,
    load_agent_run_artifacts_with_paths,
    save_agent_run_artifact,
    save_agent_run_artifact_folder,
)


def _artifact(agent_name: str, task_id: str, *, run_id: str | None = None) -> AgentRunArtifact:
    return AgentRunArtifact(
        agent_name=agent_name,
        task_id=task_id,
        run_id=run_id or f"{agent_name}:{task_id}:001",
        diff_text="--- a/x\n+++ b/x\n",
        final_message="done",
    )


def test_missing_root_raises(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(AgentRunDiscoveryError, match="does not exist"):
        discover_agent_run_artifact_paths(missing)


def test_file_root_raises(tmp_path: Path):
    file_root = tmp_path / "a-file.txt"
    file_root.write_text("hi", encoding="utf-8")
    with pytest.raises(AgentRunDiscoveryError, match="not a directory"):
        discover_agent_run_artifact_paths(file_root)


def test_empty_directory_returns_empty_list(tmp_path: Path):
    assert discover_agent_run_artifact_paths(tmp_path) == []


def test_nested_agent_run_json_files_are_discovered(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("a1", "t1"), tmp_path / "a1" / "t1")
    save_agent_run_artifact_folder(
        _artifact("a1", "t2"), tmp_path / "a1" / "t2" / "run-001"
    )
    save_agent_run_artifact_folder(
        _artifact("a2", "t1"), tmp_path / "a2" / "t1"
    )
    # An unrelated file should not be picked up.
    (tmp_path / "a1" / "notes.txt").write_text("ignore me", encoding="utf-8")

    paths = discover_agent_run_artifact_paths(tmp_path)

    assert len(paths) == 3
    assert all(p.name == "agent_run.json" for p in paths)


def test_discovery_ordering_is_deterministic(tmp_path: Path):
    # Create folders in non-lexicographic order; result must still be sorted.
    save_agent_run_artifact_folder(_artifact("z-agent", "t1"), tmp_path / "z" / "t1")
    save_agent_run_artifact_folder(_artifact("a-agent", "t1"), tmp_path / "a" / "t1")
    save_agent_run_artifact_folder(_artifact("m-agent", "t1"), tmp_path / "m" / "t1")
    save_agent_run_artifact_folder(_artifact("a-agent", "t2"), tmp_path / "a" / "t2")

    paths1 = discover_agent_run_artifact_paths(tmp_path)
    paths2 = discover_agent_run_artifact_paths(tmp_path)

    assert paths1 == paths2
    posix_strings = [p.as_posix() for p in paths1]
    assert posix_strings == sorted(posix_strings)
    assert "/a/t1/" in posix_strings[0]
    assert "/z/t1/" in posix_strings[-1]


def test_custom_filename_works(tmp_path: Path):
    folder = tmp_path / "custom"
    save_agent_run_artifact_folder(
        _artifact("a1", "t1"), folder, filename="claude.json"
    )
    # A default-named file should be ignored by the custom filter.
    save_agent_run_artifact_folder(_artifact("a1", "t2"), tmp_path / "default")

    paths = discover_agent_run_artifact_paths(tmp_path, filename="claude.json")

    assert len(paths) == 1
    assert paths[0].name == "claude.json"


def test_discovery_rejects_empty_filename(tmp_path: Path):
    with pytest.raises(AgentRunDiscoveryError, match="filename"):
        discover_agent_run_artifact_paths(tmp_path, filename="")
    with pytest.raises(AgentRunDiscoveryError, match="filename"):
        discover_agent_run_artifact_paths(tmp_path, filename="   ")


def test_discovery_accepts_string_root(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("a1", "t1"), tmp_path / "a1" / "t1")
    paths = discover_agent_run_artifact_paths(str(tmp_path))
    assert len(paths) == 1


def test_load_from_dir_returns_multiple_valid_artifacts(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("a1", "t1"), tmp_path / "a1" / "t1")
    save_agent_run_artifact_folder(_artifact("a1", "t2"), tmp_path / "a1" / "t2")
    save_agent_run_artifact_folder(_artifact("a2", "t1"), tmp_path / "a2" / "t1")

    artifacts = load_agent_run_artifacts_from_dir(tmp_path)

    assert len(artifacts) == 3
    assert {(a.agent_name, a.task_id) for a in artifacts} == {
        ("a1", "t1"),
        ("a1", "t2"),
        ("a2", "t1"),
    }


def test_loaded_artifact_order_follows_discovered_path_order(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("z-agent", "t1"), tmp_path / "z" / "t1")
    save_agent_run_artifact_folder(_artifact("a-agent", "t1"), tmp_path / "a" / "t1")
    save_agent_run_artifact_folder(_artifact("m-agent", "t1"), tmp_path / "m" / "t1")

    paths = discover_agent_run_artifact_paths(tmp_path)
    artifacts = load_agent_run_artifacts_from_dir(tmp_path)

    assert len(artifacts) == len(paths) == 3
    assert [a.agent_name for a in artifacts] == ["a-agent", "m-agent", "z-agent"]


def test_invalid_artifact_raises_when_skip_invalid_false(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("a1", "t1"), tmp_path / "good")
    bad_folder = tmp_path / "bad"
    bad_folder.mkdir()
    (bad_folder / "agent_run.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(AgentRunDiscoveryError, match="bad"):
        load_agent_run_artifacts_from_dir(tmp_path)


def test_invalid_artifact_skipped_when_skip_invalid_true(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("a1", "t1"), tmp_path / "good1")
    save_agent_run_artifact_folder(_artifact("a2", "t1"), tmp_path / "good2")

    bad_json_folder = tmp_path / "bad-json"
    bad_json_folder.mkdir()
    (bad_json_folder / "agent_run.json").write_text("{not json", encoding="utf-8")

    bad_struct_folder = tmp_path / "bad-struct"
    bad_struct_folder.mkdir()
    (bad_struct_folder / "agent_run.json").write_text(
        json.dumps({"agent_name": "", "task_id": "t", "run_id": "r"}),
        encoding="utf-8",
    )

    artifacts = load_agent_run_artifacts_from_dir(tmp_path, skip_invalid=True)

    assert len(artifacts) == 2
    assert {a.agent_name for a in artifacts} == {"a1", "a2"}


def test_load_with_paths_returns_path_and_artifact(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("a1", "t1"), tmp_path / "a1" / "t1")
    save_agent_run_artifact_folder(_artifact("a1", "t2"), tmp_path / "a1" / "t2")

    pairs = load_agent_run_artifacts_with_paths(tmp_path)

    assert len(pairs) == 2
    for path, artifact in pairs:
        assert isinstance(path, Path)
        assert isinstance(artifact, AgentRunArtifact)
        assert path.is_file()
        assert path.name == "agent_run.json"
    # Order matches discovery.
    expected_paths = discover_agent_run_artifact_paths(tmp_path)
    assert [p for p, _ in pairs] == expected_paths


def test_load_with_paths_skip_invalid_drops_pair(tmp_path: Path):
    save_agent_run_artifact_folder(_artifact("a1", "t1"), tmp_path / "good")
    bad_folder = tmp_path / "bad"
    bad_folder.mkdir()
    (bad_folder / "agent_run.json").write_text("{not json", encoding="utf-8")

    pairs = load_agent_run_artifacts_with_paths(tmp_path, skip_invalid=True)

    assert len(pairs) == 1
    assert pairs[0][1].agent_name == "a1"


def test_load_with_paths_propagates_when_not_skipping(tmp_path: Path):
    bad_folder = tmp_path / "bad"
    bad_folder.mkdir()
    (bad_folder / "agent_run.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(AgentRunDiscoveryError, match="failed to load"):
        load_agent_run_artifacts_with_paths(tmp_path)


def test_round_trip_save_discover_load(tmp_path: Path):
    a1 = _artifact("a1", "t1")
    a2 = _artifact("a2", "t1")
    save_agent_run_artifact(a1, tmp_path / "a1" / "t1" / "agent_run.json")
    save_agent_run_artifact(a2, tmp_path / "a2" / "t1" / "agent_run.json")

    loaded = load_agent_run_artifacts_from_dir(tmp_path)

    assert {a.agent_name for a in loaded} == {"a1", "a2"}
    by_name = {a.agent_name: a for a in loaded}
    assert by_name["a1"] == a1
    assert by_name["a2"] == a2
