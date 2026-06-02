"""Command-line interface for AgentEval Forge.

Run as ``python -m agenteval.cli <command> ...`` (or ``python -m agenteval``).

Commands:

* ``export-evoforge-evaluation`` — read a persisted EvoForge episode, judge its
  grounded evidence independently, and write a native AgentEval Forge external
  evaluation report that EvoForge can attach with ``attach-agenteval``.

Exit codes for ``export-evoforge-evaluation``:

* ``0`` — report generated (verdict ``pass`` or ``fail``); a ``fail`` verdict is
  still a successful export.
* ``1`` — report generated with verdict ``needs_review``.
* ``2`` — invalid / stale / unsafe episode, or any export failure.

Standard library only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from agenteval import __version__
from agenteval.integrations.evoforge import (
    EvoForgeContractError,
    EvoForgeEpisodeError,
    EvoForgeExportError,
    export_evoforge_evaluation,
)

EXIT_OK = 0
EXIT_NEEDS_REVIEW = 1
EXIT_ERROR = 2


def _cmd_export_evoforge_evaluation(args: argparse.Namespace) -> int:
    try:
        result = export_evoforge_evaluation(
            Path(args.evoforge_run),
            Path(args.output),
            overwrite=args.overwrite,
        )
    except (EvoForgeEpisodeError, EvoForgeContractError, EvoForgeExportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    scores = result["scores"]
    print("Exported AgentEval Forge evaluation for EvoForge.")
    print(f"Run: {result['run_id']}")
    print(f"Trace ID: {result['trace_id']}")
    print(f"Source evaluation ID: {result['source_evaluation_id']}")
    print(f"Verdict: {result['verdict']}")
    print("Scores:")
    for name in ("correctness", "safety", "minimality", "evidence_quality", "overall"):
        print(f"  {name}: {scores[name]}")
    if result["rejection_reasons"]:
        print("Rejection reasons:")
        for reason in result["rejection_reasons"]:
            print(f"  - {reason}")
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    print(f"Output: {result['output_path']}")

    if result["verdict"] == "needs_review":
        return EXIT_NEEDS_REVIEW
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Build the AgentEval Forge CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="agenteval",
        description="AgentEval Forge - evaluate agentic coding systems.",
    )
    parser.add_argument(
        "--version", action="version", version=f"AgentEval Forge {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export-evoforge-evaluation",
        help="Export a native AgentEval Forge evaluation report for an EvoForge episode.",
    )
    export_parser.add_argument(
        "--evoforge-run",
        required=True,
        help="Path to an EvoForge run directory containing episode.json.",
    )
    export_parser.add_argument(
        "--output",
        required=True,
        help="Destination path for the evaluation JSON report.",
    )
    export_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output file whose content differs.",
    )
    export_parser.set_defaults(func=_cmd_export_evoforge_evaluation)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
