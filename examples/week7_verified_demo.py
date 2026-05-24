"""Week 7 verified demo: simulated artifacts -> combined Markdown -> disk.

End-to-end demonstration of the verified evaluation + claim analysis flow,
saved as a single Markdown file under ``reports/generated/`` when run as
``__main__``:

    simulate three external agent_run.json artifacts under a temp dir
        -> build_and_render_verified_comparison_with_claims_markdown
           (Week 7 Day 2)
        -> save_verified_demo_outputs (Week 7 Day 3)

It performs **no** real agent execution and **no** network calls. The
original benchmark fixture is never patched — each verification copies the
fixture into a temporary workspace first. Agent ``claimed_*`` flags are
surfaced in the claim-analysis section of the rendered Markdown but never
trusted as verified evidence. Standard library only.

Importing this module is safe — no files are written on import.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agenteval.agent_runs import (
    AgentRunArtifact,
    build_and_render_verified_comparison_with_claims_markdown,
    save_verified_demo_outputs,
)
from agenteval.benchmarks.task_loader import load_benchmark_pack
from agenteval.fixtures import resolve_pack_fixture_layouts

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "benchmarks" / "python_bugfix_basic"

_ALPHA_CORRECT_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -12,4 +12,4 @@ def is_within_range(value, low, high):
     The function should be inclusive on both bounds, but currently uses
     strict inequalities.
     """
-    return low < value < high
+    return low <= value <= high
'''

_BETA_WRONG_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -12,4 +12,4 @@ def is_within_range(value, low, high):
     The function should be inclusive on both bounds, but currently uses
     strict inequalities.
     """
-    return low < value < high
+    return low == value == high
'''

_GAMMA_INVALID_PATCH = '''\
diff --git a/is_within_range.py b/is_within_range.py
--- a/is_within_range.py
+++ b/is_within_range.py
@@ -999,1 +999,1 @@
-this line does not exist
+this line will never apply
'''


def _simulated_artifacts() -> list[AgentRunArtifact]:
    """Three simulated agents with deliberately different claim/result profiles."""
    return [
        AgentRunArtifact(
            agent_name="alpha_correct",
            task_id="bugfix_005",
            run_id="alpha_correct:bugfix_005:001",
            diff_text=_ALPHA_CORRECT_PATCH,
            final_message="Switched to inclusive comparisons.",
            claimed_public_tests_passed=True,
            claimed_hidden_tests_passed=True,
        ),
        AgentRunArtifact(
            agent_name="beta_wrong_overclaim",
            task_id="bugfix_005",
            run_id="beta_wrong_overclaim:bugfix_005:001",
            diff_text=_BETA_WRONG_PATCH,
            final_message="All passing!",  # lie
            claimed_public_tests_passed=True,
            claimed_hidden_tests_passed=True,
        ),
        AgentRunArtifact(
            agent_name="gamma_no_patch_or_invalid",
            task_id="bugfix_005",
            run_id="gamma_no_patch_or_invalid:bugfix_005:001",
            diff_text=_GAMMA_INVALID_PATCH,
            final_message="Tried something.",
            claimed_public_tests_passed=True,
        ),
    ]


def _layouts_for_pack(pack):
    return {
        layout.task_id: layout
        for layout in resolve_pack_fixture_layouts(pack, project_root=REPO_ROOT)
    }


def build_week7_verified_demo_markdown(workspace_root: Path) -> str:
    """Build the combined verified comparison + claim analysis Markdown."""
    pack = load_benchmark_pack(PACK_DIR)
    return build_and_render_verified_comparison_with_claims_markdown(
        pack,
        _simulated_artifacts(),
        _layouts_for_pack(pack),
        workspace_root=workspace_root,
    )


def main() -> None:
    """Build the demo and save it to ``reports/generated/week7_verified_demo.md``.

    Tests must not call this helper — it writes outside any ``tmp_path``
    fixture. The directory is gitignored.
    """
    out_dir = REPO_ROOT / "reports" / "generated"

    with tempfile.TemporaryDirectory(prefix="agenteval_week7_demo_") as tmp:
        workspace_root = Path(tmp) / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        markdown = build_week7_verified_demo_markdown(workspace_root)

    saved = save_verified_demo_outputs(
        markdown=markdown,
        output_dir=out_dir,
        basename="week7_verified_demo",
    )

    print(f"Saved Markdown to {saved['markdown']}")
    print(f"  {len(markdown)} characters across {markdown.count(chr(10)) + 1} lines.")


if __name__ == "__main__":
    main()
