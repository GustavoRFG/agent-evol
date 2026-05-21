# AgentEval Forge — Week 1 Day 3 Summary

## Main goal of the day

The goal of Day 3 was to turn the evaluation protocol from Day 2 into the first operational benchmark task format.

Until this point, AgentEval Forge had a conceptual foundation:

- core schemas
- basic scoring
- evaluation protocol
- benchmark design notes

But the framework still did not have a real task format on disk.

Day 3 solved that first gap.

The key idea was:

A benchmark task should not exist only as informal text.  
It should be versioned, stored on disk, loaded by the framework, validated, and converted into a structured Python object.

That is why we introduced the first JSON-based task format.

## Why this matters

The Senior Software Engineer — AI Evaluation role is not only about judging code manually.

It is about building systems that can evaluate coding agents in a reproducible way.

A reproducible evaluation system needs structured inputs.

For AgentEval Forge, the first structured input is the `TaskSpec`.

A `TaskSpec` represents the task given to the agent.

It tells the evaluation framework:

- what the task is
- which benchmark version it belongs to
- where the target repository is
- which public tests are visible
- which hidden tests are reserved for evaluation

This is the first step toward a real benchmark pipeline.

## What we added to the project

We added a `version` field to `TaskSpec`.

This matters because benchmark tasks can change over time.

If a task changes, old results and new results may not be directly comparable.

The version field helps preserve evaluation integrity.

A benchmark result should always be tied to a specific task version.

This connects directly to the evaluation protocol from Day 2.

## New benchmark loader package

We created a new package:

```text
agenteval/benchmarks