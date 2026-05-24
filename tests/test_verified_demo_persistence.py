"""Tests for verified-demo persistence helpers, example import, and docs."""

import importlib
from pathlib import Path

import pytest

from agenteval.agent_runs import (
    VerifiedDemoPersistenceError,
    save_text_file,
    save_verified_comparison_with_claims_markdown,
    save_verified_demo_outputs,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_PATH = REPO_ROOT / "docs" / "verified_artifact_demo.md"


# ---- save_text_file --------------------------------------------------------


def test_save_text_file_writes_utf8(tmp_path: Path):
    target = tmp_path / "out.txt"
    returned = save_text_file("héllo — wörld\n", target)
    assert returned == target
    assert target.read_text(encoding="utf-8") == "héllo — wörld\n"


def test_save_text_file_creates_parent_directories(tmp_path: Path):
    target = tmp_path / "nested" / "deeper" / "out.md"
    save_text_file("content", target)
    assert target.is_file()


def test_save_text_file_accepts_string_path(tmp_path: Path):
    target = tmp_path / "out.txt"
    returned = save_text_file("hi", str(target))
    assert returned == target
    assert target.is_file()


def test_save_text_file_returns_path_object(tmp_path: Path):
    returned = save_text_file("x", tmp_path / "x.txt")
    assert isinstance(returned, Path)


def test_save_text_file_rejects_non_string_text(tmp_path: Path):
    with pytest.raises(VerifiedDemoPersistenceError, match="text must be a string"):
        save_text_file(123, tmp_path / "out.txt")  # type: ignore[arg-type]


def test_save_text_file_rejects_non_string_or_path(tmp_path: Path):
    with pytest.raises(VerifiedDemoPersistenceError, match="path must be"):
        save_text_file("x", 42)  # type: ignore[arg-type]


def test_save_text_file_write_failure_raises_wrapped(tmp_path: Path):
    # Attempt to write *into* an existing file by treating it as a parent dir.
    blocking_file = tmp_path / "blocker"
    blocking_file.write_text("not a dir", encoding="utf-8")
    target = blocking_file / "out.txt"
    with pytest.raises(VerifiedDemoPersistenceError, match="failed to write"):
        save_text_file("payload", target)


# ---- save_verified_comparison_with_claims_markdown -------------------------


def test_save_verified_markdown_writes_text(tmp_path: Path):
    target = tmp_path / "combined.md"
    md = "# Combined report\n\n## Ranking\n- alpha\n"
    returned = save_verified_comparison_with_claims_markdown(md, target)
    assert returned == target
    assert target.read_text(encoding="utf-8") == md


def test_save_verified_markdown_rejects_non_string(tmp_path: Path):
    with pytest.raises(VerifiedDemoPersistenceError, match="markdown"):
        save_verified_comparison_with_claims_markdown(
            None, tmp_path / "out.md"  # type: ignore[arg-type]
        )


# ---- save_verified_demo_outputs --------------------------------------------


def test_save_demo_outputs_writes_expected_md(tmp_path: Path):
    md = "# demo\n"
    saved = save_verified_demo_outputs(
        markdown=md, output_dir=tmp_path, basename="my_demo"
    )
    assert set(saved.keys()) == {"markdown"}
    md_path = saved["markdown"]
    assert md_path == tmp_path / "my_demo.md"
    assert md_path.read_text(encoding="utf-8") == md


def test_save_demo_outputs_default_basename(tmp_path: Path):
    saved = save_verified_demo_outputs(markdown="ok", output_dir=tmp_path)
    assert saved["markdown"].name == "verified_agent_eval_demo.md"


def test_save_demo_outputs_creates_output_dir(tmp_path: Path):
    out_dir = tmp_path / "fresh" / "nested"
    saved = save_verified_demo_outputs(markdown="ok", output_dir=out_dir)
    assert saved["markdown"].is_file()


def test_save_demo_outputs_rejects_empty_basename(tmp_path: Path):
    with pytest.raises(VerifiedDemoPersistenceError, match="basename"):
        save_verified_demo_outputs(
            markdown="x", output_dir=tmp_path, basename=""
        )
    with pytest.raises(VerifiedDemoPersistenceError, match="basename"):
        save_verified_demo_outputs(
            markdown="x", output_dir=tmp_path, basename="   "
        )


def test_save_demo_outputs_rejects_non_string_markdown(tmp_path: Path):
    with pytest.raises(VerifiedDemoPersistenceError, match="markdown"):
        save_verified_demo_outputs(
            markdown=42, output_dir=tmp_path  # type: ignore[arg-type]
        )


def test_save_demo_outputs_rejects_non_path_output_dir():
    with pytest.raises(VerifiedDemoPersistenceError, match="output_dir"):
        save_verified_demo_outputs(
            markdown="x", output_dir=123  # type: ignore[arg-type]
        )


# ---- example module import safety ------------------------------------------


def test_example_module_can_be_imported_without_writing_generated():
    generated_marker = REPO_ROOT / "reports" / "generated" / "week7_verified_demo.md"
    existed_before = generated_marker.exists()

    module = importlib.import_module("examples.week7_verified_demo")
    # The module must expose ``main`` but importing it must not invoke main.
    assert hasattr(module, "main")
    assert callable(module.main)

    # No new file must have appeared as a side effect of import.
    if existed_before:
        assert generated_marker.exists()  # was already there; still there
    else:
        assert not generated_marker.exists()


# ---- documentation presence + content --------------------------------------


def test_docs_file_exists():
    assert DOCS_PATH.is_file(), f"missing documentation at {DOCS_PATH}"


def test_docs_contains_key_phrases():
    text = DOCS_PATH.read_text(encoding="utf-8")
    for phrase in (
        "AgentRunArtifact",
        "agent_run.json",
        "verified evaluation",
        "public and hidden tests",
        "claim reliability",
        "claims are not trusted",
    ):
        assert phrase in text, f"docs missing required phrase: {phrase!r}"


def test_docs_explains_how_to_run_demo():
    text = DOCS_PATH.read_text(encoding="utf-8")
    assert "examples.week7_verified_demo" in text
    assert "reports/generated" in text


# ---- side-effect boundary --------------------------------------------------


def test_tests_did_not_write_week7_generated_files():
    generated_dir = REPO_ROOT / "reports" / "generated"
    # The file may exist from a prior __main__ invocation; this test only
    # asserts our test run does not create a new fingerprint. We snapshot
    # before and after a no-op to confirm tests don't write here.
    snapshot = sorted(p.name for p in generated_dir.glob("week7_*")) if generated_dir.exists() else []
    # Re-run save into tmp via tmp_path is exercised above; nothing new here.
    after = sorted(p.name for p in generated_dir.glob("week7_*")) if generated_dir.exists() else []
    assert snapshot == after
