# Design of a Robust AI Coding Evaluation Framework — Short Summary

## Overview

AgentEval Forge is a Python framework for evaluating autonomous coding agents.

Its main purpose is to verify whether an agent actually solved a coding task, instead of trusting the agent's final message or self-reported claims.

The framework is designed around one core principle:

Agent claims are not evidence.

Only framework-verified execution counts as evidence.

## Problem

Coding agents can produce convincing but wrong outputs.

Common failure modes include:

- plausible patches that do not fix the real bug

- public-test-only fixes

- overclaiming success

- claiming tests passed when no reliable verification happened

- final answers that look good but are not backed by evidence

- inconsistent comparison between agents

A robust evaluator needs tasks, fixtures, patches, tests, structured evidence, reports, and comparison tools.

## Design goals

AgentEval Forge is designed for:

- reproducibility

- controlled execution

- public and hidden tests

- external artifact ingestion

- verified evidence

- claim non-trust

- multi-agent comparison

- auditability

- extensibility

The framework separates agent execution from evaluation.

Agents run outside the framework.

The framework ingests their artifacts and verifies them.

## High-level architecture

The verified evaluation flow is:

External agent to agent_run.json to AgentRunArtifact to fixture layout to copied workspace to patch application to public and hidden tests to TaskEvidence to EvaluationResult to RunReport to ComparisonReport to combined Markdown report A separate claim-analysis path compares what the agent claimed with what the framework verified.

## Benchmark design

Benchmarks are organized as BenchmarkPacks.

Each pack contains TaskSpec objects.

A task includes:

- task ID

- title

- version

- description

- repo fixture path

- public tests

- hidden tests

Public tests check visible behavior.

Hidden tests check whether the underlying bug was actually fixed.

This helps distinguish shallow symptom fixes from real root-cause fixes.

## Controlled execution

Patch verification happens in isolated copied workspaces.

The original benchmark fixture is never modified.

The framework:

- copies the fixture

- applies the diff with git apply

- rejects unsafe paths

- runs public pytest nodes

- runs hidden pytest nodes

- captures subprocess output

- applies timeouts

- converts outcomes into structured evidence

This keeps evaluation reproducible and safer.

## External agent artifacts

AgentEval Forge does not execute agents directly.

Instead, agents produce agent_run.json files.

Each AgentRunArtifact can contain:

- agent name

- task ID

- run ID

- diff text

- final message

- transcript text

- claimed commands

- claimed public test result

- claimed hidden test result

- metadata

This makes the framework agent-agnostic.

Claude Code, Codex, ForgeAgent, DGM, or any other tool can be evaluated if it produces the expected artifact format.

## Verified evaluation pipeline

A verified result is created only when the framework applies the patch and runs tests.

The core path is:

AgentRunArtifact to ingest_agent_run_artifact to verify_ingested_agent_run to copy_fixture_apply_patch_and_build_evidence to build_task_evidence_from_pytest_results to build_evaluation_result to EvaluationResult

If verification fails, the result can be recorded as unverified or failed, depending on configuration.

Agent claims are never used to decide pass/fail.

## Claim analysis

The framework compares agent claims with verified outcomes.

It can detect:

- matching claims

- mismatching claims

- overclaims

- underclaims

- missing claims

Example:

Agent claimed public tests passed: True

Framework verified public tests passed: False

Result: mismatch / overclaim

Claim reliability is informational.

It does not change the main score or ranking by default.

## Reporting and comparison

EvaluationResult objects are aggregated into RunReports.

RunReports are aggregated into ComparisonReports.

The comparison report includes:

- ranking

- pairwise comparison

- per-task score matrix

- disagreement / divergence section

- weakness tally

- claim analysis rollup

The combined Markdown report makes the evaluation easy to inspect.

## CI and engineering discipline

The project includes GitHub Actions CI.

On every push and pull request, CI:

- sets up Python 3.11 - installs the project with dev dependencies - runs python -m pytest This protects the framework from regressions.

It also reinforces the engineering discipline expected from a serious evaluation system.

## Failure modes handled

The framework has tests for cases such as:

- empty diff

- invalid patch

- semantically wrong patch

- public pass but hidden fail

- overclaiming

- missing artifact

- missing layout

- duplicate artifact

- unknown task

- unattempted task

Each failure mode is represented explicitly instead of being hidden.

## Current limitations

The framework does not execute real agents directly.

The demos use simulated artifacts.

Verification is sequential.

The benchmark scope is still small.

There is no CLI yet.

There is no TypeScript benchmark pack yet.

Sandboxing is limited to copied workspaces, subprocess boundaries, and timeouts.

Claim reliability does not affect score by default.

## Future work

Possible next steps include:

- CLI entry point

- multi-task verified demo

- TypeScript benchmark pack

- stronger sandboxing

- claim-aware scoring policy

- larger benchmark packs

- parallel verification

- richer CI matrix

- real recorded artifacts from Claude Code, Codex, ForgeAgent, and DGM

## Interview-ready summary

I built AgentEval Forge, a Python framework for evaluating agentic coding systems.

It ingests external agent artifacts, applies patches inside isolated benchmark workspaces, runs public and hidden tests, builds verified evidence, compares agents, and analyzes whether agent claims match verified outcomes.

The key principle is that agent claims are not evidence.

The framework only trusts what it can verify through controlled execution.