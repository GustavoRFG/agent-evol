# Design of a Robust AI Coding Evaluation Framework

This document explains the design of **AgentEval Forge**, a Python framework
for evaluating autonomous coding agents. It is intended as both an
architectural reference and an interview-ready synthesis of the project.

## 1. Problem statement

Coding agents are easy to demo and hard to measure. A single transcript
where Claude Code, Codex, ForgeAgent, or DGM cheerfully reports "all tests
pass" tells you almost nothing about whether the agent actually solved the
task. In practice, several failure modes are common:

* The agent produces a *plausible but wrong* patch that compiles and
  satisfies the surface-level tests yet misses the underlying bug.
* The agent **overclaims** success: its final message asserts that public
  and hidden tests pass even though nothing was executed, or even though
  what was executed failed.
* The final answer alone is insufficient: a structured patch, a transcript,
  and the actual test outcomes are all needed to judge the work.
* Different agents need to be compared on the **same** task with the
  **same** evidence shape so ranking is meaningful.
* Evidence must be **reproducible** — running the evaluation twice should
  give the same answer for the same inputs.

A robust evaluation framework therefore needs to capture tasks, fixtures,
patches, test outcomes, structured evidence, agent self-reports, and a
comparison surface. It must verify what is verifiable and remain honest
about what is not.

## 2. Design goals

* **Reproducibility** — given the same artifact and the same fixture, the
  framework produces the same `EvaluationResult`.
* **Controlled execution** — patches are applied inside copied workspaces;
  the original benchmark fixture is never mutated.
* **Public and hidden tests** — every task ships a visible suite and a
  hidden suite, so symptom-fixes can be told from root-cause-fixes.
* **Artifact-based ingestion** — agents run *outside* the framework and
  drop `agent_run.json` files; the framework ingests them.
* **Verified evidence** — only outcomes the framework itself produced by
  applying the patch and running the tests count as evidence.
* **Claim non-trust** — agent self-reported `claimed_*` flags are
  surfaced for analysis but never used as verified outcomes. In short,
  agent claims are not evidence.
* **Multi-agent comparison** — ranking, pairwise comparison, per-task
  divergence, and weakness tally are first-class outputs.
* **Auditability** — every result carries its `task_id`, `run_id`, parsed
  patch summary, rationale, and weaknesses, so a reader can trace why a
  score is what it is.
* **Extensibility** — new benchmark packs, new tasks, new agents, and new
  failure-mode codes can be added without changing the core schemas or the
  scoring helper.

## 3. High-level architecture

The framework is layered. Each layer has a single responsibility and is
composed by the next layer up. The control flow for a verified comparison
looks like this:

```
+-------------------------+
|  external agents (Claude Code, Codex,
|  ForgeAgent, DGM, …)    |
+-----------+-------------+
            |
            v   agent_run.json files
+-----------+-------------+
|  AgentRunArtifact       |   <-- ingestion (Week 5)
+-----------+-------------+
            |
            v
+-----------+-------------+
|  TaskFixtureLayout      |   <-- fixture discovery (Week 4)
+-----------+-------------+
            |
            v
+-----------+-------------+
|  copy_fixture_apply_patch_and_run_tests
|    - copy fixture       |
|    - git apply diff     |
|    - run public tests   |
|    - run hidden tests   |   <-- controlled execution (Week 4)
+-----------+-------------+
            |
            v
+-----------+-------------+
|  TaskEvidence           |   <-- evidence schema (Week 2/4)
+-----------+-------------+
            |
            v
+-----------+-------------+
|  EvaluationResult       |   <-- result builder + scoring (Week 1/2)
+-----------+-------------+
            |
            v
+-----------+-------------+
|  RunReport (per agent)  |   <-- aggregation (Week 2)
+-----------+-------------+
            |
            v
+-----------+-------------+
|  ComparisonReport       |   <-- cross-agent (Week 3)
+-----------+-------------+
            |
            +--> ClaimAnalysisReport (Week 6 Day 5–6)
            |       overclaim / underclaim / reliability
            v
+-------------------------+
|  Combined Markdown      |   <-- demo output (Week 7)
+-------------------------+

(CI runs the full pytest suite on every push/pull_request — Week 7 Day 4.)
```

The key insight is that each box is a *plain dataclass* and each arrow is a
*pure function* (apart from the controlled-execution box, which is the only
place that touches the filesystem and subprocesses).

## 4. Benchmark design

A benchmark is shipped as a `BenchmarkPack` — a versioned collection of
`TaskSpec` objects. The project ships `python_bugfix_basic` (pack version
`1.0`) with five Python bug-fix tasks (`bugfix_001` through `bugfix_005`).

