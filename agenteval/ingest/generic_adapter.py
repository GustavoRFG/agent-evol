"""Generic V1 evidence-review adapter.

This module accepts an agent-agnostic JSON-like dict, validates the public V1
contract, and maps it into AgentEval Forge's existing internal model. It does
not apply patches, execute commands, run tests, touch client workspaces, or make
network calls. Caller-supplied claims remain claims only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.evaluation import (
    build_evaluation_result_from_ingested_run,
)
from agenteval.agent_runs.ingestion import (
    IngestedAgentRun,
    ingest_agent_run_artifact,
)
from agenteval.core.scoring import clamp_score
from agenteval.core.schemas import (
    AgentRun,
    EvaluationResult,
    PatchSummary,
    TaskSpec,
)

GENERIC_SCHEMA_VERSION = "1.0"
PATCH_FORMAT_UNIFIED_DIFF = "unified_diff"

EVIDENCE_LEVEL_PATCH_ONLY = "patch_only_review"
EVIDENCE_LEVEL_SELF_REPORTED = "self_reported_execution_evidence"
EVIDENCE_LEVEL_HASH_BOUND = "hash_bound_evidence_review"
EVIDENCE_LEVEL_VERIFIED_RESERVED = "independently_verified_execution"

MODE_EVIDENCE_REVIEW = "evidence_review"

VERDICT_REVIEW_ONLY = "review_only"
VERDICT_REQUIRES_REVIEW = "requires_review"
VERDICT_LOOKS_CONSISTENT = "looks_consistent"
VERDICT_INCONSISTENT = "inconsistent"


class GenericAgentRunAdapterError(ValueError):
    """Raised when a generic V1 evidence package is invalid."""


@dataclass
class IntegrityStatus:
    """Integrity-manifest verification result."""

    supplied: bool = False
    verified: bool = False
    findings: list[dict[str, str]] | None = None


@dataclass
class GenericAgentRunNormalization:
    """Canonical internal objects produced from a generic evidence package."""

    task: TaskSpec
    agent_run: AgentRun
    artifact: AgentRunArtifact
    ingested: IngestedAgentRun
    patch_summary: PatchSummary
    evaluation_result: EvaluationResult
    evidence_level: str
    integrity: IntegrityStatus


def evaluate_generic_agent_run(data: dict[str, Any]) -> dict[str, Any]:
    """Validate, normalize, and evaluate a generic V1 evidence package."""
    return GenericAgentRunAdapter().evaluate(data)


class GenericAgentRunAdapter:
    """Adapter for the generic AgentEval Forge V1 evidence-review contract."""

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and return ``data`` unchanged when it satisfies V1."""
        if not isinstance(data, dict):
            raise GenericAgentRunAdapterError(
                f"generic evidence package must be an object, got "
                f"{type(data).__name__}"
            )

        schema_version = data.get("schema_version")
        if schema_version != GENERIC_SCHEMA_VERSION:
            raise GenericAgentRunAdapterError(
                "schema_version must be '1.0'"
            )

        _required_non_empty_string(data, "run_id")

        task = _required_object(data, "task")
        _required_non_empty_string(task, "prompt", path="task.prompt")
        _optional_string(task, "task_id", path="task.task_id")

        patch = _required_object(data, "patch")
        patch_format = patch.get("format")
        if patch_format != PATCH_FORMAT_UNIFIED_DIFF:
            raise GenericAgentRunAdapterError(
                "patch.format must be 'unified_diff' in schema_version 1.0"
            )
        _required_non_empty_string(patch, "text", path="patch.text")

        _optional_object(data, "producer")
        _optional_object(data, "claims")
        _optional_object(data, "test_evidence")
        _optional_object(data, "trace")
        _optional_object(data, "integrity")
        _optional_object(data, "metadata")

        producer = data.get("producer")
        if isinstance(producer, dict):
            _optional_string(producer, "agent_name", path="producer.agent_name")
            _optional_string(producer, "model", path="producer.model")

        claims = data.get("claims")
        if isinstance(claims, dict):
            _optional_bool_or_none(
                claims,
                "public_tests_passed",
                path="claims.public_tests_passed",
            )
            _optional_bool_or_none(
                claims,
                "hidden_tests_passed",
                path="claims.hidden_tests_passed",
            )
            _optional_bool_or_none(
                claims,
                "all_tests_passed",
                path="claims.all_tests_passed",
            )
            _optional_string(claims, "summary", path="claims.summary")

        test_evidence = data.get("test_evidence")
        if isinstance(test_evidence, dict):
            _optional_string(
                test_evidence, "framework", path="test_evidence.framework"
            )
            _optional_string(
                test_evidence, "command", path="test_evidence.command"
            )
            _optional_int(test_evidence, "exit_code", path="test_evidence.exit_code")
            _optional_string(
                test_evidence, "summary", path="test_evidence.summary"
            )
            _optional_string(test_evidence, "stdout", path="test_evidence.stdout")
            _optional_string(test_evidence, "stderr", path="test_evidence.stderr")

        trace = data.get("trace")
        if isinstance(trace, dict):
            commands = trace.get("commands")
            if commands is not None:
                if not isinstance(commands, list):
                    raise GenericAgentRunAdapterError(
                        "trace.commands must be a list of strings"
                    )
                for index, command in enumerate(commands):
                    if not isinstance(command, str):
                        raise GenericAgentRunAdapterError(
                            f"trace.commands[{index}] must be a string"
                        )
            _optional_string(trace, "final_message", path="trace.final_message")

        integrity = data.get("integrity")
        if isinstance(integrity, dict):
            _optional_string(integrity, "algorithm", path="integrity.algorithm")
            _optional_string(
                integrity, "patch_sha256", path="integrity.patch_sha256"
            )
            _optional_string(
                integrity,
                "test_evidence_sha256",
                path="integrity.test_evidence_sha256",
            )
            _optional_string(
                integrity, "bundle_sha256", path="integrity.bundle_sha256"
            )

        return data

    def normalize(self, data: dict[str, Any]) -> GenericAgentRunNormalization:
        """Map a valid generic package into canonical AgentEval Forge objects."""
        data = self.validate(data)
        integrity = _verify_integrity(data)
        evidence_level = _classify_evidence_level(data, integrity)

        task_data = data["task"]
        task_id = _task_id(task_data, data["run_id"])
        prompt = task_data["prompt"]
        producer = data.get("producer") if isinstance(data.get("producer"), dict) else {}
        trace = data.get("trace") if isinstance(data.get("trace"), dict) else {}
        claims = data.get("claims") if isinstance(data.get("claims"), dict) else {}

        agent_name = _string_or_default(producer.get("agent_name"), "generic-agent")
        final_message = _string_or_default(trace.get("final_message"), "")
        commands = list(trace.get("commands", [])) if isinstance(trace, dict) else []
        metadata = _metadata_strings(data)

        task = TaskSpec(
            task_id=task_id,
            title=_title_from_prompt(prompt),
            description=prompt,
        )
        artifact = AgentRunArtifact(
            agent_name=agent_name,
            task_id=task_id,
            run_id=data["run_id"],
            diff_text=data["patch"]["text"],
            final_message=final_message,
            transcript_text=_trace_text(commands, final_message),
            claimed_commands=commands,
            claimed_public_tests_passed=claims.get("public_tests_passed"),
            claimed_hidden_tests_passed=claims.get("hidden_tests_passed"),
            metadata=metadata,
        )
        ingested = ingest_agent_run_artifact(artifact)
        evaluation_result = build_evaluation_result_from_ingested_run(
            task, ingested
        )
        agent_run = AgentRun(
            run_id=artifact.run_id,
            agent_name=artifact.agent_name,
            task_id=artifact.task_id,
            final_message=artifact.final_message,
            commands_run=list(artifact.claimed_commands),
        )
        patch_summary = ingested.patch_summary or PatchSummary(
            diff_text=artifact.diff_text
        )

        return GenericAgentRunNormalization(
            task=task,
            agent_run=agent_run,
            artifact=artifact,
            ingested=ingested,
            patch_summary=patch_summary,
            evaluation_result=evaluation_result,
            evidence_level=evidence_level,
            integrity=integrity,
        )

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return a structured Mode A evidence-review verdict."""
        normalized = self.normalize(data)
        findings = _findings_for(data, normalized)
        verdict = _verdict_for(normalized, findings)
        claims_summary = _claims_summary(data)

        return {
            "evaluation_id": _evaluation_id(data["run_id"]),
            "mode": MODE_EVIDENCE_REVIEW,
            "evidence_level": normalized.evidence_level,
            "verdict": verdict,
            "scores": _scores_for(data, normalized),
            "findings": findings,
            "claims": claims_summary,
            "integrity": {
                "hash_manifest_supplied": normalized.integrity.supplied,
                "hashes_verified": normalized.integrity.verified,
            },
            "human_review": _human_review(verdict, findings, normalized),
        }


def _required_object(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise GenericAgentRunAdapterError(f"{key} must be an object")
    return value


def _optional_object(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if value is not None and not isinstance(value, dict):
        raise GenericAgentRunAdapterError(f"{key} must be an object when present")


def _required_non_empty_string(
    data: dict[str, Any], key: str, *, path: str | None = None
) -> None:
    label = path or key
    value = data.get(key)
    if not isinstance(value, str):
        raise GenericAgentRunAdapterError(f"{label} must be a string")
    if not value.strip():
        raise GenericAgentRunAdapterError(f"{label} must be non-empty")


def _optional_string(
    data: dict[str, Any], key: str, *, path: str | None = None
) -> None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise GenericAgentRunAdapterError(
            f"{path or key} must be a string when present"
        )


def _optional_bool_or_none(
    data: dict[str, Any], key: str, *, path: str | None = None
) -> None:
    value = data.get(key)
    if value is not None and not isinstance(value, bool):
        raise GenericAgentRunAdapterError(
            f"{path or key} must be true, false, or null when present"
        )


def _optional_int(data: dict[str, Any], key: str, *, path: str | None = None) -> None:
    value = data.get(key)
    if value is not None and not isinstance(value, int):
        raise GenericAgentRunAdapterError(
            f"{path or key} must be an integer when present"
        )


def _task_id(task_data: dict[str, Any], run_id: str) -> str:
    task_id = task_data.get("task_id")
    if isinstance(task_id, str) and task_id.strip():
        return task_id
    return f"{run_id}:task"


def _title_from_prompt(prompt: str) -> str:
    first_line = prompt.strip().splitlines()[0]
    if len(first_line) <= 80:
        return first_line
    return first_line[:77] + "..."


def _string_or_default(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return default


def _trace_text(commands: list[str], final_message: str) -> str:
    parts: list[str] = []
    if commands:
        parts.append("Commands:\n" + "\n".join(commands))
    if final_message:
        parts.append("Final message:\n" + final_message)
    return "\n\n".join(parts)


def _metadata_strings(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    producer = data.get("producer")
    if isinstance(producer, dict):
        for key in ("model",):
            value = producer.get(key)
            if isinstance(value, str):
                out[key] = value
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
                out[key] = str(value)
    return out


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _normalize_digest(value: str) -> str:
    value = value.strip()
    if value.startswith("sha256:"):
        return value.lower()
    return "sha256:" + value.lower()


def _verify_integrity(data: dict[str, Any]) -> IntegrityStatus:
    integrity = data.get("integrity")
    if not isinstance(integrity, dict):
        return IntegrityStatus(supplied=False, verified=False, findings=[])

    findings: list[dict[str, str]] = []
    algorithm = integrity.get("algorithm")
    if algorithm != "sha256":
        findings.append(
            _finding(
                "warning",
                "UNSUPPORTED_INTEGRITY_ALGORITHM",
                "Only sha256 integrity manifests can be verified in V1.",
            )
        )
        return IntegrityStatus(supplied=True, verified=False, findings=findings)

    patch_digest = integrity.get("patch_sha256")
    if not isinstance(patch_digest, str) or not patch_digest.strip():
        findings.append(
            _finding(
                "warning",
                "INTEGRITY_MANIFEST_INCOMPLETE",
                "A sha256 integrity manifest must include patch_sha256.",
            )
        )
        return IntegrityStatus(supplied=True, verified=False, findings=findings)

    expected_patch = _sha256_text(data["patch"]["text"])
    if _normalize_digest(patch_digest) != expected_patch:
        findings.append(
            _finding(
                "error",
                "INTEGRITY_HASH_MISMATCH",
                "patch_sha256 does not match patch.text.",
            )
        )

    test_digest = integrity.get("test_evidence_sha256")
    if isinstance(test_digest, str) and test_digest.strip():
        test_evidence = data.get("test_evidence")
        if not isinstance(test_evidence, dict):
            findings.append(
                _finding(
                    "error",
                    "INTEGRITY_HASH_MISMATCH",
                    "test_evidence_sha256 was supplied but test_evidence is absent.",
                )
            )
        elif _normalize_digest(test_digest) != _sha256_json(test_evidence):
            findings.append(
                _finding(
                    "error",
                    "INTEGRITY_HASH_MISMATCH",
                    "test_evidence_sha256 does not match test_evidence.",
                )
            )

    bundle_digest = integrity.get("bundle_sha256")
    if isinstance(bundle_digest, str) and bundle_digest.strip():
        bundle_payload = dict(data)
        bundle_payload.pop("integrity", None)
        if _normalize_digest(bundle_digest) != _sha256_json(bundle_payload):
            findings.append(
                _finding(
                    "error",
                    "INTEGRITY_HASH_MISMATCH",
                    "bundle_sha256 does not match the evidence package.",
                )
            )

    return IntegrityStatus(
        supplied=True,
        verified=not any(f["code"] == "INTEGRITY_HASH_MISMATCH" for f in findings),
        findings=findings,
    )


def _classify_evidence_level(
    data: dict[str, Any], integrity: IntegrityStatus
) -> str:
    if integrity.supplied and integrity.verified:
        return EVIDENCE_LEVEL_HASH_BOUND
    if isinstance(data.get("claims"), dict) or isinstance(data.get("test_evidence"), dict):
        return EVIDENCE_LEVEL_SELF_REPORTED
    return EVIDENCE_LEVEL_PATCH_ONLY


def _finding(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _findings_for(
    data: dict[str, Any], normalized: GenericAgentRunNormalization
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if normalized.integrity.findings:
        findings.extend(normalized.integrity.findings)

    if normalized.evidence_level == EVIDENCE_LEVEL_PATCH_ONLY:
        findings.append(
            _finding(
                "info",
                "PATCH_ONLY_REVIEW",
                "Only task and patch evidence were supplied; execution was not reviewed.",
            )
        )
    else:
        findings.append(
            _finding(
                "warning",
                "EXECUTION_NOT_INDEPENDENTLY_VERIFIED",
                "Execution evidence was supplied by the caller and was not reproduced by AgentEval Forge.",
            )
        )

    if normalized.evidence_level == EVIDENCE_LEVEL_HASH_BOUND:
        findings.append(
            _finding(
                "info",
                "HASHES_PROVE_INTEGRITY_NOT_ORIGIN",
                "Hash binding proves the submitted package is internally consistent, not that the original execution was truthful.",
            )
        )

    if _claims_consistent_with_test_evidence(data) is False:
        findings.append(
            _finding(
                "warning",
                "CLAIM_EVIDENCE_INCONSISTENT",
                "Caller test claims are inconsistent with supplied test evidence.",
            )
        )

    risky = _safety_findings(data["patch"]["text"], data.get("trace"))
    findings.extend(risky)
    return findings


def _claims_summary(data: dict[str, Any]) -> dict[str, bool | None]:
    claims = data.get("claims")
    tests_claimed_passed = None
    if isinstance(claims, dict):
        tests_claimed_passed = (
            claims.get("all_tests_passed") is True
            or claims.get("public_tests_passed") is True
            or claims.get("hidden_tests_passed") is True
        )
    return {
        "tests_claimed_passed": tests_claimed_passed,
        "evidence_consistent_with_claim": _claims_consistent_with_test_evidence(data),
        "independently_verified": False,
    }


def _claims_consistent_with_test_evidence(data: dict[str, Any]) -> bool | None:
    claims = data.get("claims")
    test_evidence = data.get("test_evidence")
    if not isinstance(claims, dict) or not isinstance(test_evidence, dict):
        return None

    test_status = _test_evidence_status(test_evidence)
    if test_status == "unknown":
        return None

    claimed_all = claims.get("all_tests_passed")
    claimed_public = claims.get("public_tests_passed")
    if claimed_all is True or claimed_public is True:
        return test_status == "passed"
    if claimed_all is False or claimed_public is False:
        return test_status == "failed"
    return None


def _test_evidence_status(test_evidence: dict[str, Any]) -> str:
    exit_code = test_evidence.get("exit_code")
    summary = " ".join(
        str(test_evidence.get(key, ""))
        for key in ("summary", "stdout", "stderr")
    ).lower()
    if isinstance(exit_code, int):
        if exit_code != 0:
            return "failed"
        if "failed" not in summary and "error" not in summary:
            return "passed"
    if re.search(r"\b[1-9]\d*\s+failed\b|\bfailed\b|\berror", summary):
        return "failed"
    if re.search(r"\b[1-9]\d*\s+passed\b|\bpassed\b", summary):
        return "passed"
    return "unknown"


def _safety_findings(patch_text: str, trace: Any) -> list[dict[str, str]]:
    commands = ""
    if isinstance(trace, dict) and isinstance(trace.get("commands"), list):
        commands = "\n".join(c for c in trace["commands"] if isinstance(c, str))
    corpus = patch_text + "\n" + commands
    if re.search(r"(?i)(private key|api[_-]?key|password|secret)\s*[:=]", corpus):
        return [
            _finding(
                "warning",
                "POTENTIAL_SECRET_PATTERN",
                "Patch or commands contain a credential-like assignment pattern.",
            )
        ]
    if re.search(r"(?i)\brm\s+-rf\b|remove-item\b.*-recurse.*-force", corpus):
        return [
            _finding(
                "warning",
                "POTENTIAL_DESTRUCTIVE_COMMAND",
                "Trace commands include a destructive filesystem pattern.",
            )
        ]
    return []


def _verdict_for(
    normalized: GenericAgentRunNormalization,
    findings: list[dict[str, str]],
) -> str:
    if any(f["code"] == "INTEGRITY_HASH_MISMATCH" for f in findings):
        return VERDICT_INCONSISTENT
    if any(f["code"] == "CLAIM_EVIDENCE_INCONSISTENT" for f in findings):
        return VERDICT_INCONSISTENT
    if normalized.evidence_level == EVIDENCE_LEVEL_PATCH_ONLY:
        return VERDICT_REVIEW_ONLY
    if normalized.evidence_level == EVIDENCE_LEVEL_HASH_BOUND:
        return VERDICT_LOOKS_CONSISTENT
    return VERDICT_REQUIRES_REVIEW


def _scores_for(
    data: dict[str, Any], normalized: GenericAgentRunNormalization
) -> dict[str, float]:
    patch = normalized.patch_summary
    file_count = len(set(patch.changed_files + patch.added_files + patch.deleted_files))
    added, removed = _count_diff_lines(patch.diff_text)
    total = added + removed

    task_alignment = 0.7 if file_count > 0 else 0.55
    patch_minimality = _minimality_score(file_count, total)
    evidence_quality = {
        EVIDENCE_LEVEL_PATCH_ONLY: 0.35,
        EVIDENCE_LEVEL_SELF_REPORTED: 0.6,
        EVIDENCE_LEVEL_HASH_BOUND: 0.85,
    }[normalized.evidence_level]
    if normalized.integrity.supplied and not normalized.integrity.verified:
        evidence_quality = min(evidence_quality, 0.4)

    safety_signal = 0.88
    if _safety_findings(data["patch"]["text"], data.get("trace")):
        safety_signal = 0.55

    return {
        "task_alignment": round(clamp_score(task_alignment), 4),
        "patch_minimality": round(clamp_score(patch_minimality), 4),
        "evidence_quality": round(clamp_score(evidence_quality), 4),
        "safety_signal": round(clamp_score(safety_signal), 4),
    }


def _count_diff_lines(diff_text: str) -> tuple[int, int]:
    added = 0
    removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _minimality_score(file_count: int, changed_lines: int) -> float:
    if changed_lines <= 50 and file_count <= 3:
        return 0.91
    if changed_lines <= 150 and file_count <= 5:
        return 0.75
    if changed_lines <= 400 and file_count <= 10:
        return 0.55
    return 0.35


def _human_review(
    verdict: str,
    findings: list[dict[str, str]],
    normalized: GenericAgentRunNormalization,
) -> dict[str, Any]:
    reasons: list[str] = []
    if normalized.evidence_level != EVIDENCE_LEVEL_HASH_BOUND:
        reasons.append("Execution was not independently reproduced.")
    if verdict in {VERDICT_REVIEW_ONLY, VERDICT_REQUIRES_REVIEW}:
        reasons.append("Mode A evidence review cannot guarantee code correctness.")
    if any(f["severity"] in {"warning", "error"} for f in findings):
        reasons.extend(f["code"] for f in findings if f["severity"] in {"warning", "error"})
    return {
        "recommended": bool(reasons),
        "reasons": list(dict.fromkeys(reasons)),
    }


def _evaluation_id(run_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id.strip())
    return f"eval_{safe}"


__all__ = [
    "EVIDENCE_LEVEL_HASH_BOUND",
    "EVIDENCE_LEVEL_PATCH_ONLY",
    "EVIDENCE_LEVEL_SELF_REPORTED",
    "EVIDENCE_LEVEL_VERIFIED_RESERVED",
    "GenericAgentRunAdapter",
    "GenericAgentRunAdapterError",
    "GenericAgentRunNormalization",
    "evaluate_generic_agent_run",
]
