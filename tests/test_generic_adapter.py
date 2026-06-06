"""Tests for the generic V1 evidence-review adapter."""

from __future__ import annotations

import hashlib
import json

import pytest

from agenteval.core.schemas import WeaknessCode
from agenteval.ingest.generic_adapter import (
    EVIDENCE_LEVEL_HASH_BOUND,
    EVIDENCE_LEVEL_PATCH_ONLY,
    EVIDENCE_LEVEL_SELF_REPORTED,
    GenericAgentRunAdapter,
    GenericAgentRunAdapterError,
    evaluate_generic_agent_run,
)

VALID_DIFF = """diff --git a/range_check.py b/range_check.py
index 1234567..89abcde 100644
--- a/range_check.py
+++ b/range_check.py
@@ -1,2 +1,2 @@
 def is_within_range(value, start, end):
-    return start < value < end
+    return start <= value <= end
"""


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _request(**overrides):
    data = {
        "schema_version": "1.0",
        "run_id": "run_2026_06_06_001",
        "task": {
            "task_id": "range-validation-001",
            "prompt": "Fix the off-by-one bug in the range validation function.",
        },
        "patch": {
            "format": "unified_diff",
            "text": VALID_DIFF,
        },
    }
    data.update(overrides)
    return data


def test_valid_level_0_patch_only_review_never_claims_tests_passed():
    response = evaluate_generic_agent_run(_request())

    assert response["mode"] == "evidence_review"
    assert response["evidence_level"] == EVIDENCE_LEVEL_PATCH_ONLY
    assert response["verdict"] == "review_only"
    assert response["claims"]["tests_claimed_passed"] is None
    assert response["claims"]["independently_verified"] is False
    assert "verified_pass" not in json.dumps(response)


def test_valid_level_1_emits_execution_not_independently_verified_finding():
    response = evaluate_generic_agent_run(
        _request(
            claims={"public_tests_passed": True, "all_tests_passed": True},
            test_evidence={
                "framework": "pytest",
                "command": "python -m pytest",
                "exit_code": 0,
                "summary": "12 passed in 0.41s",
            },
        )
    )

    assert response["evidence_level"] == EVIDENCE_LEVEL_SELF_REPORTED
    assert response["verdict"] == "requires_review"
    assert response["claims"]["tests_claimed_passed"] is True
    assert response["claims"]["evidence_consistent_with_claim"] is True
    assert response["claims"]["independently_verified"] is False
    assert any(
        finding["code"] == "EXECUTION_NOT_INDEPENDENTLY_VERIFIED"
        for finding in response["findings"]
    )


def test_valid_level_2_integrity_manifest_that_verifies():
    data = _request()
    data["integrity"] = {
        "algorithm": "sha256",
        "patch_sha256": _sha256_text(VALID_DIFF),
    }

    response = evaluate_generic_agent_run(data)

    assert response["evidence_level"] == EVIDENCE_LEVEL_HASH_BOUND
    assert response["integrity"] == {
        "hash_manifest_supplied": True,
        "hashes_verified": True,
    }
    assert any(
        finding["code"] == "HASHES_PROVE_INTEGRITY_NOT_ORIGIN"
        for finding in response["findings"]
    )


def test_tampered_manifest_does_not_reach_level_2_and_is_flagged():
    response = evaluate_generic_agent_run(
        _request(
            claims={"public_tests_passed": True},
            integrity={
                "algorithm": "sha256",
                "patch_sha256": _sha256_text("different patch"),
            },
        )
    )

    assert response["evidence_level"] == EVIDENCE_LEVEL_SELF_REPORTED
    assert response["integrity"]["hash_manifest_supplied"] is True
    assert response["integrity"]["hashes_verified"] is False
    assert response["verdict"] == "inconsistent"
    assert any(
        finding["code"] == "INTEGRITY_HASH_MISMATCH"
        for finding in response["findings"]
    )


def test_patch_format_other_than_unified_diff_is_rejected():
    data = _request(patch={"format": "git_binary_patch", "text": VALID_DIFF})

    with pytest.raises(GenericAgentRunAdapterError, match="patch.format"):
        evaluate_generic_agent_run(data)


@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda data: data.pop("run_id"), "run_id"),
        (lambda data: data["task"].pop("prompt"), "task.prompt"),
        (lambda data: data["patch"].pop("text"), "patch.text"),
    ],
)
def test_missing_required_fields_are_rejected(mutator, match):
    data = _request()
    mutator(data)

    with pytest.raises(GenericAgentRunAdapterError, match=match):
        evaluate_generic_agent_run(data)


def test_caller_claims_are_never_promoted_to_verified_outcomes():
    adapter = GenericAgentRunAdapter()
    normalized = adapter.normalize(
        _request(
            claims={
                "public_tests_passed": True,
                "hidden_tests_passed": True,
                "all_tests_passed": True,
            },
            test_evidence={
                "framework": "pytest",
                "command": "python -m pytest",
                "exit_code": 0,
                "summary": "12 passed in 0.41s",
            },
        )
    )
    result = normalized.evaluation_result

    assert result.passed_public_tests is False
    assert result.passed_hidden_tests is False
    assert WeaknessCode.VERIFY in result.weaknesses
    assert result.score == 0.0


def test_generic_adapter_normalizes_to_existing_internal_model():
    normalized = GenericAgentRunAdapter().normalize(_request())

    assert normalized.task.task_id == "range-validation-001"
    assert normalized.agent_run.run_id == "run_2026_06_06_001"
    assert normalized.artifact.diff_text == VALID_DIFF
    assert normalized.patch_summary.changed_files == ["range_check.py"]
    assert normalized.evaluation_result.patch_summary is not None
