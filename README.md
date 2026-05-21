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
