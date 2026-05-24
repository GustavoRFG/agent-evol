"""Tests for the GitHub Actions CI workflow and accompanying README section."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
README_PATH = REPO_ROOT / "README.md"


def _workflow_text() -> str:
    assert WORKFLOW_PATH.is_file(), f"missing CI workflow at {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


# ---- workflow file presence ------------------------------------------------


def test_ci_workflow_file_exists():
    assert WORKFLOW_PATH.is_file()


def test_workflow_has_ci_name():
    text = _workflow_text()
    assert "name: CI" in text


# ---- triggers --------------------------------------------------------------


def test_workflow_runs_on_push():
    text = _workflow_text()
    on_block = text.split("\non:", 1)[1].split("\njobs:", 1)[0]
    assert "push" in on_block


def test_workflow_runs_on_pull_request():
    text = _workflow_text()
    on_block = text.split("\non:", 1)[1].split("\njobs:", 1)[0]
    assert "pull_request" in on_block


# ---- runner + actions ------------------------------------------------------


def test_workflow_runs_on_ubuntu_latest():
    text = _workflow_text()
    assert "runs-on: ubuntu-latest" in text


def test_workflow_uses_actions_checkout():
    text = _workflow_text()
    assert "actions/checkout@v6" in text


def test_workflow_uses_actions_setup_python():
    text = _workflow_text()
    assert "actions/setup-python@v6" in text


def test_workflow_sets_explicit_python_version():
    text = _workflow_text()
    # The project requires Python 3.11+. The workflow should pin a concrete
    # 3.x version (not "latest" or "3").
    assert "python-version:" in text
    pinned_line = next(
        line for line in text.splitlines() if "python-version:" in line
    )
    assert any(version in pinned_line for version in ('"3.11"', '"3.12"', "'3.11'", "'3.12'"))


# ---- test execution --------------------------------------------------------


def test_workflow_runs_pytest():
    text = _workflow_text()
    assert "python -m pytest" in text


def test_workflow_installs_package_with_dev_extras():
    text = _workflow_text()
    assert 'pip install -e ".[dev]"' in text or "pip install -e .[dev]" in text


# ---- safety constraints ----------------------------------------------------


def test_workflow_does_not_reference_secrets():
    text = _workflow_text()
    # No CI step should pull a GitHub secret or env-mapped secret.
    lowered = text.lower()
    assert "secrets." not in lowered
    assert "${{ secrets" not in lowered


def test_workflow_does_not_run_real_agents():
    text = _workflow_text().lower()
    # The CI workflow must not invoke any real agent or external coding tool.
    for forbidden in (
        "claude-code",
        "claude_code",
        "codex",
        "forgeagent",
        "anthropic",
        "openai",
        "curl ",
        "wget ",
    ):
        assert forbidden not in text, (
            f"CI workflow must not reference {forbidden!r}"
        )


def test_workflow_does_not_upload_external_artifacts():
    text = _workflow_text().lower()
    # No coverage upload or external artifact services.
    for service in ("codecov", "coveralls"):
        assert service not in text


# ---- README CI section -----------------------------------------------------


def test_readme_mentions_ci():
    assert README_PATH.is_file()
    text = README_PATH.read_text(encoding="utf-8")
    # The README should describe the CI workflow so contributors know it exists.
    assert "Continuous integration" in text or "## CI" in text
    assert ".github/workflows/ci.yml" in text
    assert "pytest" in text
