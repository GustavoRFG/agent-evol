"""The AgentEval Forge -> EvoForge external evaluation report contract.

This module is the single source of truth, *inside AgentEval Forge*, for the
shape of the report that EvoForge's ``attach-agenteval`` command consumes. It
mirrors EvoForge's ``schemas/agenteval_forge_evaluation_schema.json`` (version
``0.1``) without importing any EvoForge code: the two repositories stay
independent and are connected only by this explicit, versioned contract.

If EvoForge ever bumps its accepted schema version, the mismatch surfaces here
(and in the controlled compatibility validation) rather than silently producing
reports EvoForge rejects.

Standard library only.
"""

from __future__ import annotations

import re
from typing import Any

EVALUATION_SCHEMA_VERSION = "0.1"
SOURCE_SYSTEM = "AgentEval Forge"

ALLOWED_VERDICTS: frozenset[str] = frozenset({"pass", "fail", "needs_review"})
ALLOWED_CHECK_STATUSES: frozenset[str] = frozenset(
    {"pass", "fail", "warning", "unknown"}
)
SCORE_FIELDS: tuple[str, ...] = (
    "correctness",
    "safety",
    "minimality",
    "evidence_quality",
    "overall",
)

# EvoForge records sha256 digests as ``sha256:<64 lowercase hex chars>``.
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class EvoForgeContractError(ValueError):
    """Raised when a report does not satisfy the EvoForge external contract."""


def _require_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvoForgeContractError(f"field must be non-empty text: {key}")
    return value


def _require_object(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise EvoForgeContractError(f"field must be an object: {key}")
    return value


def _require_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise EvoForgeContractError(f"field must be a list: {key}")
    return value


def _require_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = _require_list(data, key)
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise EvoForgeContractError(f"{key}[{index}] must be a string")
    return value


def _validate_scores(scores: dict[str, Any]) -> None:
    for name in SCORE_FIELDS:
        value = scores.get(name)
        # bool is a subclass of int; a boolean score is never valid.
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise EvoForgeContractError(f"score must be numeric: {name}")
        if value < 0.0 or value > 1.0:
            raise EvoForgeContractError(f"score out of range [0.0, 1.0]: {name}")


def _validate_checks(checks: list[Any]) -> None:
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise EvoForgeContractError(f"check must be an object: checks[{index}]")
        _require_text(check, "id")
        status = check.get("status")
        if status not in ALLOWED_CHECK_STATUSES:
            raise EvoForgeContractError(
                f"unsupported check status: {status!r} (checks[{index}])"
            )
        if not isinstance(check.get("message"), str):
            raise EvoForgeContractError(
                f"check message must be a string: checks[{index}]"
            )


def _validate_artifact_hashes(hashes: dict[str, Any]) -> None:
    for name, digest in hashes.items():
        if not isinstance(name, str) or not name.strip():
            raise EvoForgeContractError("artifact hash names must be non-empty text")
        if not isinstance(digest, str) or not SHA256_PATTERN.match(digest):
            raise EvoForgeContractError(f"invalid artifact hash for {name!r}: {digest!r}")


def validate_evaluation_report(report: dict[str, Any]) -> None:
    """Validate ``report`` against the EvoForge external evaluation contract.

    This performs the same structural checks EvoForge's adapter performs, so a
    report that passes here is one EvoForge will accept (subject to the run /
    trace / artifact-hash binding EvoForge verifies against its own episode).

    Raises:
        EvoForgeContractError: If any field is missing or malformed.
    """
    if not isinstance(report, dict):
        raise EvoForgeContractError("report must be a JSON object")

    if report.get("evaluation_schema_version") != EVALUATION_SCHEMA_VERSION:
        raise EvoForgeContractError(
            "unsupported evaluation_schema_version: "
            f"{report.get('evaluation_schema_version')!r} "
            f"(expected {EVALUATION_SCHEMA_VERSION!r})"
        )
    if report.get("source_system") != SOURCE_SYSTEM:
        raise EvoForgeContractError(
            f"unsupported source_system: {report.get('source_system')!r}"
        )

    _require_text(report, "source_evaluation_id")
    _require_text(report, "evaluated_at")

    if report.get("verdict") not in ALLOWED_VERDICTS:
        raise EvoForgeContractError(f"unsupported verdict: {report.get('verdict')!r}")
    if not isinstance(report.get("requires_human_review"), bool):
        raise EvoForgeContractError("requires_human_review must be a boolean")

    evaluator = _require_object(report, "evaluator")
    _require_text(evaluator, "name")
    _require_text(evaluator, "version")
    _require_text(evaluator, "policy_version")

    subject = _require_object(report, "subject")
    _require_text(subject, "evoforge_run_id")
    _require_text(subject, "trace_id")
    _validate_artifact_hashes(_require_object(subject, "artifact_hashes"))

    _validate_scores(_require_object(report, "scores"))
    _validate_checks(_require_list(report, "checks"))
    _require_string_list(report, "rejection_reasons")
    _require_string_list(report, "warnings")
