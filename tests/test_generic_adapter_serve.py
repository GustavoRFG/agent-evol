"""Tests for the generic evidence-review stdin/stdout boundary."""

from __future__ import annotations

import io
import json

from agenteval.ingest.serve import serve_once

VALID_DIFF = """diff --git a/range_check.py b/range_check.py
index 1234567..89abcde 100644
--- a/range_check.py
+++ b/range_check.py
@@ -1,2 +1,2 @@
 def is_within_range(value, start, end):
-    return start < value < end
+    return start <= value <= end
"""


def _request() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "run_serve_001",
        "task": {
            "task_id": "range-validation-001",
            "prompt": "Fix the off-by-one bug in range validation.",
        },
        "patch": {
            "format": "unified_diff",
            "text": VALID_DIFF,
        },
    }


def _invoke(payload: object, *, validate_only: bool = False) -> tuple[int, dict]:
    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()

    exit_code = serve_once(
        stdin=stdin,
        stdout=stdout,
        validate_only=validate_only,
    )

    return exit_code, json.loads(stdout.getvalue())


def test_serve_once_writes_verdict_json_for_valid_request():
    exit_code, payload = _invoke(_request())

    assert exit_code == 0
    assert payload["mode"] == "evidence_review"
    assert payload["evidence_level"] == "patch_only_review"
    assert "verified_pass" not in json.dumps(payload)


def test_serve_once_validate_only_writes_ok_without_verdict():
    exit_code, payload = _invoke(_request(), validate_only=True)

    assert exit_code == 0
    assert payload == {"ok": True}


def test_serve_once_invalid_evidence_returns_structured_error():
    request = _request()
    request["patch"]["format"] = "binary_patch"

    exit_code, payload = _invoke(request)

    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_GENERIC_EVIDENCE"
    assert "patch.format" in payload["error"]["message"]


def test_serve_once_rejects_non_object_json():
    stdin = io.StringIO("[]")
    stdout = io.StringIO()

    exit_code = serve_once(stdin=stdin, stdout=stdout)
    payload = json.loads(stdout.getvalue())

    assert exit_code == 2
    assert payload["error"]["code"] == "INVALID_GENERIC_EVIDENCE"
    assert "must be an object" in payload["error"]["message"]


def test_serve_once_rejects_invalid_json():
    stdin = io.StringIO("{not valid")
    stdout = io.StringIO()

    exit_code = serve_once(stdin=stdin, stdout=stdout)
    payload = json.loads(stdout.getvalue())

    assert exit_code == 2
    assert payload["error"]["code"] == "INVALID_GENERIC_EVIDENCE"
    assert "invalid JSON" in payload["error"]["message"]
