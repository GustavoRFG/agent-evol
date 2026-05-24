# Verified artifact demo

This document explains the verified evaluation pipeline that AgentEval Forge
ships with, and how to run the Week 7 demo end-to-end.

## What the verified demo does

The demo takes a small collection of simulated external agent run artifacts,
verifies each one by actually applying the patch and running the task's
public + hidden tests, then renders a combined Markdown report containing:

1. a cross-agent comparison (ranking, pairwise summary, per-task score
   matrix, per-task disagreement, per-agent weakness tally);
2. a claim analysis report (per-agent rollup of agent self-reported claims
   versus verified outcomes, including claim reliability metrics).

Everything runs locally. No agent is executed. No network call is made.

## What an `AgentRunArtifact` is

An `AgentRunArtifact` is the framework's standard in-memory record of a
single external agent run for a single task. The relevant fields are:

* `agent_name` — the agent that produced the run (e.g. `claude-code`,
  `codex`, `forgeagent`).
* `task_id` — the benchmark task the run targets (e.g. `bugfix_005`).
* `run_id` — a unique identifier for this specific run.
* `diff_text` — the unified-diff patch the agent produced (may be empty).
* `final_message` — the agent's final natural-language message.
* `transcript_text` — optional full transcript of the run.
* `claimed_commands` — commands the agent claims it ran.
* `claimed_public_tests_passed` / `claimed_hidden_tests_passed` — the
  agent's self-reported test outcomes. Tri-state: `True`, `False`, or
  `None` (no claim).
* `metadata` — opaque string key/value pairs (model name, wall time, etc.).

## What `agent_run.json` represents

`agent_run.json` is the on-disk serialization of one `AgentRunArtifact`.
External agents drop one folder per `(agent, task, attempt)` and write a
single `agent_run.json` inside it. The framework discovers them with
`load_agent_run_artifacts_from_dir`. A typical layout:

```
agent_runs/
  claude_code/bugfix_005/run_001/agent_run.json
  codex/bugfix_003/run_001/agent_run.json
```

Agents run *outside* AgentEval Forge. The framework only reads what they
left behind.

## Why claims are not trusted

The `claimed_*` flags are recorded but never used as verified evidence.
Agents can be wrong, optimistic, or actively misleading — the framework
treats those flags as self-report only. The verified pipeline ignores them
when deciding whether a result passes; it runs the tests itself. The claim
analysis report compares claims against verified outcomes after the fact, so
overclaims and underclaims become visible without polluting the ranking.

## How patch verification works

For each artifact whose `diff_text` is non-empty:

1. Copy the task's repo fixture into a fresh workspace under a
   caller-provided `workspace_root`. The original fixture is never touched.
2. Apply `diff_text` with `git apply --whitespace=nowarn` inside the copy.
   If application fails, the run is marked as failed verification with a
   `VERIFY` weakness; the original fixture is still untouched.
3. Run the task's public tests, then its hidden tests, against the patched
   copy via the controlled pytest harness.
4. Convert the public/hidden outcomes into a `TaskEvidence`, then into a
   final `EvaluationResult` via the existing result builder. No agent claims
   are consulted in this step.

Workspaces are sibling-isolated by a sanitized `(index, run_id)` so multiple
runs cannot collide.

## What public and hidden tests mean

Each benchmark task ships two pytest node-id buckets:

* **Public tests** are the tests the agent is allowed to see and target.
  Passing them means the agent's patch satisfies the visible spec.
* **Hidden tests** are reserved by the benchmark for evaluation. Passing
  them means the patch actually addresses the underlying bug, not just the
  visible surface.

The scoring helper considers both buckets independently. A patch that
passes public but not hidden is a "symptom fix" and is tagged with a
`ROOT` weakness; a patch that fails the visible suite is tagged `LAZY`.
Tasks the agent never attempted are tagged `VERIFY`.

## What claim reliability means

For each agent, the claim analysis layer counts:

* `matching_claims` — explicit `True` / `False` claims that matched the
  verified outcome (per bucket).
* `mismatching_claims` — explicit claims that disagreed with the verified
  outcome (per bucket).
* `overclaims` — claimed pass, verified failed.
* `underclaims` — claimed fail, verified passed.
* `results_with_no_claim` — runs where the agent made no claim at all.

These counters drive several rate properties (`claim_reliability`,
`mismatch_rate`, `overclaim_rate`, `underclaim_rate`, `no_claim_rate`).
Each rate is `None` when its denominator is zero — distinct from `0.0`,
which means the denominator was nonzero but the numerator was not.

Claim reliability is informational only. It does *not* change
`EvaluationResult.score`, `EvaluationResult.weaknesses`, or
`ComparisonReport.ranking`.

## How to run the demo

From the project root:

```
python -m examples.week7_verified_demo
```

This:

1. lays out three simulated agent artifacts (correct patch / wrong-but-clean
   patch / invalid patch) under a temporary directory;
2. runs the full verified comparison + claim analysis pipeline;
3. saves the combined Markdown under `reports/generated/`.

## What files are generated

When `examples/week7_verified_demo.py` is run as `__main__`:

* `reports/generated/week7_verified_demo.md` — the combined verified
  comparison + claim analysis Markdown.

The Week 6 capstone example (`examples/week6_verified_artifact_capstone.py`)
writes its own `reports/generated/week6_verified_capstone.md`. Both
directories are gitignored. Tests must never write to `reports/generated/`.

## Current limitations

* Verification is sequential — wall-clock scales with the number of
  attempted runs in the batch.
* The demo targets a single task (`bugfix_005`) across three agents. The
  pipeline supports arbitrary multi-task batches; the demo is intentionally
  small for clarity.
* Claim reliability is informational. No `WeaknessCode.FALSE` is injected
  into mismatched results.
* No CLI yet — the demo is invoked via the Python module path above.
* No CI workflow yet.
* No real agent execution and no network calls anywhere.
