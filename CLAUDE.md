# CLAUDE.md

Project instructions for Claude Code sessions working on **AgentEval Forge**.

## What this project is

AgentEval Forge is a Python framework for evaluating agentic coding systems
(e.g. Claude Code, Codex, ForgeAgent). It captures benchmark tasks, agent run
transcripts, patches, test results, structured scores, and failure taxonomies.

The repository is currently at its **first foundational milestone**: core
schemas, scoring helpers, and tests. Keep additions consistent with this small
scope unless the user explicitly asks to expand it.

## Working rules

- **Never claim tests passed unless you actually ran them.** Report the exact
  command output.
- **Prefer small, targeted changes.** Avoid broad rewrites unless explicitly
  requested.
- **Always state which files were changed** in your final response.
- **Run `pytest` after code changes** whenever possible, and report the result.
- **No network calls, secrets, crypto wallets, or destructive commands.**
- Use only the Python standard library for core schemas unless a dependency is
  clearly justified and approved.

## Conventions

- Target Python 3.11+.
- Core data models live in `agenteval/core/schemas.py` as dataclasses and enums.
- Scoring logic lives in `agenteval/core/scoring.py` and must stay simple,
  understandable, and tested.
- Tests live in `tests/` and must pass with `pytest`.

## Validation

After any code change, run:

```powershell
pytest
```

Report the exact result. If tests fail, say so plainly and show the output.
