# Generic Evidence Review V1

The generic V1 contract is the public, agent-agnostic input shape for Mode A
Evidence Review. It is independent of EvoForge, ForgeAgent, Claude Code, Codex,
and any other client dialect.

The adapter accepts JSON-compatible objects with:

```json
{
  "schema_version": "1.0",
  "run_id": "run_2026_06_06_001",
  "task": {
    "task_id": "optional-client-task-id",
    "prompt": "Fix the off-by-one bug in the range validation function."
  },
  "patch": {
    "format": "unified_diff",
    "text": "--- a/file.py\n+++ b/file.py\n@@ ..."
  }
}
```

Required fields:

- `schema_version`: must equal `"1.0"`.
- `run_id`: non-empty string.
- `task.prompt`: non-empty string.
- `patch.format`: must equal `"unified_diff"`.
- `patch.text`: non-empty unified diff text.

`patch.format` accepts only `"unified_diff"` in V1 because the format is
standardized, parseable, and supported by the existing `parse_unified_diff`
path.

Optional fields improve the verdict but are never required:

```json
{
  "producer": { "agent_name": "codex", "model": "optional-model-name" },
  "claims": {
    "public_tests_passed": true,
    "hidden_tests_passed": null,
    "all_tests_passed": true,
    "summary": "All visible tests passed."
  },
  "test_evidence": {
    "framework": "pytest",
    "command": "python -m pytest",
    "exit_code": 0,
    "summary": "12 passed in 0.41s",
    "stdout": "...",
    "stderr": ""
  },
  "trace": {
    "commands": ["cat src/file.py", "python -m pytest"],
    "final_message": "Fixed the boundary condition and ran the tests."
  },
  "integrity": {
    "algorithm": "sha256",
    "patch_sha256": "sha256:...",
    "test_evidence_sha256": "sha256:...",
    "bundle_sha256": "sha256:..."
  },
  "metadata": {
    "repository": "optional",
    "language": "python",
    "duration_seconds": 42
  }
}
```

Trace evidence should be operational evidence: commands, tool calls, changed
files, test output, and final messages. The generic contract does not require
the agent's private reasoning.

## Integrity Hashes

All V1 integrity hashes use SHA-256 over UTF-8 bytes. Digests may be supplied as
bare hex or as `sha256:<hex>`; responses normalize the concept to SHA-256.

- `patch_sha256`: SHA-256 of `patch.text`.
- `test_evidence_sha256`: SHA-256 of canonical JSON for `test_evidence`, using
  sorted keys and compact separators.
- `bundle_sha256`: SHA-256 of canonical JSON for the full evidence package with
  the entire `integrity` object removed.

Level 2 requires a supplied `integrity.algorithm == "sha256"` and a matching
`patch_sha256`. Any supplied optional hash must also verify. Hash mismatches
are flagged and do not reach Level 2.

Hash binding proves the submitted package is internally consistent. It does not
prove the original execution was truthful or that the submitter is trustworthy.

## Response Shape

The adapter returns a Mode A verdict shaped like:

```json
{
  "evaluation_id": "eval_run_2026_06_06_001",
  "mode": "evidence_review",
  "evidence_level": "self_reported_execution_evidence",
  "verdict": "requires_review",
  "scores": {
    "task_alignment": 0.7,
    "patch_minimality": 0.91,
    "evidence_quality": 0.6,
    "safety_signal": 0.88
  },
  "findings": [
    {
      "severity": "warning",
      "code": "EXECUTION_NOT_INDEPENDENTLY_VERIFIED",
      "message": "Execution evidence was supplied by the caller and was not reproduced by AgentEval Forge."
    }
  ],
  "claims": {
    "tests_claimed_passed": true,
    "evidence_consistent_with_claim": true,
    "independently_verified": false
  },
  "integrity": {
    "hash_manifest_supplied": false,
    "hashes_verified": false
  },
  "human_review": {
    "recommended": true,
    "reasons": ["Execution was not independently reproduced."]
  }
}
```

Mode A verdicts use `review_only`, `requires_review`, `looks_consistent`, or
`inconsistent`. They never use `verified_pass`.
