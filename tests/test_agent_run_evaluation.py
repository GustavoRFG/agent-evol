"""Tests for the IngestedAgentRun -> EvaluationResult bridge."""

import pytest

from agenteval.agent_runs import (
    AgentRunArtifact,
    AgentRunEvaluationError,
    IngestedAgentRun,
    build_evaluation_result_from_ingested_run,
    build_evaluation_results_from_agent_artifacts,
    build_evaluation_results_from_ingested_runs,
    ingest_agent_run_artifact,
)
from agenteval.core.schemas import EvaluationResult, TaskSpec, WeaknessCode

VALID_DIFF = """diff --git a/sum_range.py b/sum_range.py
index abc1234..def5678 100644
--- a/sum_range.py
+++ b/sum_range.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end))
+    return sum(range(start, end + 1))
"""


def _task(task_id: str = "bugfix-001", title: str = "Fix sum_range") -> TaskSpec:
    return TaskSpec(task_id=task_id, title=title)


def _artifact(**overrides) -> AgentRunArtifact:
    defaults = {
        "agent_name": "claude-code",
        "task_id": "bugfix-001",
        "run_id": "claude-code:bugfix-001:001",
    }
    defaults.update(overrides)
    return AgentRunArtifact(**defaults)


# ---- build_evaluation_result_from_ingested_run -----------------------------


def test_one_ingested_artifact_produces_evaluation_result():
    artifact = _artifact(diff_text=VALID_DIFF, final_message="done")
    ingested = ingest_agent_run_artifact(artifact)

    result = build_evaluation_result_from_ingested_run(_task(), ingested)

    assert isinstance(result, EvaluationResult)
    assert result.task_id == "bugfix-001"
    assert result.run_id == "claude-code:bugfix-001:001"


def test_task_id_mismatch_raises():
    ingested = ingest_agent_run_artifact(_artifact(task_id="bugfix-001"))
    other_task = _task(task_id="bugfix-002", title="Other")

    with pytest.raises(AgentRunEvaluationError, match="task_id mismatch"):
        build_evaluation_result_from_ingested_run(other_task, ingested)


def test_missing_preliminary_evidence_raises():
    artifact = _artifact()
    ingested = IngestedAgentRun(
        artifact=artifact, patch_summary=None, preliminary_evidence=None
    )

    with pytest.raises(AgentRunEvaluationError, match="preliminary evidence"):
        build_evaluation_result_from_ingested_run(_task(), ingested)


def test_non_ingested_input_raises():
    with pytest.raises(AgentRunEvaluationError, match="IngestedAgentRun"):
        build_evaluation_result_from_ingested_run(
            _task(), "not an ingested run"  # type: ignore[arg-type]
        )


def test_result_keeps_public_tests_not_passed():
    ingested = ingest_agent_run_artifact(_artifact())
    result = build_evaluation_result_from_ingested_run(_task(), ingested)
    assert result.passed_public_tests is False


def test_result_keeps_hidden_tests_not_passed():
    ingested = ingest_agent_run_artifact(_artifact())
    result = build_evaluation_result_from_ingested_run(_task(), ingested)
    assert result.passed_hidden_tests is False


def test_result_includes_verify_weakness():
    ingested = ingest_agent_run_artifact(_artifact())
    result = build_evaluation_result_from_ingested_run(_task(), ingested)
    assert WeaknessCode.VERIFY in result.weaknesses


def test_result_preserves_preliminary_rationale():
    artifact = _artifact(claimed_public_tests_passed=True)
    ingested = ingest_agent_run_artifact(artifact)
    result = build_evaluation_result_from_ingested_run(_task(), ingested)

    assert "AgentEval Forge" in result.rationale
    assert "not executed" in result.rationale
    assert "agent claimed public tests passed" in result.rationale


def test_result_includes_patch_summary_when_diff_present():
    artifact = _artifact(diff_text=VALID_DIFF)
    ingested = ingest_agent_run_artifact(artifact)

    result = build_evaluation_result_from_ingested_run(_task(), ingested)

    assert result.patch_summary is not None
    assert result.patch_summary.changed_files == ["sum_range.py"]
    assert result.patch_summary.diff_text == VALID_DIFF


def test_result_has_no_patch_summary_when_diff_absent():
    ingested = ingest_agent_run_artifact(_artifact())
    result = build_evaluation_result_from_ingested_run(_task(), ingested)
    assert result.patch_summary is None


def test_claimed_public_tests_true_does_not_verify_public_tests():
    artifact = _artifact(claimed_public_tests_passed=True)
    ingested = ingest_agent_run_artifact(artifact)
    result = build_evaluation_result_from_ingested_run(_task(), ingested)

    assert result.passed_public_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert result.score == 0.0


def test_claimed_hidden_tests_true_does_not_verify_hidden_tests():
    artifact = _artifact(claimed_hidden_tests_passed=True)
    ingested = ingest_agent_run_artifact(artifact)
    result = build_evaluation_result_from_ingested_run(_task(), ingested)

    assert result.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert result.score == 0.0


