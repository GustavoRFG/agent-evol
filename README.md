# AgentEval Forge

AgentEval Forge is an independent evaluation layer for agentic coding systems.
It reviews external run evidence, validates integrity, analyzes patches in a
read-only mode, and produces audit-ready structured verdicts. It can also
verify patches by controlled execution in the existing verified-execution path;
that path is distinct from public evidence review and requires controlled
workspaces.

AgentEval Forge evaluates runs from any coding agent or internal pipeline via a
generic input contract. Claude Code, Codex, ForgeAgent, EvoForge, and private
agent pipelines are clients that can submit evidence; EvoForge is an optional
integration, not the evaluator's input model.

## Product modes

- **Mode A - Evidence Review:** reads a submitted evidence package, validates
  consistency and integrity, analyzes scope/minimality/safety/task alignment,
  and returns a structured verdict. It executes nothing and is safe to expose as
  an independent, audit-friendly review of coding-agent run evidence.
- **Mode B - Sandboxed Verified Execution:** applies patches in controlled
  workspaces and runs tests independently. This stronger guarantee already
  exists as an internal verified-execution path, but exposing it publicly
  requires dedicated sandbox infrastructure.

Mode A never claims submitted code is guaranteed to work. Its promise is:

> Independent, audit-friendly review of coding-agent run evidence.

## Current capabilities

- Generic V1 evidence-review input contract (`schema_version: "1.0"`)
- EvoForge evidence export integration as an optional dialect
- Core dataclasses for tasks, runs, patches, results, and weakness codes
- Unified-diff patch parsing and patch summary reporting
- Claim analysis and claim reliability reporting
- Run reports, comparison reports, and markdown rendering
- Controlled patch workspace and pytest harness for verified execution
- CLI entry points for existing workflows
- GitHub Actions CI running the pytest suite

## Requirements

- Python 3.11+

## Installation (development)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Running the tests

```powershell
pytest
```

## Generic evidence review

Any coding-agent pipeline can submit the generic V1 evidence package described
in [`docs/generic_evidence_review_v1.md`](docs/generic_evidence_review_v1.md).
The generic adapter validates the public contract, parses only unified diffs,
classifies the evidence level, and maps the package into the existing
`TaskSpec`, `AgentRun`, `PatchSummary`, `AgentRunArtifact`, and unverified
evaluation-result path.

Mode A treats caller-supplied test output as evidence, not proof. Claims such as
"all tests passed" are never promoted into verified outcomes unless Mode B
independently executes the tests.

## EvoForge evaluation export

AgentEval Forge can also produce a native, hash-bound external judgment for an
**EvoForge episode** and let EvoForge attach it for governed promotion:

```powershell
python -m agenteval.cli export-evoforge-evaluation `
  --evoforge-run <run-dir> `
  --output <evaluation-json>
```

The exporter reads a persisted EvoForge episode, verifies its run / trace /
artifact hashes (fail-closed), judges the grounded trace evidence
*independently* across correctness, safety, minimality, evidence quality, and an
overall score, and writes a report compatible with EvoForge's `attach-agenteval`
command (schema `0.1`). It evaluates persisted evidence only: it never executes
`commands.log`, applies `patch.diff`, reruns tests, modifies the episode, or
trusts EvoForge's local `eval.json` as its verdict. See
[`docs/evoforge_evaluation_export.md`](docs/evoforge_evaluation_export.md).

## Design document

For an end-to-end synthesis of the framework - problem statement, design goals,
architecture, controlled execution model, verified evaluation pipeline, claim
analysis, reporting, CI, failure modes handled, current limitations, and future
work - see
[`docs/design_of_robust_ai_coding_evaluation_framework.md`](docs/design_of_robust_ai_coding_evaluation_framework.md).

## Continuous integration

GitHub Actions runs the full pytest suite on every `push` and `pull_request`.
The workflow (`.github/workflows/ci.yml`) installs the package with its `dev`
extras on Python 3.11 (the project's minimum supported version) and runs
`python -m pytest`. It exists to protect the evaluation framework from
regressions; it does not execute real coding agents, hit any external
APIs/networks, or upload artifacts to third-party services.

## Project layout

```text
agenteval-forge/
  agenteval/
    agent_runs/       # external run artifacts, ingestion, reporting
    core/             # stable dataclasses and scoring helpers
    execution/        # controlled workspace and pytest harness
    ingest/           # generic public evidence-review adapters
    integrations/     # optional client dialects such as EvoForge
    patches/          # unified-diff parsing and patch summaries
  docs/
  examples/
  tests/
```
