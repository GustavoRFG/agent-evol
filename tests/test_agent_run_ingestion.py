"""Tests for the AgentRunArtifact -> preliminary evidence ingestion bridge."""

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunIngestionError,
    IngestedAgentRun,
    build_preliminary_task_evidence_from_artifact,
    ingest_agent_run_artifact,
    ingest_agent_run_artifacts,
    parse_patch_summary_from_artifact,
)
from agenteval.core.schemas import PatchSummary, WeaknessCode
from agenteval.evaluation.batch_builder import TaskEvidence

VALID_DIFF = """diff --git a/sum_range.py b/sum_range.py
index abc1234..def5678 100644
--- a/sum_range.py
+++ b/sum_range.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end))
+    return sum(range(start, end + 1))
"""


def _artifact(**overrides) -> AgentRunArtifact:
    defaults = {
        "agent_name": "claude-code",
        "task_id": "bugfix-001",
        "run_id": "claude-code:bugfix-001:001",
    }
    defaults.update(overrides)
    return AgentRunArtifact(**defaults)


# ---- parse_patch_summary_from_artifact -------------------------------------


def test_empty_diff_returns_none_patch_summary():
    assert parse_patch_summary_from_artifact(_artifact(diff_text="")) is None


def test_whitespace_only_diff_returns_none_patch_summary():
    assert parse_patch_summary_from_artifact(_artifact(diff_text="   \n\t")) is None


def test_valid_diff_returns_patch_summary():
    summary = parse_patch_summary_from_artifact(_artifact(diff_text=VALID_DIFF))
    assert isinstance(summary, PatchSummary)
    assert summary.diff_text == VALID_DIFF


def test_parsed_patch_summary_includes_changed_files():
    summary = parse_patch_summary_from_artifact(_artifact(diff_text=VALID_DIFF))
    assert summary is not None
    assert summary.changed_files == ["sum_range.py"]
    assert summary.added_files == []
    assert summary.deleted_files == []


def test_parse_does_not_mutate_artifact():
    artifact = _artifact(diff_text=VALID_DIFF)
    snapshot = artifact.diff_text
    parse_patch_summary_from_artifact(artifact)
    assert artifact.diff_text == snapshot


# ---- build_preliminary_task_evidence_from_artifact -------------------------


def test_preliminary_evidence_is_unverified_with_verify_weakness():
    evidence = build_preliminary_task_evidence_from_artifact(_artifact())
    assert isinstance(evidence, TaskEvidence)
    assert evidence.passed_public_tests is False
    assert evidence.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in evidence.weaknesses


def test_preliminary_evidence_does_not_trust_claimed_public_tests():
    evidence = build_preliminary_task_evidence_from_artifact(
        _artifact(claimed_public_tests_passed=True)
    )
    assert evidence.passed_public_tests is False
    assert WeaknessCode.VERIFY in evidence.weaknesses


def test_preliminary_evidence_does_not_trust_claimed_hidden_tests():
    evidence = build_preliminary_task_evidence_from_artifact(
        _artifact(claimed_hidden_tests_passed=True)
    )
    assert evidence.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in evidence.weaknesses


def test_rationale_mentions_no_tests_executed_by_agenteval_forge():
    evidence = build_preliminary_task_evidence_from_artifact(_artifact())
    assert "AgentEval Forge" in evidence.rationale
    assert "not executed" in evidence.rationale


def test_rationale_mentions_agent_claims_when_present():
    evidence = build_preliminary_task_evidence_from_artifact(
        _artifact(
            claimed_public_tests_passed=True,
            claimed_hidden_tests_passed=False,
        )
    )
    assert "agent claimed public tests passed" in evidence.rationale
    assert "agent claimed hidden tests failed" in evidence.rationale
    assert "unverified" in evidence.rationale.lower()


def test_rationale_omits_claim_section_when_no_claims():
    evidence = build_preliminary_task_evidence_from_artifact(_artifact())
    assert "agent claimed" not in evidence.rationale


def test_rationale_is_deterministic_for_same_input():
    a = build_preliminary_task_evidence_from_artifact(
        _artifact(claimed_public_tests_passed=True)
    )
    b = build_preliminary_task_evidence_from_artifact(
        _artifact(claimed_public_tests_passed=True)
    )
    assert a.rationale == b.rationale


def test_final_message_is_preserved():
    evidence = build_preliminary_task_evidence_from_artifact(
        _artifact(final_message="all done")
    )
    assert evidence.final_message == "all done"


