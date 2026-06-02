"""Export a native AgentEval Forge evaluation report for an EvoForge episode.

This is the public entry point for the V0.3.1 export hook. It loads and
fail-closed-verifies the episode, judges the grounded evidence independently,
assembles a report that satisfies the EvoForge external contract, validates it,
and writes it as UTF-8 JSON. EvoForge then attaches it manually with
``evoforge attach-agenteval``.

The exporter never writes inside the run directory, never executes
``commands.log``, never applies ``patch.diff``, and never reruns tests.
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agenteval import __version__
from agenteval.integrations.evoforge.contract import (
    EVALUATION_SCHEMA_VERSION,
    SOURCE_SYSTEM,
    validate_evaluation_report,
)
from agenteval.integrations.evoforge.episode_loader import (
    CORE_EVIDENCE_FILES,
    LoadedEpisode,
    load_evoforge_episode,
)
from agenteval.integrations.evoforge.evaluator import (
    POLICY_VERSION,
    EvidenceJudgment,
    judge_episode,
)

EVALUATOR_NAME = "AgentEval Forge"
DEFAULT_REPORT_FILENAME = "agenteval_forge_evaluation.json"


class EvoForgeExportError(ValueError):
    """Raised when a report cannot be exported (e.g. output conflict)."""


def _subject_artifact_hashes(loaded: LoadedEpisode) -> dict[str, str]:
    """The verified hashes for the core evidence files actually judged."""
    return {
        name: loaded.verified_hashes[name]
        for name in CORE_EVIDENCE_FILES
        if name in loaded.evidence_paths
    }


def _source_evaluation_id(
    loaded: LoadedEpisode, subject_hashes: dict[str, str]
) -> str:
    """Build a deterministic, evidence-bound source evaluation id.

    The digest binds the run id, trace id, and the verified evidence hashes, so
    the same immutable episode always yields the same id. A changed episode
    fails hash validation in the loader rather than silently reusing the id.
    """
    canonical = "|".join(
        [
            loaded.run_id,
            loaded.trace_id,
            *(f"{name}={subject_hashes[name]}" for name in sorted(subject_hashes)),
        ]
    )
    digest_prefix = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
    return f"agenteval-evoforge-{loaded.run_id}-{digest_prefix}"


def build_evaluation_report(
    loaded: LoadedEpisode,
    judgment: EvidenceJudgment,
    *,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the external evaluation report dict and validate it.

    Args:
        loaded: The verified, hash-bound episode.
        judgment: The independent evidence judgment.
        evaluated_at: ISO-8601 timestamp; defaults to the current UTC time.
            Inject a fixed value for deterministic, byte-identical exports.

    Returns:
        A report dict that satisfies the EvoForge external contract.
    """
    subject_hashes = _subject_artifact_hashes(loaded)
    report = {
        "evaluation_schema_version": EVALUATION_SCHEMA_VERSION,
        "source_system": SOURCE_SYSTEM,
        "source_evaluation_id": _source_evaluation_id(loaded, subject_hashes),
        "evaluated_at": evaluated_at
        or datetime.now(timezone.utc).isoformat(),
        "evaluator": {
            "name": EVALUATOR_NAME,
            "version": __version__,
            "policy_version": POLICY_VERSION,
        },
        "subject": {
            "evoforge_run_id": loaded.run_id,
            "trace_id": loaded.trace_id,
            "artifact_hashes": subject_hashes,
        },
        "verdict": judgment.verdict,
        "scores": dict(judgment.scores),
        "checks": [dict(check) for check in judgment.checks],
        "rejection_reasons": list(judgment.rejection_reasons),
        "warnings": list(judgment.warnings),
        "requires_human_review": judgment.requires_human_review,
    }
    validate_evaluation_report(report)
    return report


def _render(report: dict[str, Any]) -> bytes:
    """Render the report as stable UTF-8 JSON with a trailing newline."""
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    return (text + "\n").encode("utf-8")


def export_evoforge_evaluation(
    run_dir: Path | str,
    output_file: Path | str,
    *,
    overwrite: bool = False,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    """Export a native AgentEval Forge report for an EvoForge episode.

    Args:
        run_dir: EvoForge run directory containing ``episode.json``.
        output_file: Destination path for the report JSON (outside the run dir).
        overwrite: Replace an existing output file with differing bytes.
        evaluated_at: Optional fixed ISO timestamp for deterministic output.

    Returns:
        A summary dict: ``run_id``, ``trace_id``, ``source_evaluation_id``,
        ``output_path``, ``verdict``, ``scores``, ``warnings``,
        ``rejection_reasons``.

    Raises:
        EvoForgeEpisodeError: If the episode cannot be safely loaded/verified.
        EvoForgeContractError: If the assembled report violates the contract.
        EvoForgeExportError: If the output exists with differing bytes and
            ``overwrite`` is false, or the output path is unsafe.
    """
    loaded = load_evoforge_episode(run_dir)
    judgment = judge_episode(loaded)
    report = build_evaluation_report(loaded, judgment, evaluated_at=evaluated_at)
    payload = _render(report)

    output_path = Path(output_file).resolve()
    if output_path == loaded.run_dir or loaded.run_dir in output_path.parents:
        raise EvoForgeExportError(
            "refusing to write the report inside the EvoForge run directory"
        )
    if output_path.is_dir():
        raise EvoForgeExportError(f"output path is a directory: {output_file}")

    if output_path.exists():
        existing = output_path.read_bytes()
        if existing != payload and not overwrite:
            raise EvoForgeExportError(
                f"output already exists with different content: {output_file} "
                "(pass overwrite=True to replace it)"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)

    return {
        "run_id": loaded.run_id,
        "trace_id": loaded.trace_id,
        "source_evaluation_id": report["source_evaluation_id"],
        "output_path": output_path,
        "verdict": judgment.verdict,
        "scores": dict(judgment.scores),
        "warnings": list(judgment.warnings),
        "rejection_reasons": list(judgment.rejection_reasons),
        "requires_human_review": judgment.requires_human_review,
    }