Each `TaskSpec` carries:

* `task_id`, `title`, `version`, `description`;
* `repo_path` — where the broken reference implementation lives;
* `public_tests` — pytest node IDs the agent is allowed to see and target;
* `hidden_tests` — pytest node IDs reserved by the benchmark.

**Public tests** measure whether the agent satisfied the visible
specification. **Hidden tests** measure whether the agent addressed the
underlying bug. A patch that passes public but not hidden tests is a
symptom-fix and gets a `WeaknessCode.ROOT` weakness. A patch that fails
public is `WeaknessCode.LAZY`. Tasks the agent never attempted are
`WeaknessCode.VERIFY`. The two-bucket design is the smallest mechanism that
distinguishes "satisfied the surface spec" from "actually fixed the bug",
and it scales naturally — a richer task can ship more hidden node IDs
without changing any framework code.

Task coverage matters because a single-task report cannot distinguish a
generally strong agent from a lucky one. The pack/aggregation layer
preserves per-task results so divergence and per-task ranking are visible
in the comparison report.

## 5. Controlled execution model

This is the only layer that performs side effects. It does so under tight
constraints:

* **One isolated workspace per run.** Each verification call copies the
  task's repo fixture into a fresh directory under a caller-provided
  `workspace_root`, so every run gets its own isolated workspace and the
  original benchmark fixture is never touched. Workspaces are
  sibling-isolated by a sanitized `(index, run_id)` prefix so two runs
  of the same `run_id` never collide.
* **`git apply` for patches.** Diffs are fed to `git apply
  --whitespace=nowarn -` over stdin, with `cwd=workspace_path`. The diff
  bytes are piped raw so Python's text-mode wrapper never translates
  `\n` into `\r\n` on Windows (a real bug that would otherwise break
  hunk matching).
* **Path safety.** Before invoking `git apply`, every path inside the
  diff is rejected if it is absolute or contains a `..` segment.
* **Public and hidden pytest execution.** Both buckets run via
  `subprocess.run(...)` against the *same* patched workspace, with no
  shared state between buckets beyond the patch itself.
* **Subprocess boundaries.** Subprocess output is captured as bytes and
  decoded explicitly with `errors="replace"`. Exit codes are inspected;
  non-zero exits are propagated as structured exceptions, not silently
  swallowed.
* **Timeouts.** `git apply` and each pytest invocation run under a
  caller-controlled `timeout_seconds` (default `30`). On timeout the
  helper raises a typed exception with the workspace path attached.

The result is that an artifact can be verified safely: a malicious diff
cannot escape the copied workspace, a hanging test cannot block forever,
and a CRLF/LF mismatch cannot silently corrupt the patch.

## 6. External agent artifacts

AgentEval Forge does **not** execute agents. Agents are large, opinionated
systems; trying to drive them all from one framework would couple the
evaluator to every agent's authentication, rate-limiting, prompt format,
and tool layer. Instead, agents run *outside* the framework and drop
artifacts in a known shape:

```
agent_runs/
  claude_code/bugfix_005/run_001/agent_run.json
  codex/bugfix_003/run_001/agent_run.json
  forgeagent/bugfix_001/run_001/agent_run.json
```

Each `agent_run.json` deserializes into an `AgentRunArtifact` carrying:

* identity: `agent_name`, `task_id`, `run_id`;
* the work: `diff_text` (unified diff), `final_message`, `transcript_text`;
* self-report: `claimed_commands`, `claimed_public_tests_passed`,
  `claimed_hidden_tests_passed`;
* opaque labels: `metadata` (model name, wall time, etc.).

This separation is useful for several reasons. The framework stays small
and dependency-free. Agents can run on different machines, networks, or
even cloud accounts, with no framework code in their loop. New agents are
trivial to support — write `agent_run.json` and drop it in. And, crucially,
ingestion is fully testable with fixture-only inputs: no network, no API
keys, no flakiness.

## 7. Verified evaluation pipeline

A verified evaluation for one external artifact runs through this
composition (most calls are one-liners over the previous layer):

```
AgentRunArtifact
  -> ingest_agent_run_artifact      (parse diff, build preliminary evidence)
  -> verify_ingested_agent_run      (copy + git apply + public + hidden)
        -> copy_fixture_apply_patch_and_build_evidence
              -> copy_fixture_to_workspace
              -> apply_patch_to_workspace
              -> run_pytest_nodes_in_workspace (public)
              -> run_pytest_nodes_in_workspace (hidden)
              -> build_task_evidence_from_pytest_results
        -> build_evaluation_result
  -> EvaluationResult
```

