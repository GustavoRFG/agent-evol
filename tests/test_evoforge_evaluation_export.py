"""Tests for the native EvoForge evaluation export hook (V0.3.1).

Every test builds a self-contained, EvoForge-like episode in a temporary
directory with grounded evidence files and correct artifact hashes. Nothing
here touches the real EvoForge repository, executes commands, applies patches,
or reruns tests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agenteval import __version__
from agenteval.integrations.evoforge.contract import (
    EvoForgeContractError,
    validate_evaluation_report,
)
from agenteval.integrations.evoforge.episode_loader import (
    EvoForgeEpisodeError,
    load_evoforge_episode,
)
from agenteval.integrations.evoforge.evaluator import (
    evaluate_evoforge_episode,
    parse_test_outcome,
)
from agenteval.integrations.evoforge.exporter import (
    EvoForgeExportError,
    _render,
    export_evoforge_evaluation,
)

# --------------------------------------------------------------------------- #
# Test fixtures / helpers
# --------------------------------------------------------------------------- #

PASSING_PYTEST_LOG = "============== 1 passed in 0.01s ==============\n"
FAILING_PYTEST_LOG = "========== 1 failed, 0 passed in 0.02s ==========\n"
SAFE_COMMANDS = "echo building\npython -m pytest -q\n"
SMALL_PATCH = (
    "diff --git a/app.py b/app.py\n"
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1 +1 @@\n"
    '-    return "old"\n'
    '+    return "new"\n'
)
TASK_TEXT = "# Task\n\nFix the return value.\n"

RUN_ID = "2026-06-01_task_ea5a5302"
TRACE_ID = "83e922932fccd97f66f66a47"


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def make_episode(
    root: Path,
    *,
    files: dict[str, str | bytes] | None = None,
    run_id: str = RUN_ID,
    trace_id: str = TRACE_ID,
    include_source: bool = True,
    extra_hashes: dict[str, str] | None = None,
) -> Path:
    """Create an EvoForge-like run directory and return its path.

    ``files`` maps evidence filenames to content. Every written file is hashed
    into ``episode.json``'s ``artifact_hashes`` so the loader's fail-closed
    binding passes. ``extra_hashes`` injects raw hash entries (e.g. to test
    traversal or tampering) without writing a file.
    """
    if files is None:
        files = {
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
            "tests.log": PASSING_PYTEST_LOG,
        }
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifact_hashes: dict[str, str] = {}
    artifacts: dict[str, str] = {}
    for name, content in files.items():
        data = content.encode("utf-8") if isinstance(content, str) else content
        (run_dir / name).write_bytes(data)
        artifact_hashes[name] = _sha256(data)
        artifacts[name.replace(".", "_")] = name

    if extra_hashes:
        artifact_hashes.update(extra_hashes)

    episode: dict[str, object] = {
        "schema_version": "0.2.1",
        "run_id": run_id,
        "trace": {"trace_id": trace_id},
        "artifacts": artifacts,
        "artifact_hashes": artifact_hashes,
    }
    if include_source:
        episode["source"] = {
            "kind": "forgeagent_import",
            "source_system": "ForgeAgent",
            "source_run_id": "forgeagent-sample-001",
        }
    (run_dir / "episode.json").write_text(
        json.dumps(episode, indent=2), encoding="utf-8"
    )
    return run_dir


# --------------------------------------------------------------------------- #
# 1. Rich safe episode -> pass
# --------------------------------------------------------------------------- #


def test_export_rich_safe_episode_produces_pass_report(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    output = tmp_path / "out" / "report.json"

    result = export_evoforge_evaluation(run_dir, output)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert result["verdict"] == "pass"
    assert report["verdict"] == "pass"
    scores = report["scores"]
    assert scores["correctness"] >= 0.75
    assert scores["safety"] >= 0.75
    assert scores["minimality"] >= 0.50
    assert scores["evidence_quality"] >= 0.75
    assert scores["overall"] >= 0.75
    assert report["requires_human_review"] is False

    # subject hashes match the actual files on disk
    for name in ("task.md", "commands.log", "patch.diff", "tests.log"):
        actual = _sha256((run_dir / name).read_bytes())
        assert report["subject"]["artifact_hashes"][name] == actual

    # the report is contract-valid (i.e. EvoForge will accept its structure)
    validate_evaluation_report(report)
    assert report["evaluator"]["version"] == __version__


# --------------------------------------------------------------------------- #
# 2. Failed test evidence -> fail
# --------------------------------------------------------------------------- #


def test_failed_tests_produce_fail_verdict(tmp_path: Path):
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
            "tests.log": FAILING_PYTEST_LOG,
        },
    )
    output = tmp_path / "report.json"
    result = export_evoforge_evaluation(run_dir, output)

    assert result["verdict"] == "fail"
    assert any("tests_failed" in reason for reason in result["rejection_reasons"])


def test_failed_unittest_summary_is_detected(tmp_path: Path):
    log = "Ran 3 tests in 0.004s\n\nFAILED (failures=1)\n"
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
            "tests.log": log,
        },
    )
    result = export_evoforge_evaluation(run_dir, tmp_path / "r.json")
    assert result["verdict"] == "fail"


# --------------------------------------------------------------------------- #
# 3 & 4. Missing evidence -> needs_review
# --------------------------------------------------------------------------- #


def test_missing_patch_produces_needs_review(tmp_path: Path):
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "tests.log": PASSING_PYTEST_LOG,
        },
    )
    result = export_evoforge_evaluation(run_dir, tmp_path / "r.json")
    assert result["verdict"] == "needs_review"
    assert result["requires_human_review"] is True


def test_missing_tests_log_produces_needs_review(tmp_path: Path):
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
        },
    )
    result = export_evoforge_evaluation(run_dir, tmp_path / "r.json")
    assert result["verdict"] == "needs_review"
    assert result["requires_human_review"] is True


# --------------------------------------------------------------------------- #
# 5. Stale artifact -> fail closed before report generation
# --------------------------------------------------------------------------- #


def test_stale_hash_rejected_fail_closed(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    # Tamper with the evidence after the hash was recorded.
    (run_dir / "patch.diff").write_text("tampered\n", encoding="utf-8")

    output = tmp_path / "r.json"
    with pytest.raises(EvoForgeEpisodeError, match="mismatch"):
        export_evoforge_evaluation(run_dir, output)
    assert not output.exists()


def test_declared_artifact_missing_on_disk_is_rejected(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    (run_dir / "tests.log").unlink()
    with pytest.raises(EvoForgeEpisodeError, match="missing on disk"):
        export_evoforge_evaluation(run_dir, tmp_path / "r.json")


# --------------------------------------------------------------------------- #
# 6 & 7. Subject binding
# --------------------------------------------------------------------------- #


def test_report_binds_run_and_trace(tmp_path: Path):
    run_dir = make_episode(tmp_path, run_id="custom_run_42", trace_id="abc123trace")
    output = tmp_path / "r.json"
    export_evoforge_evaluation(run_dir, output)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["subject"]["evoforge_run_id"] == "custom_run_42"
    assert report["subject"]["trace_id"] == "abc123trace"


def test_report_binds_core_artifact_hashes(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    output = tmp_path / "r.json"
    export_evoforge_evaluation(run_dir, output)
    report = json.loads(output.read_text(encoding="utf-8"))
    hashes = report["subject"]["artifact_hashes"]
    assert set(hashes) == {"task.md", "commands.log", "patch.diff", "tests.log"}
    for name, digest in hashes.items():
        assert digest == _sha256((run_dir / name).read_bytes())


# --------------------------------------------------------------------------- #
# 8. Output conflict handling
# --------------------------------------------------------------------------- #


def test_export_refuses_different_existing_output_without_overwrite(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    output = tmp_path / "r.json"
    output.write_text("different prior content\n", encoding="utf-8")

    with pytest.raises(EvoForgeExportError, match="different content"):
        export_evoforge_evaluation(run_dir, output)

    # overwrite=True replaces it
    result = export_evoforge_evaluation(run_dir, output, overwrite=True)
    assert result["verdict"] == "pass"


def test_identical_output_is_idempotent(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    output = tmp_path / "r.json"
    fixed = "2026-06-01T18:00:00+00:00"
    export_evoforge_evaluation(run_dir, output, evaluated_at=fixed)
    first = output.read_bytes()
    # Re-export with identical (deterministic) bytes succeeds without overwrite.
    export_evoforge_evaluation(run_dir, output, evaluated_at=fixed)
    assert output.read_bytes() == first


def test_export_refuses_to_write_inside_run_dir(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    with pytest.raises(EvoForgeExportError, match="inside the EvoForge run directory"):
        export_evoforge_evaluation(run_dir, run_dir / "agenteval_forge_evaluation.json")


# --------------------------------------------------------------------------- #
# 9 & 10. Safety violations block pass (and secrets are redacted)
# --------------------------------------------------------------------------- #


def test_secret_like_content_blocks_pass_and_is_redacted(tmp_path: Path):
    secret = "AKIAIOSFODNN7EXAMPLE"
    patch = (
        "diff --git a/config.py b/config.py\n"
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -0,0 +1 @@\n"
        f'+AWS_ACCESS_KEY_ID = "{secret}"\n'
    )
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "patch.diff": patch,
            "tests.log": PASSING_PYTEST_LOG,
        },
    )
    output = tmp_path / "r.json"
    result = export_evoforge_evaluation(run_dir, output)

    assert result["verdict"] == "fail"
    raw = output.read_bytes()
    assert secret.encode("utf-8") not in raw  # raw secret never echoed
    report = json.loads(raw.decode("utf-8"))
    assert any(c["id"] == "patch_safety" and c["status"] == "fail" for c in report["checks"])


def test_destructive_command_blocks_pass(tmp_path: Path):
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": "echo start\nrm -rf /\n",
            "patch.diff": SMALL_PATCH,
            "tests.log": PASSING_PYTEST_LOG,
        },
    )
    result = export_evoforge_evaluation(run_dir, tmp_path / "r.json")
    assert result["verdict"] == "fail"
    assert any("safety_violation" in r for r in result["rejection_reasons"])


# --------------------------------------------------------------------------- #
# 11. Prose "passed" is not proof
# --------------------------------------------------------------------------- #


def test_passed_word_in_prose_is_not_test_success(tmp_path: Path):
    prose = "All tests passed successfully.\nexit code: 0\n0 failed\n"
    assert parse_test_outcome(prose)[0] == "unknown"
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
            "tests.log": prose,
        },
    )
    result = export_evoforge_evaluation(run_dir, tmp_path / "r.json")
    assert result["verdict"] == "needs_review"


# --------------------------------------------------------------------------- #
# 12. UTF-8 round-trip
# --------------------------------------------------------------------------- #


def test_utf8_portuguese_text_is_preserved(tmp_path: Path):
    pt_warning = "Rode o comando de validação específico."
    pt_message = "Não edite arquivos."
    report = {
        "warnings": [pt_warning],
        "checks": [{"id": "x", "status": "pass", "message": pt_message}],
    }
    payload = _render(report)
    # ensure_ascii=False: non-ASCII bytes are preserved, not \u-escaped.
    assert pt_warning.encode("utf-8") in payload
    assert pt_message.encode("utf-8") in payload
    assert json.loads(payload.decode("utf-8")) == report

    # And a real export over Portuguese evidence yields valid round-trippable UTF-8.
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": "# Tarefa\n\nNão edite arquivos. Validação específica.\n",
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
            "tests.log": PASSING_PYTEST_LOG,
        },
    )
    output = tmp_path / "r.json"
    export_evoforge_evaluation(run_dir, output)
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "pass"


# --------------------------------------------------------------------------- #
# 13. Path traversal rejected
# --------------------------------------------------------------------------- #


def test_episode_artifact_path_traversal_rejected(tmp_path: Path):
    run_dir = make_episode(
        tmp_path,
        extra_hashes={"../evil.txt": _sha256(b"x")},
    )
    with pytest.raises(EvoForgeEpisodeError, match="traversal"):
        load_evoforge_episode(run_dir)


def test_absolute_artifact_path_rejected(tmp_path: Path):
    abs_key = "C:\\Windows\\system32\\evil.txt" if Path("C:/").drive else "/etc/evil"
    run_dir = make_episode(tmp_path, extra_hashes={abs_key: _sha256(b"x")})
    with pytest.raises(EvoForgeEpisodeError):
        load_evoforge_episode(run_dir)


# --------------------------------------------------------------------------- #
# 14. Stable, evidence-bound source evaluation id
# --------------------------------------------------------------------------- #


def test_source_evaluation_id_is_stable(tmp_path: Path):
    run_dir = make_episode(tmp_path)
    out1 = tmp_path / "a.json"
    out2 = tmp_path / "b.json"
    id1 = export_evoforge_evaluation(run_dir, out1)["source_evaluation_id"]
    id2 = export_evoforge_evaluation(run_dir, out2)["source_evaluation_id"]
    assert id1 == id2
    assert id1.startswith(f"agenteval-evoforge-{RUN_ID}-")


def test_source_evaluation_id_changes_with_evidence(tmp_path: Path):
    run_a = make_episode(tmp_path / "a")
    run_b = make_episode(
        tmp_path / "b",
        files={
            "task.md": "# Different task\n",
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
            "tests.log": PASSING_PYTEST_LOG,
        },
    )
    id_a = export_evoforge_evaluation(run_a, tmp_path / "a.json")["source_evaluation_id"]
    id_b = export_evoforge_evaluation(run_b, tmp_path / "b.json")["source_evaluation_id"]
    assert id_a != id_b


# --------------------------------------------------------------------------- #
# Loader / evaluator / contract direct checks
# --------------------------------------------------------------------------- #


def test_evaluate_does_not_use_evoforge_local_verdict(tmp_path: Path):
    # EvoForge's local eval.json claims pass, but tests.log fails: our verdict
    # must follow the grounded evidence, not the local verdict.
    run_dir = make_episode(
        tmp_path,
        files={
            "task.md": TASK_TEXT,
            "commands.log": SAFE_COMMANDS,
            "patch.diff": SMALL_PATCH,
            "tests.log": FAILING_PYTEST_LOG,
            "eval.json": json.dumps({"score": 1.0, "tests_status": "passed"}),
        },
    )
    judgment = evaluate_evoforge_episode(run_dir)
    assert judgment.verdict == "fail"


def test_contract_rejects_out_of_range_score():
    report = {
        "evaluation_schema_version": "0.1",
        "source_system": "AgentEval Forge",
        "source_evaluation_id": "x",
        "evaluated_at": "t",
        "verdict": "pass",
        "requires_human_review": False,
        "evaluator": {"name": "a", "version": "b", "policy_version": "c"},
        "subject": {"evoforge_run_id": "r", "trace_id": "t", "artifact_hashes": {}},
        "scores": {
            "correctness": 1.5,
            "safety": 1.0,
            "minimality": 1.0,
            "evidence_quality": 1.0,
            "overall": 1.0,
        },
        "checks": [],
        "rejection_reasons": [],
        "warnings": [],
    }
    with pytest.raises(EvoForgeContractError, match="out of range"):
        validate_evaluation_report(report)


def test_missing_episode_json_rejected(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(EvoForgeEpisodeError, match="episode.json"):
        load_evoforge_episode(tmp_path / "empty")
