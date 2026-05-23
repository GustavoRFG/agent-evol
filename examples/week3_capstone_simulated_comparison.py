"""Week 3 capstone: a simulated end-to-end multi-agent comparison.

This example wires the full Week 3 pipeline together on top of the shipped
``python_bugfix_basic`` benchmark pack:

    load pack
        -> build several simulated RunReports (one per agent)
        -> build_comparison_report
        -> render Markdown (ranking, pairwise, per-task matrix,
                            divergence, weakness tally)
        -> persist JSON + Markdown

It is fully agent-agnostic — every agent is identified only by a name string,
and the simulated identifiers (``claude_code_simulated``, ``codex_simulated``,
…) are arbitrary labels, not provider-specific code paths.

It performs **no** real agent execution: no Claude Code, Codex, ForgeAgent,
DGM, DeepSeek, Grok, external APIs, network calls, subprocess agents, or
shell execution; no patches are applied to the filesystem; no target
repository tests are run. Everything below is assembled from already-known
evidence using existing helpers. Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.comparison import (
    build_comparison_report,
    render_comparison_report_markdown,
    save_comparison_report,
    save_comparison_report_markdown,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    ComparisonReport,
    RunReport,
    WeaknessCode,
)
from agenteval.evaluation import TaskEvidence, evaluate_pack_to_report

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

# A small, deterministic correct-fix diff used to demonstrate that patch
# evidence flows through the pipeline. The content does not need to apply
# anywhere — it is only parsed for changed-file metadata.
_CORRECT_FIX_DIFF = """\
diff --git a/repos/bugfix_001/calc.py b/repos/bugfix_001/calc.py
index 1111111..2222222 100644
--- a/repos/bugfix_001/calc.py
+++ b/repos/bugfix_001/calc.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end))
+    return sum(range(start, end + 1))
"""

# A symptomatic patch that satisfies the public tests but not the hidden ones.
_SYMPTOM_FIX_DIFF = """\
diff --git a/repos/bugfix_001/calc.py b/repos/bugfix_001/calc.py
index 1111111..3333333 100644
--- a/repos/bugfix_001/calc.py
+++ b/repos/bugfix_001/calc.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end))
+    return sum(range(start, end)) + end
"""


def _evidence_profiles(
    pack: BenchmarkPack,
) -> list[tuple[str, dict[str, TaskEvidence]]]:
    """Return ``(agent_name, evidence_by_task_id)`` pairs for the capstone.

    Five simulated agents with deliberately different evidence shapes so the
    Week 3 report surfaces real ranking, divergence, weaknesses, and patch
    evidence rather than five identical rows. The agent names are arbitrary
    strings — nothing in this module branches on them.
    """
    task_id = pack.tasks[0].task_id

    # Strong: passes public + hidden, carries a real diff.
    strong = {
        task_id: TaskEvidence(
            passed_public_tests=True,
            passed_hidden_tests=True,
            rationale="Off-by-one fixed; both public and hidden suites pass.",
            diff_text=_CORRECT_FIX_DIFF,
        )
    }

    # Symptom fix: public passes, hidden fails — flagged as ROOT.
    symptom_fix = {
        task_id: TaskEvidence(
            passed_public_tests=True,
            passed_hidden_tests=False,
            weaknesses=[WeaknessCode.ROOT],
            rationale=(
                "Public tests pass but hidden tests fail; "
                "patched a symptom rather than the root cause."
            ),
            diff_text=_SYMPTOM_FIX_DIFF,
        )
    }

    # Correct but overengineered: full pass with an OVERENG flag.
    overengineered = {
        task_id: TaskEvidence(
            passed_public_tests=True,
            passed_hidden_tests=True,
            weaknesses=[WeaknessCode.OVERENG],
            rationale="Correct fix, but added unrequested helper utilities.",
        )
    }

    # Unverified: no evidence at all → VERIFY weakness from the batch builder.
    unverified: dict[str, TaskEvidence] = {}

    # Self-reported success that never ran the suite: explicit VERIFY + FALSE.
    false_claim = {
        task_id: TaskEvidence(
            passed_public_tests=False,
            passed_hidden_tests=False,
            weaknesses=[WeaknessCode.VERIFY, WeaknessCode.FALSE],
            rationale=(
                "Agent claimed success without running tests; "
                "no verification evidence was produced."
            ),
        )
    }

    return [
        ("claude_code_simulated", strong),
        ("codex_simulated", symptom_fix),
        ("forgeagent_simulated", overengineered),
        ("dgm_original_simulated", unverified),
        ("deepseek_simulated", false_claim),
    ]


def build_simulated_week3_capstone_reports() -> list[RunReport]:
    """Build simulated :class:`RunReport` objects for the Week 3 capstone.

    Loads the shipped ``python_bugfix_basic`` benchmark pack and evaluates it
    against each agent's pre-canned :class:`TaskEvidence` via
    :func:`evaluate_pack_to_report`. No agent is actually executed.

    Returns:
        One :class:`RunReport` per simulated agent, in a deterministic order.
    """
    pack = load_benchmark_pack(PACK_DIR)
    return [
        evaluate_pack_to_report(pack, agent_name, evidence)
        for agent_name, evidence in _evidence_profiles(pack)
    ]


def build_simulated_week3_capstone_comparison() -> ComparisonReport:
    """Build the simulated capstone :class:`ComparisonReport`.

    Wraps :func:`build_simulated_week3_capstone_reports` with
    :func:`build_comparison_report`.
    """
    return build_comparison_report(build_simulated_week3_capstone_reports())


def render_simulated_week3_capstone_markdown() -> str:
    """Render the simulated capstone comparison as Markdown.

    The output includes the ranking, pairwise summary, per-task score matrix,
    divergence section, and per-agent weakness tally produced by
    :func:`render_comparison_report_markdown`.
    """
    return render_comparison_report_markdown(
        build_simulated_week3_capstone_comparison()
    )


def main() -> None:
    """Save the simulated capstone comparison to ``reports/generated/``.

    Tests must not call this helper — it writes to a path outside any
    ``tmp_path`` fixture. The directory is gitignored.
    """
    out_dir = REPO_ROOT / "reports" / "generated"
    json_path = out_dir / "week3_capstone_comparison.json"
    md_path = out_dir / "week3_capstone_comparison.md"

    comparison = build_simulated_week3_capstone_comparison()
    save_comparison_report(comparison, json_path)
    save_comparison_report_markdown(comparison, md_path)

    print(f"Saved JSON to {json_path}")
    print(f"Saved Markdown to {md_path}")


if __name__ == "__main__":
    main()
