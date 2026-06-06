"""Stdin/stdout boundary for generic Mode A evidence review.

This module is intentionally small: it reads one JSON object, validates or
evaluates it through the generic adapter, and writes JSON to stdout. It never
applies patches, runs client tests, touches workspaces, or makes network calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, TextIO

from agenteval.ingest.generic_adapter import (
    GenericAgentRunAdapter,
    GenericAgentRunAdapterError,
    evaluate_generic_agent_run,
)

INVALID_JSON = "INVALID_JSON"
INVALID_GENERIC_EVIDENCE = "INVALID_GENERIC_EVIDENCE"
INTERNAL_ERROR = "INTERNAL_ERROR"


def _write_json(stream: TextIO, payload: dict[str, Any]) -> None:
    json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    stream.write("\n")
    stream.flush()


def _read_json_object(stream: TextIO) -> dict[str, Any]:
    try:
        payload = json.load(stream)
    except json.JSONDecodeError as exc:
        raise GenericAgentRunAdapterError(f"invalid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise GenericAgentRunAdapterError(
            f"generic evidence package must be an object, got {type(payload).__name__}"
        )
    return payload


def serve_once(
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    validate_only: bool = False,
) -> int:
    """Process one generic evidence package from ``stdin``.

    Returns a process-style exit code:
    - 0 for success;
    - 2 for caller-supplied invalid input;
    - 1 for unexpected internal failures.
    """
    try:
        payload = _read_json_object(stdin)
        if validate_only:
            GenericAgentRunAdapter().validate(payload)
            _write_json(stdout, {"ok": True})
        else:
            _write_json(stdout, evaluate_generic_agent_run(payload))
        return 0
    except GenericAgentRunAdapterError as exc:
        _write_json(
            stdout,
            {
                "ok": False,
                "error": {
                    "code": INVALID_GENERIC_EVIDENCE,
                    "message": str(exc),
                },
            },
        )
        return 2
    except Exception:
        _write_json(
            stdout,
            {
                "ok": False,
                "error": {
                    "code": INTERNAL_ERROR,
                    "message": "internal evaluator error",
                },
            },
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate one generic AgentEval evidence package from stdin."
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the V1 package and exit without producing a verdict.",
    )
    args = parser.parse_args(argv)
    return serve_once(validate_only=args.validate_only)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