The batch and per-agent variants compose the same primitives. A
verification failure (empty diff, invalid patch, harness error) becomes a
typed `EvaluationResult` with `WeaknessCode.VERIFY` and a
`"Verification failed: …"` rationale when `continue_on_error=True`, or a
typed exception when `continue_on_error=False`. The agent's `claimed_*`
flags are never read by this pipeline.

The pack-level helper
`build_verified_run_report_from_agent_artifacts(pack, agent_name, artifacts, layouts, *, workspace_root)`
fills in unattempted pack tasks with unverified results and aggregates the
attempted-task verified results into a `RunReport`. The cross-agent helper
`build_verified_comparison_report_from_agent_artifacts(...)` does the same
across agents and produces a `ComparisonReport`.

## 8. Claim versus verified outcome analysis

Agent claims and verified outcomes are tracked as separate streams. A
per-result `ClaimVerificationSummary` records, for one
`(AgentRunArtifact, EvaluationResult)` pair:

* `claimed_public_tests_passed` (tri-state) vs `passed_public_tests`;
* `claimed_hidden_tests_passed` (tri-state) vs `passed_hidden_tests`;
* `public_claim_matches` / `hidden_claim_matches` (tri-state — `None`
  when the agent made no claim);
* `has_any_claim`, `has_mismatch`, `mismatch_labels`, `rationale`.

The per-agent rollup `AgentClaimRollup` counts public and hidden buckets
independently. A result that overclaimed both buckets contributes `2` to
`mismatching_claims` and `2` to `overclaims` but `1` to `mismatch_run_ids`
(one *result* with mismatches). The rollup exposes five derived rates as
computed properties:

* `claim_reliability = matching / explicit_claims`
* `mismatch_rate = mismatching / explicit_claims`
* `overclaim_rate = overclaims / explicit_claims`
* `underclaim_rate = underclaims / explicit_claims`
* `no_claim_rate = results_with_no_claim / total_results`

Each rate is `None` when its denominator is zero — distinct from `0.0`,
which means the denominator is nonzero but the numerator is. The
distinction lets a consumer tell "agent made no claims" from "agent made
claims and they were all wrong".

The claim analysis layer is informational. It does *not* change
`EvaluationResult.score`, `EvaluationResult.weaknesses`, or
`ComparisonReport.ranking`. The intent is to make agent honesty visible
without conflating it with capability.

## 9. Reporting and comparison

`RunReport` aggregates per-task `EvaluationResult` objects for one agent
on one pack: `total_tasks`, `mean_score`, `weakness_tally`, and the full
ordered `results`. `ComparisonReport` aggregates `RunReport`s across
agents: `agents`, `mean_scores_by_agent`, `ranking`,
`weakness_tally_by_agent`, and the full ordered `reports`.

The Markdown renderer surfaces six sections that together answer the
useful questions a reader has:

* **Ranking** — who is at the top, and by how much.
* **Pairwise summary** — when two agents are compared head-to-head, who
  wins more tasks.
* **Per-task score matrix** — where each agent is strong and weak.
* **Tasks where agents most disagree** — the divergence section makes
  per-task variance explicit.
* **Weakness tally by agent** — which failure modes each agent shows.
* (Combined output) **Agent claim analysis report** — claim reliability
  and overclaim detail, with a standing note that the reliability metric
  is informational.

A one-call helper `build_and_render_verified_comparison_with_claims_markdown(...)`
collapses the verified comparison + claim analysis pipeline into a single
Markdown string for demos.

## 10. CI and engineering discipline

The project ships a GitHub Actions workflow at `.github/workflows/ci.yml`
that triggers on every `push` and `pull_request`, installs the package
with its `dev` extras on Python 3.11 (the project's minimum supported
version), and runs `python -m pytest`. The workflow is deliberately
minimal: no secrets, no real-agent execution, no third-party coverage
upload, no deployment.

Its job is **regression protection** for the evaluation framework itself.
A coding-evaluation framework whose own tests break silently is not
trustworthy as a yardstick for other people's code. The 710-test suite
includes:

* Unit tests for every schema and helper (Weeks 1–3).
* Real-subprocess tests for patch application and pytest execution
  against the shipped `bugfix_005` fixture (Week 4+).
* End-to-end capstones for Week 4 (controlled execution), Week 5
  (unverified ingestion), and Week 6 (verified comparison).
* Structural tests for the CI workflow and the documentation files
  themselves (Week 7 Day 4–5).

This is the kind of discipline a senior engineer should expect from
anything that calls itself an *evaluation* framework: no claim is made
in code that the test suite cannot back up.

