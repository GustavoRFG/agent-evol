# AgentEval Forge

AgentEval Forge is a practical Python framework for **evaluating agentic coding
systems** — autonomous agents that read, write, and modify code to complete
software engineering tasks.

It is designed to evaluate agents such as **Claude Code**, **Codex**, and
**ForgeAgent**: feeding them benchmark tasks, capturing their run transcripts and
patches, running tests, and producing structured scores and failure analyses.

## Why

Coding agents are easy to demo and hard to measure. AgentEval Forge aims to make
agent quality *comparable* and *reproducible* by treating each evaluation as
structured data: a task spec, an agent run, a patch summary, test results, a
numeric score, and a taxonomy of weaknesses.

## Planned scope

Eventually the framework should support:

- Benchmark task definitions
- Agent run transcripts and command logs
- Patch summaries (changed / added / deleted files, diffs)
- Public and hidden test results
- Structured numeric scoring
- A failure taxonomy (weakness codes)
- Evaluation reports

## First milestone

This repository starts as a **minimal foundation only**. The first milestone is
deliberately small:

1. **Schemas** — core dataclasses and enums describing tasks, runs, patches,
   evaluation results, and weakness codes (`agenteval/core/schemas.py`).
2. **Scoring** — a small, understandable scoring helper that rewards passed
   tests and penalizes weaknesses (`agenteval/core/scoring.py`).
3. **Tests** — pytest tests covering the schemas and scoring logic.

No web app, dashboard, database, agent runner, or CI workflow is included yet.

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

## EvoForge evaluation export

AgentEval Forge can produce a native, hash-bound external judgment for an
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
command (schema `0.1`). It evaluates persisted evidence only — it never executes
`commands.log`, applies `patch.diff`, reruns tests, modifies the episode, or
trusts EvoForge's local `eval.json` as its verdict. See
[`docs/evoforge_evaluation_export.md`](docs/evoforge_evaluation_export.md).

## Design document

For an end-to-end synthesis of the framework — problem statement, design
goals, architecture, controlled execution model, verified evaluation
pipeline, claim analysis, reporting, CI, failure modes handled, current
limitations, and future work — see
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
    core/
      schemas.py    # dataclasses and enums
      scoring.py    # scoring helpers
  tests/
    test_schemas.py
    test_scoring.py
```