def test_diff_text_is_preserved_when_present():
    evidence = build_preliminary_task_evidence_from_artifact(
        _artifact(diff_text=VALID_DIFF)
    )
    assert evidence.diff_text == VALID_DIFF


def test_diff_text_is_none_when_artifact_diff_is_empty():
    evidence = build_preliminary_task_evidence_from_artifact(_artifact())
    assert evidence.diff_text is None


def test_build_preliminary_evidence_does_not_mutate_artifact():
    artifact = _artifact(
        diff_text=VALID_DIFF,
        final_message="msg",
        claimed_public_tests_passed=True,
        claimed_commands=["pytest"],
        metadata={"k": "v"},
    )
    snapshot_commands = list(artifact.claimed_commands)
    snapshot_metadata = dict(artifact.metadata)
    build_preliminary_task_evidence_from_artifact(artifact)
    assert artifact.diff_text == VALID_DIFF
    assert artifact.final_message == "msg"
    assert artifact.claimed_public_tests_passed is True
    assert artifact.claimed_commands == snapshot_commands
    assert artifact.metadata == snapshot_metadata


# ---- ingest_agent_run_artifact ---------------------------------------------


def test_ingest_returns_ingested_agent_run_with_all_parts():
    artifact = _artifact(
        diff_text=VALID_DIFF,
        final_message="done",
        claimed_public_tests_passed=True,
    )
    result = ingest_agent_run_artifact(artifact)

    assert isinstance(result, IngestedAgentRun)
    assert result.artifact is artifact
    assert isinstance(result.patch_summary, PatchSummary)
    assert result.patch_summary.changed_files == ["sum_range.py"]
    assert isinstance(result.preliminary_evidence, TaskEvidence)
    assert result.preliminary_evidence.passed_public_tests is False
    assert WeaknessCode.VERIFY in result.preliminary_evidence.weaknesses


def test_ingest_returns_none_patch_summary_for_empty_diff():
    result = ingest_agent_run_artifact(_artifact())
    assert result.patch_summary is None
    assert isinstance(result.preliminary_evidence, TaskEvidence)


def test_ingest_invalid_artifact_raises_ingestion_error():
    artifact = _artifact(agent_name="")
    with pytest.raises(AgentRunIngestionError, match="agent_name"):
        ingest_agent_run_artifact(artifact)


def test_ingest_invalid_metadata_raises_ingestion_error():
    artifact = _artifact()
    artifact.metadata = {"k": 123}  # type: ignore[dict-item]
    with pytest.raises(AgentRunIngestionError, match="metadata"):
        ingest_agent_run_artifact(artifact)


# ---- ingest_agent_run_artifacts --------------------------------------------


def test_ingest_batch_preserves_input_order():
    artifacts = [
        _artifact(task_id="t1", run_id="r1"),
        _artifact(task_id="t2", run_id="r2"),
        _artifact(task_id="t3", run_id="r3"),
    ]
    results = ingest_agent_run_artifacts(artifacts)
    assert [r.artifact.task_id for r in results] == ["t1", "t2", "t3"]
    assert [r.artifact.run_id for r in results] == ["r1", "r2", "r3"]


def test_ingest_batch_raises_with_run_id_context_on_failure():
    artifacts = [
        _artifact(task_id="t1", run_id="good-1"),
        _artifact(task_id="t2", run_id="bad-1", agent_name=""),
        _artifact(task_id="t3", run_id="good-2"),
    ]
    with pytest.raises(AgentRunIngestionError, match="bad-1"):
        ingest_agent_run_artifacts(artifacts)


def test_ingest_batch_rejects_non_list():
    with pytest.raises(AgentRunIngestionError, match="list"):
        ingest_agent_run_artifacts(_artifact())  # type: ignore[arg-type]


def test_ingest_batch_empty_returns_empty_list():
    assert ingest_agent_run_artifacts([]) == []


def test_ingest_batch_does_not_mutate_inputs():
    artifact = _artifact(
        diff_text=VALID_DIFF,
        claimed_commands=["pytest"],
        metadata={"k": "v"},
    )
    snapshot_commands = list(artifact.claimed_commands)
    snapshot_metadata = dict(artifact.metadata)
    ingest_agent_run_artifacts([artifact])
    assert artifact.diff_text == VALID_DIFF
    assert artifact.claimed_commands == snapshot_commands
    assert artifact.metadata == snapshot_metadata