def test_score_is_zero_for_unverified_result():
    ingested = ingest_agent_run_artifact(_artifact(diff_text=VALID_DIFF))
    result = build_evaluation_result_from_ingested_run(_task(), ingested)
    assert result.score == 0.0


def test_handbuilt_ingested_without_verify_still_yields_verify():
    # Defensive: a caller could hand-build an IngestedAgentRun whose evidence
    # lost the VERIFY weakness. The bridge must restore it rather than emit a
    # falsely-verified result.
    from agenteval.evaluation.batch_builder import TaskEvidence

    artifact = _artifact()
    ingested = IngestedAgentRun(
        artifact=artifact,
        patch_summary=None,
        preliminary_evidence=TaskEvidence(
            passed_public_tests=False,
            passed_hidden_tests=False,
            weaknesses=[],
            rationale="hand-built",
        ),
    )
    result = build_evaluation_result_from_ingested_run(_task(), ingested)
    assert WeaknessCode.VERIFY in result.weaknesses


def test_does_not_mutate_inputs():
    artifact = _artifact(
        diff_text=VALID_DIFF,
        claimed_commands=["pytest"],
        metadata={"k": "v"},
    )
    ingested = ingest_agent_run_artifact(artifact)
    snapshot_commands = list(artifact.claimed_commands)
    snapshot_metadata = dict(artifact.metadata)
    snapshot_evidence_weaknesses = list(ingested.preliminary_evidence.weaknesses)

    build_evaluation_result_from_ingested_run(_task(), ingested)

    assert artifact.claimed_commands == snapshot_commands
    assert artifact.metadata == snapshot_metadata
    assert (
        list(ingested.preliminary_evidence.weaknesses)
        == snapshot_evidence_weaknesses
    )


# ---- build_evaluation_results_from_ingested_runs ---------------------------


def test_batch_preserves_input_order():
    tasks = {f"t{i}": _task(task_id=f"t{i}") for i in (1, 2, 3)}
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(task_id=f"t{i}", run_id=f"r{i}"))
        for i in (3, 1, 2)
    ]

    results = build_evaluation_results_from_ingested_runs(tasks, ingested_runs)

    assert [r.task_id for r in results] == ["t3", "t1", "t2"]
    assert [r.run_id for r in results] == ["r3", "r1", "r2"]


def test_batch_missing_task_raises_with_context():
    tasks = {"t1": _task(task_id="t1")}
    ingested_runs = [
        ingest_agent_run_artifact(_artifact(task_id="t1", run_id="r1")),
        ingest_agent_run_artifact(_artifact(task_id="t99", run_id="r99")),
    ]

    with pytest.raises(AgentRunEvaluationError, match="t99"):
        build_evaluation_results_from_ingested_runs(tasks, ingested_runs)


def test_batch_rejects_non_dict_tasks():
    with pytest.raises(AgentRunEvaluationError, match="tasks_by_id"):
        build_evaluation_results_from_ingested_runs(
            [("t1", _task())], []  # type: ignore[arg-type]
        )


def test_batch_rejects_non_list_runs():
    with pytest.raises(AgentRunEvaluationError, match="ingested_runs"):
        build_evaluation_results_from_ingested_runs(
            {"t1": _task()},
            ingest_agent_run_artifact(_artifact()),  # type: ignore[arg-type]
        )


def test_batch_empty_returns_empty_list():
    assert build_evaluation_results_from_ingested_runs({"t1": _task()}, []) == []


# ---- build_evaluation_results_from_agent_artifacts -------------------------


def test_convenience_helper_from_artifacts_works():
    tasks = {f"t{i}": _task(task_id=f"t{i}") for i in (1, 2)}
    artifacts = [
        _artifact(task_id="t1", run_id="r1", diff_text=VALID_DIFF),
        _artifact(task_id="t2", run_id="r2"),
    ]

    results = build_evaluation_results_from_agent_artifacts(tasks, artifacts)

    assert len(results) == 2
    assert [r.task_id for r in results] == ["t1", "t2"]
    assert all(WeaknessCode.VERIFY in r.weaknesses for r in results)
    assert all(r.passed_public_tests is False for r in results)
    assert all(r.passed_hidden_tests is False for r in results)
    assert results[0].patch_summary is not None
    assert results[0].patch_summary.changed_files == ["sum_range.py"]
    assert results[1].patch_summary is None


def test_convenience_helper_rejects_non_list_artifacts():
    with pytest.raises(AgentRunEvaluationError, match="artifacts"):
        build_evaluation_results_from_agent_artifacts(
            {"t1": _task()}, _artifact()  # type: ignore[arg-type]
        )


def test_convenience_helper_wraps_ingestion_failure_with_run_id():
    tasks = {"t1": _task(task_id="t1")}
    bad_artifact = _artifact(task_id="t1", run_id="bad-run", agent_name="")

    with pytest.raises(AgentRunEvaluationError, match="bad-run"):
        build_evaluation_results_from_agent_artifacts(tasks, [bad_artifact])
