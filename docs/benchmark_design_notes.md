# Benchmark Design Notes

This document describes **how AgentEval Forge designs benchmark tasks**: why
difficulty matters, the difficulty ladder we use, candidate benchmark packs, and
how the same task is reused for cross-agent comparison.

It is a companion to `evaluation_protocol.md`. The protocol says *how* we judge;
these notes say *what* we judge agents on.

---

## 1. Why easy tasks are not enough

A benchmark made only of easy tasks tells you almost nothing useful:

- **Ceiling effect.** If every capable agent scores ~100%, the benchmark cannot
  distinguish between them. There is no signal.
- **Easy tasks reward pattern-matching, not engineering.** A one-line, obvious
  fix can be solved by completing a familiar pattern. It does not exercise
  multi-file reasoning, root-cause analysis, or judgment.
- **Easy tasks hide the failure modes we care about.** Overengineering, false
  success claims, missed edge cases, and destructive actions tend to appear on
  *harder* tasks where the agent has to make decisions.
- **Easy tasks overfit to public tests.** When the public tests fully specify
  the answer, an agent can pass without understanding the problem.

A benchmark earns its value from **discrimination**: tasks spread across a
difficulty range so agents land at different scores, and the *shape* of an
agent's failures becomes visible.

---

## 2. The difficulty ladder

AgentEval Forge organizes tasks into six rungs of increasing difficulty. Each
rung targets a different capability; a complete benchmark pack should include
several rungs.

### Rung 1 — Micro tasks

Single-file, small, well-scoped fixes. One bug, one function. Public tests
mostly specify the fix. Purpose: a sanity floor — an agent that fails here is
broken.

### Rung 2 — Multi-file tasks

The change spans two or more files (e.g. a function signature change plus its
callers, or a model plus its serializer). Tests cross-file reasoning and
consistent edits. Purpose: measures whether the agent keeps a codebase coherent.

### Rung 3 — Hidden-edge-case tasks

The public tests look complete but do not cover important edges (empty input,
boundary values, unicode, concurrency, error paths). Hidden tests do. Purpose:
catches **overfitting** — agents that fix only what they can see.

### Rung 4 — Agentic-trap tasks

Tasks deliberately seeded with traps that exploit known agent weaknesses:

- A tempting but wrong shortcut that passes public tests only.
- An instruction that is easy to skip ("do not modify file X").
- A symptom whose obvious patch hides the real root cause.
- A prompt that invites overengineering or unrequested rewrites.
- A situation where a destructive command looks convenient.

Purpose: directly probes the weakness taxonomy (`INST`, `OVERENG`, `LAZY`,
`FALSE`, `ROOT`, `DESTRUCT`, etc. — see `agenteval/core/schemas.py`).

### Rung 5 — Domain-inspired tasks

Tasks drawn from real problem domains (finance, vision, robotics, education),
requiring some domain reasoning rather than generic code manipulation. Purpose:
tests whether the agent can work against unfamiliar but realistic requirements.

### Rung 6 — Larger repository tasks

A change inside a non-trivial repository where the agent must locate the
relevant code, understand existing structure, and integrate without breakage.
Purpose: tests navigation, context management, and restraint at scale.

---

## 3. Candidate benchmark packs

Each pack groups tasks around a theme and spans several rungs of the ladder.
These are **candidates** — drawn from problem domains familiar to our projects —
not yet implemented tasks. All packs are versioned per the protocol (§6.5).

### Python bugfix basic

Foundational pack. Small to multi-file bugfixes in plain Python: off-by-one
errors, wrong default arguments, incorrect comparisons, mishandled `None`.
Spans rungs 1–3. Establishes the score floor and tests hidden-edge handling.

### DeFi mock

Mock decentralized-finance logic (e.g. a simplified lending pool or token
ledger) — **simulated, no real chain, no real assets**. Tests numeric edge
cases: rounding, overflow, balance invariants. Spans rungs 3–5.

### ArbitrageBot mock

A mock arbitrage strategy over simulated price feeds. Tests reasoning about
state, ordering, and stale-data edge cases. Includes agentic traps where a fix
that passes public tests breaks an invariant checked by hidden tests. Rungs 3–5.

### OMR mock

Optical-mark-recognition mock (e.g. scoring a mock answer sheet from a structured
grid input — no real image processing required). Tests boundary handling:
ambiguous marks, blank rows, malformed input. Rungs 3–5.

### EducGate mock

Mock education-gateway logic: enrollment rules, grade thresholds, access gating.
Rich in instruction-following traps ("students below threshold must not be
enrolled") that probe the `INST` and `ROOT` weaknesses. Rungs 2–5.

### Robotics grader mock

Mock robotics-grading logic: validating a simulated command sequence against
safety and ordering constraints. Tests handling of invalid sequences and
**destructive-action traps** (a convenient command that violates a safety
constraint). Rungs 4–5.

### DGM / ForgeAgent reliability tasks

Tasks aimed at self-improving and in-house agents specifically: reliability,
reproducibility, and honesty under self-referential evaluation. These emphasize
verifying final claims against evidence and detecting `FALSE`/`VERIFY`
weaknesses. Rungs 4–6, and they are the primary input to self-referential
development evaluation (`evaluation_protocol.md` §4).

> All "mock" packs are deliberately self-contained simulations: no network, no
> real funds, no real hardware. This keeps the benchmark safe, deterministic,
> and reproducible, consistent with the project rules in `CLAUDE.md`.

---

## 4. Cross-agent comparison

The core comparison experiment: take **one versioned task** and run it,
unchanged, against every agent of interest:

- Claude Code
- Codex
- ForgeAgent
- DGM original
- DGM modified

Because the task spec and public tests are identical for all five, the resulting
`EvaluationResult` scores are directly comparable. This is what makes the
benchmark answer real questions:

- *Does DGM modified actually beat DGM original?* — compare their scores on the
  same task; a difference is only meaningful if the task version matches.
- *Where does each agent fail?* — compare their recorded weakness codes, not
  just the numbers. Two agents can score 0.7 for very different reasons.
- *Is an improvement real or noise?* — run the comparison across a whole pack
  and multiple task versions before concluding.

Cross-agent comparison depends entirely on the protocol's contamination rules:
same task, withheld hidden tests, recorded artifacts, versioned tasks. Without
them, a "comparison" is just two numbers that were never measured the same way.

---

## Summary

Good benchmark design is about **discrimination and honesty**: a ladder of
difficulty so agents spread out, agentic-trap and hidden-edge tasks so failure
modes become visible, domain-inspired packs so the work is realistic, and one
identical versioned task reused across agents so comparisons mean something.
Easy tasks alone measure nothing.
