# AgentEval Forge — Week 1 Day 1 Summary

Today we started the practical project that will support my preparation for the Senior Software Engineer — AI Evaluation role.

The project is called **AgentEval Forge**.

AgentEval Forge is a practical Python framework for evaluating coding agents such as Claude Code, Codex, and ForgeAgent. The goal is to measure whether an agent actually solves a repository-level software engineering task, instead of merely producing a confident or plausible final message.

The motivation comes directly from the role requirements. The job is about designing coding benchmarks, building evaluation pipelines, analyzing AI-generated code, detecting failure patterns, and providing detailed technical feedback on model behavior. Instead of studying those ideas only in theory, we are building a real system that implements them.

The central idea is simple:

AgentEval Forge evaluates coding agents by combining task specifications, agent run evidence, patch analysis, test execution, scoring, weakness taxonomies, and structured reports.

In the first practical milestone, we created the initial repository foundation. The repository now contains a Python package, a README, project instructions for Claude Code, core schemas, a basic scoring module, and pytest tests.

The initial files include:

- `README.md`
- `CLAUDE.md`
- `pyproject.toml`
- `.gitignore`
- `agenteval/__init__.py`
- `agenteval/core/__init__.py`
- `agenteval/core/schemas.py`
- `agenteval/core/scoring.py`
- `tests/test_schemas.py`
- `tests/test_scoring.py`

The core schemas define the first structured concepts of the framework:

- `TaskSpec`, which represents the coding task given to an agent.
- `AgentRun`, which represents what the agent did.
- `PatchSummary`, which summarizes the files and diff produced by the agent.
- `EvaluationResult`, which stores the outcome of the evaluation.
- `WeaknessCode`, which represents structured failure categories such as instruction-following failures, false claims, lack of verification, root-cause failures, hallucinated code, file issues, and overengineering.

We also created a small scoring module. The first scoring model is intentionally simple. It rewards passing public and hidden tests and applies penalties for recorded weaknesses. This is not meant to be the final scoring system. It is a first understandable baseline that can evolve later.

A key part of the project is `CLAUDE.md`. This file gives project-level instructions to Claude Code. It tells the agent to make small targeted changes, avoid broad rewrites, avoid destructive commands, avoid secrets or network calls, report changed files, and never claim that tests passed unless they were actually run.

This is important because Claude Code is not only helping develop the project. It is also becoming one of the agents that the project is designed to evaluate.

That makes AgentEval Forge self-referential:

Claude Code can help build the evaluation framework, and then the framework can be used to evaluate Claude Code-like behavior.

During this first day, Claude Code created the initial foundation. Then we independently validated the result.

The tests passed:

`19 passed`

We also confirmed that the UTF-8 issue in the PowerShell output was not a file corruption problem. It was only a terminal encoding display issue. After switching the terminal to UTF-8, the README displayed correctly.

We also encountered a Git safety warning related to repository ownership. This was resolved by adding the project directory as a safe Git directory.

Finally, we created the first local Git commit:

`Initialize AgentEval Forge foundation`

This commit is local only. It has not been pushed to GitHub yet.

The main lesson from Day 1 is that this preparation will not be purely theoretical. Every requirement in the job description will become a concrete feature or design decision in AgentEval Forge.

The project maps directly to the role:

- Coding benchmarks become benchmark task definitions.
- Data pipelines become task ingestion, agent run capture, scoring, and reports.
- AI-generated code analysis becomes patch validation and quality checks.
- Structured evaluation scenarios become benchmark packs with public and hidden tests.
- Technical feedback becomes Markdown and JSON evaluation reports.
- Evaluation frameworks become the AgentEval Forge system itself.
- Python expertise is developed through the implementation.
- CI/CD and robust tests will come through pytest and GitHub Actions.

The most important interview answer from Day 1 is:

“AgentEval Forge is a practical framework for evaluating coding agents such as Claude Code, Codex, and ForgeAgent. I built it to study and implement the core ideas behind AI evaluation and coding benchmarks: defining task specs, capturing agent run evidence, analyzing patches, running tests, applying weakness taxonomies, computing scores, and generating structured reports. The key goal is to determine whether an agent actually solved a repository-level coding task, rather than simply producing a plausible final message.”

This is the foundation for the rest of the project.

Next, we will continue by making the core schemas persistent, probably with JSON serialization, or by starting the first patch validator. Both directions move us closer to a real evaluation pipeline for coding agents.