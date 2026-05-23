"""Week 5 capstone: external agent_run.json folders -> ComparisonReport.

Demonstrates the full Week 5 ingestion pipeline end-to-end against the shipped
``python_bugfix_basic`` benchmark pack:

    write simulated agent_run.json artifacts under tmp_path
        -> discover + load with Week 5 Day 3 helpers
        -> build per-agent RunReports with Week 5 Day 6 helpers
        -> build_comparison_report (Week 3)
        -> render_comparison_report_markdown (Week 3)

No agent is executed, no patch is applied, no test is run, and the agent's
``claimed_*`` flags are not trusted. The test writes only inside ``tmp_path``
and must never touch ``reports/generated/``.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.agent_runs import (
    AgentRunArtifact,
    build_run_reports_from_agent_artifact_dir,
    load_agent_run_artifacts_from_dir,
    save_agent_run_artifact_folder,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.comparison import (
    build_comparison_report,
    render_comparison_report_markdown,
)
from agenteval.core.schemas import ComparisonReport, RunReport, WeaknessCode

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

_CLAUDE_DIFF_001 = """\
diff --git a/repos/bugfix_001/calc.py b/repos/bugfix_001/calc.py
index 1111111..2222222 100644
--- a/repos/bugfix_001/calc.py
+++ b/repos/bugfix_001/calc.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end))
+    return sum(range(start, end + 1))
"""

_CLAUDE_DIFF_005 = """\
diff --git a/repos/bugfix_005/range_check.py b/repos/bugfix_005/range_check.py
index aaaaaaa..bbbbbbb 100644
--- a/repos/bugfix_005/range_check.py
+++ b/repos/bugfix_005/range_check.py
@@ -1,2 +1,2 @@
 def is_within_range(value, low, high):
-    return low < value < high
+    return low <= value <= high
"""

_CODEX_DIFF_003 = """\
diff --git a/repos/bugfix_003/names.py b/repos/bugfix_003/names.py
index ccccccc..ddddddd 100644
--- a/repos/bugfix_003/names.py
+++ b/repos/bugfix_003/names.py
@@ -1,2 +1,2 @@
 def normalize_name(name):