## 11. Failure modes handled

Each of these has at least one regression test:

* **Empty diff.** Either rejected (`continue_on_error=False`) or recorded
  as an unverified result with rationale "empty diff_text".
* **Invalid patch.** `git apply` non-zero exit becomes a typed
  `PatchApplyError`; the workspace is untouched, the original fixture is
  untouched, and the failure is reflected in the final result.
* **Semantically wrong patch.** Applies cleanly but fails the real tests.
  No exception is raised — the verified result honestly records
  `passed_public_tests=False` / `passed_hidden_tests=False`.
* **Public pass / hidden fail.** Recorded as `WeaknessCode.ROOT` (symptom
  fix). Score is lower but non-zero.
* **Overclaiming.** Agent claimed pass; framework verified failure. The
  ranking is unaffected; the claim rollup records `overclaims += 1` and
  the agent's `run_id` lands in `mismatch_run_ids`.
* **Missing artifact for a result.** Batch claim analysis raises with
  the offending `run_id` in the message.
* **Missing layout for a task.** With `continue_on_error=True` the
  verifier emits an unverified result with rationale "no layout found";
  with `False`, raises.
* **Duplicate artifact.** Same-agent same-task duplicates raise a typed
  reporting error before any verification work starts.
* **Unknown task.** An artifact whose `task_id` is not in the pack raises
  before any verification work.
* **Unattempted task.** Pack tasks the agent did not attempt become
  unverified results with a "no external agent artifact" rationale.

## 12. Current limitations

* **No real agent execution.** The framework intentionally never invokes
  Claude Code, Codex, ForgeAgent, DGM, or any other agent. Agents run
  outside the framework and drop artifacts.
* **Simulated demo artifacts.** The Week 5/6/7 demos build artifacts
  in-memory or write them to `tmp_path`; there is no shipped recording of
  real agent runs (yet).
* **Sequential verification.** Each artifact is verified one at a time.
  Wall-clock scales with the number of attempted runs.
* **Limited benchmark scope.** One pack (`python_bugfix_basic`) with five
  small Python bug-fix tasks.
* **No CLI.** Demos are invoked via `python -m examples.week7_verified_demo`.
* **No multi-language pack.** Python only.
* **Sandboxing is limited.** Patches are applied in copied workspaces and
  tests run in subprocesses with timeouts, but there is no container or
  seccomp layer.
* **Claim reliability is informational.** It does not change scores or
  weaknesses by default. Consumers who want claim-aware scoring must
  build it on top.

## 13. Future work

* **CLI entry point** (`agenteval verify-demo --artifacts-dir … --pack-dir
  … --output-dir …`) so demo invocation is one line.
* **Multi-task verified demo** spanning all five `bugfix_*` tasks with
  several agents.
* **TypeScript benchmark pack** to prove the layout is language-agnostic.
* **Stronger sandboxing** — containers, ephemeral filesystems, or
  Firecracker-style microVMs for higher-risk benchmarks.
* **Claim-aware scoring policy** — optional `WeaknessCode.FALSE`
  injection for mismatched claims, or a separate reliability-weighted
  ranking.
* **Larger benchmark packs** — more tasks, more diversity, hidden test
  buckets at multiple difficulty tiers.
* **Parallel verification** — `ProcessPoolExecutor` over the per-run
  workspace primitive.
* **Richer CI matrix** — Python 3.11/3.12/3.13 × Ubuntu/Windows/macOS to
  catch subprocess/filesystem regressions.
* **Real external artifact ingestion** — recording and replaying actual
  `agent_run.json` files from Claude Code / Codex / ForgeAgent / DGM
  runs.

## 14. Interview-ready summary

I built **AgentEval Forge**, a Python framework for evaluating agentic
coding systems. It ingests external agent artifacts (`agent_run.json`
files), applies their patches inside isolated copies of benchmark
fixtures, runs the task's public and hidden tests under a controlled
pytest harness, and produces verified `EvaluationResult` objects. Those
results aggregate into per-agent `RunReport`s and a cross-agent
`ComparisonReport` with ranking, pairwise comparison, per-task
divergence, and weakness tally. Alongside that, a claim analysis layer
compares each agent's self-reported test outcomes against what the
framework actually verified, surfacing overclaims, underclaims, and
per-agent claim reliability — without conflating honesty with capability.
The framework is fully tested (710+ pytest tests), CI-guarded on every
push and pull request, and architected around a strict boundary: agents
run outside it, the framework only verifies what it can verify itself,
and agent claims are never treated as evidence.