-    return name.lstrip()
+    return name.strip()
"""

_FORGE_DIFF_001 = """\
diff --git a/repos/bugfix_001/calc.py b/repos/bugfix_001/calc.py
index 1111111..3333333 100644
--- a/repos/bugfix_001/calc.py
+++ b/repos/bugfix_001/calc.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end)) + end
+    return sum(range(start, end + 1))
"""


def _write_capstone_artifacts(root: Path) -> list[Path]:
    """Lay out a simulated external-agent artifact tree under ``root``.

    Three simulated agents, partial coverage of the pack, mixed diff presence,
    and at least one ``claimed_public_tests_passed=True`` to prove claims do
    not translate into verified outcomes.
    """
    artifacts: list[tuple[Path, AgentRunArtifact]] = [
        (
            root / "claude_code_simulated" / "bugfix_001" / "run_001",
            AgentRunArtifact(
                agent_name="claude_code_simulated",
                task_id="bugfix_001",
                run_id="claude_code_simulated:bugfix_001:001",
                diff_text=_CLAUDE_DIFF_001,
                final_message="Off-by-one fixed; included end in the range.",
                claimed_commands=["pytest -q"],
                claimed_public_tests_passed=True,
                claimed_hidden_tests_passed=True,
                metadata={"model": "claude-opus-simulated", "wall_time_s": "9.1"},
            ),
        ),
        (
            root / "claude_code_simulated" / "bugfix_005" / "run_001",
            AgentRunArtifact(
                agent_name="claude_code_simulated",
                task_id="bugfix_005",
                run_id="claude_code_simulated:bugfix_005:001",
                diff_text=_CLAUDE_DIFF_005,
                final_message="Switched to inclusive comparisons.",
                claimed_commands=["pytest -q"],
                metadata={"model": "claude-opus-simulated"},
            ),
        ),
        (
            root / "codex_simulated" / "bugfix_003" / "run_001",
            AgentRunArtifact(
                agent_name="codex_simulated",
                task_id="bugfix_003",
                run_id="codex_simulated:bugfix_003:001",
                diff_text=_CODEX_DIFF_003,
                final_message="normalize_name now uses .strip().",
                claimed_commands=["pytest"],
                claimed_public_tests_passed=True,
                metadata={"model": "codex-simulated"},
            ),
        ),
        (
            root / "forgeagent_simulated" / "bugfix_001" / "run_001",
            AgentRunArtifact(
                agent_name="forgeagent_simulated",
                task_id="bugfix_001",
                run_id="forgeagent_simulated:bugfix_001:001",
                diff_text=_FORGE_DIFF_001,
                final_message="Replaced sentinel offset with inclusive range.",
                claimed_commands=["pytest"],
                claimed_hidden_tests_passed=True,
                metadata={"agent": "forgeagent-simulated"},
            ),
        ),
    ]

    written: list[Path] = []
    for folder, artifact in artifacts:
        written.append(save_agent_run_artifact_folder(artifact, folder))
    return written


def test_week5_capstone_full_pipeline(tmp_path: Path):
    runs_root = tmp_path / "agent_runs"
    written_paths = _write_capstone_artifacts(runs_root)
    assert len(written_paths) == 4

    # --- discovery + loading (Day 3) ----------------------------------------
    loaded = load_agent_run_artifacts_from_dir(runs_root)
    assert len(loaded) == 4
    loaded_agents = {a.agent_name for a in loaded}
    assert loaded_agents == {
        "claude_code_simulated",
        "codex_simulated",
        "forgeagent_simulated",
    }

    # --- per-agent RunReports (Day 6) ---------------------------------------
    pack = load_benchmark_pack(PACK_DIR)
    reports = build_run_reports_from_agent_artifact_dir(pack, runs_root)
    assert all(isinstance(r, RunReport) for r in reports)
    assert [r.agent_name for r in reports] == [
        "claude_code_simulated",
        "codex_simulated",
        "forgeagent_simulated",
    ]
    for report in reports:
        assert report.pack_name == "python_bugfix_basic"
        assert report.pack_version == "1.0"
        assert report.total_tasks == len(pack.tasks)
        # Every result is unverified — score 0, VERIFY present.
        assert report.mean_score == 0.0
        for result in report.results:
            assert result.passed_public_tests is False
            assert result.passed_hidden_tests is False
            assert WeaknessCode.VERIFY in result.weaknesses
            assert result.score == 0.0
        assert report.weakness_tally.get("VERIFY") == len(pack.tasks)

    # The Claude artifact that attempted bugfix_001 carried a diff —
    # its result must carry a parsed PatchSummary.
    claude_report = next(r for r in reports if r.agent_name == "claude_code_simulated")
    claude_by_task = {r.task_id: r for r in claude_report.results}
    assert claude_by_task["bugfix_001"].patch_summary is not None
    assert claude_by_task["bugfix_001"].patch_summary.changed_files == [
        "repos/bugfix_001/calc.py"
    ]
    # And the tasks Claude did not attempt are unattempted-unverified.
    assert claude_by_task["bugfix_002"].patch_summary is None
    assert (
        "no external agent artifact"
        in claude_by_task["bugfix_002"].rationale.lower()
    )

    # Claim non-trust: the Claude bugfix_001 artifact claimed both suites
    # passed, but the result must still show them as not passed.
    assert claude_by_task["bugfix_001"].passed_public_tests is False
    assert claude_by_task["bugfix_001"].passed_hidden_tests is False
    # The codex artifact also claimed public tests passed.
    codex_report = next(r for r in reports if r.agent_name == "codex_simulated")
    codex_by_task = {r.task_id: r for r in codex_report.results}
    assert codex_by_task["bugfix_003"].passed_public_tests is False

    # --- ComparisonReport (Week 3) ------------------------------------------
    comparison = build_comparison_report(reports)
    assert isinstance(comparison, ComparisonReport)
    assert comparison.pack_name == "python_bugfix_basic"
    assert comparison.pack_version == "1.0"
    assert set(comparison.agents) == {
        "claude_code_simulated",
        "codex_simulated",
        "forgeagent_simulated",
    }
    assert comparison.total_tasks == len(pack.tasks)
    # All zero scores -> every agent ties at 0.0 mean.
    assert all(score == 0.0 for score in comparison.mean_scores_by_agent.values())
    # Every agent's weakness tally must include VERIFY for every task.
    for agent in comparison.agents:
        assert comparison.weakness_tally_by_agent[agent].get("VERIFY") == len(
            pack.tasks
        )

    # --- Markdown rendering (Week 3) ----------------------------------------
    markdown = render_comparison_report_markdown(comparison)
    assert "# AgentEval Forge — Cross-Agent Comparison" in markdown
    assert "## Ranking" in markdown
    assert "## Pairwise summary" in markdown
    assert "## Per-task score matrix" in markdown
    assert "## Tasks where agents most disagree" in markdown
    assert "## Weakness tally by agent" in markdown
    # Every simulated agent name must appear somewhere in the rendered report.
    for agent in (
        "claude_code_simulated",
        "codex_simulated",
        "forgeagent_simulated",
    ):
        assert agent in markdown
    # VERIFY appears in the tally section.
    assert "VERIFY" in markdown

    # --- side-effect boundary -----------------------------------------------
    # The capstone must not have written anything outside tmp_path.
    generated_dir = REPO_ROOT / "reports" / "generated"
    capstone_marker = generated_dir / "week5_external_artifact_comparison.md"
    assert not capstone_marker.exists()
