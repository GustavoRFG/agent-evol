# Evaluation Protocol

This document defines **how AgentEval Forge evaluates coding agents**. It is the
authoritative description of roles, judging rules, test categories, evaluation
modes, and contamination controls.

The single most important concern this protocol addresses is **self-benchmark
bias**: if one agent designs the benchmark, solves the task, sees every test,
and then grades itself, the resulting score is not trustworthy. The protocol
exists to keep evaluation *honest* and *reproducible*.

---

## 1. Three separate roles

AgentEval Forge keeps three responsibilities strictly separate. Conflating any
two of them is what produces inflated, meaningless scores.

### Agent under test

The coding agent being measured (e.g. Claude Code, Codex, ForgeAgent). It
receives a task spec and a repository, performs work, runs commands, and
produces a patch plus a final message. It **only ever sees what a real user
would see**: the task description and the public tests. It never sees hidden
tests, scoring rubrics, or the evaluation code.

### Evaluation framework

The neutral machinery — AgentEval Forge itself. It presents tasks, captures
transcripts, applies patches, runs public *and* hidden tests, records every
artifact, and computes structured scores. It is deterministic where possible
and does not "reason" about whether the agent did well; it measures.

### Human reviewer

A person who inspects the recorded artifacts (transcript, patch, test output,
final message) and assigns judgments the framework cannot reliably automate:
root-cause quality, instruction adherence, overengineering, false claims. The
human reviewer is the **final authority** on disputed or qualitative outcomes.

> Rule of thumb: the agent *acts*, the framework *measures*, the human *judges*.

---

## 2. Why an agent must not be the final judge of its own output

An agent grading its own work has a structural conflict of interest. Specific
failure modes:

- **Optimistic self-assessment.** Agents tend to report success ("all tests
  pass", "the bug is fixed") even when evidence is incomplete or contradicts it.
- **Test visibility leakage.** If the agent can see the tests it will be graded
  on, it can write code that satisfies those exact tests without solving the
  underlying problem (overfitting to the rubric).
- **Rubric gaming.** An agent that knows the scoring formula can optimize the
  score rather than the task.
- **No independent ground truth.** Self-judgment has nothing to check against;
  hidden tests and human review provide that ground truth.

Therefore: **scores are produced by the framework and the human reviewer, never
by the agent under test.** An agent's own final message is treated as a *claim
to be verified*, not as evidence.

This applies even when the agent under test is Claude Code and the framework was
also built with Claude Code — the *roles* are separated, not the vendor.

---

## 3. Test and judgment categories

Evaluation evidence comes from four distinct sources. They are not
interchangeable; each catches different problems.

| Category | Visible to agent? | Produced by | Catches |
|---|---|---|---|
| **Public tests** | Yes | Task author | Obvious correctness; given to the agent as part of the task |
| **Hidden tests** | No | Task author / framework | Overfitting, missed edge cases, shallow fixes |
| **Human review** | n/a | Human reviewer | Root cause, instruction adherence, overengineering, false claims |
| **Structured scoring** | No | Evaluation framework | A reproducible numeric summary combining the above |

- **Public tests** ship with the task. They tell the agent what "done" looks
  like at a basic level. Passing them is necessary but not sufficient.
- **Hidden tests** are run by the framework *after* the agent finishes. The
  agent must never see them, or they stop measuring generalization.
- **Human review** covers what tests cannot: did the agent fix the *cause* or
  just silence a symptom? Did it follow instructions? Did it claim things that
  the transcript does not support?
- **Structured scoring** is the framework's numeric output (see
  `agenteval/core/scoring.py`). It rewards passed tests and penalizes recorded
  weaknesses, producing a comparable, clamped `[0.0, 1.0]` score.

---

## 4. Evaluation modes

AgentEval Forge supports four modes. They share the same artifacts and
contamination rules; they differ in how many agents/tasks are involved and what
question they answer.

### Single-agent evaluation

One agent, one task. Question: *how well did this agent do this task?*
Produces one `EvaluationResult`. The baseline mode.

### Pairwise evaluation

Two agents, the **same task**, compared directly. Question: *which agent did
better, and why?* Useful for A/B decisions (e.g. Claude Code vs. Codex on an
identical bugfix). Comparison is only valid when both agents saw exactly the
same task spec and public tests.

### Multi-agent benchmark

Many agents across many tasks. Question: *how do agents rank across a benchmark
pack?* Produces a matrix of results that supports leaderboards and trend
tracking. Requires versioned tasks so runs stay comparable over time.

### Self-referential development evaluation

The case where the agent under test is also (a version of) the agent that helps
build AgentEval Forge — or a self-improving system like a DGM variant evaluating
its own descendants. This mode carries the **highest contamination risk** and
demands the strictest discipline:

- Hidden tests and rubrics are authored or audited by a *different* party than
  the agent under test.
- A human reviewer signs off on every result.
- The task version and framework version are both pinned and recorded.
- Self-reported success is always cross-checked against artifacts.

This mode is allowed, but its scores are only as trustworthy as the role
separation around it.

---

## 5. Example agents

The protocol is agent-agnostic. Concrete examples currently in scope:

- **Claude Code** — Anthropic's CLI coding agent.
- **Codex** — an OpenAI-family coding agent.
- **ForgeAgent** — our in-house agent.
- **DGM original** — a baseline Darwin-Gödel-Machine-style self-improving agent,
  unmodified.
- **DGM modified** — a variant of the DGM with changes we want to measure
  against the original.

A typical comparison run evaluates all five on the same task to see whether a
modification actually helps (see §4 multi-agent benchmark and
`benchmark_design_notes.md` §4).

---

## 6. Rules for avoiding benchmark contamination

These rules are mandatory. A run that violates any of them produces a score that
must be marked **untrusted**.

1. **Never expose hidden tests to the agent under test.** Hidden tests, scoring
   rubrics, and evaluation code are withheld. The agent sees only the task spec
   and public tests.
2. **Record every artifact.** For each run, persist: the task spec, the patch
   (changed/added/deleted files + diff), the full transcript, the list of
   commands run, all test outputs (public and hidden), and the agent's final
   message. Evaluation without recorded evidence is not valid.
3. **Verify final claims against evidence.** The agent's final message is a
   claim. If it says "all tests pass," the framework and reviewer confirm this
   against actual test output. Unsupported claims are recorded as the `FALSE`
   weakness.
4. **Compare agents on the same task.** Cross-agent comparison is only
   meaningful when each agent received an identical task spec and identical
   public tests. Do not compare scores from different task versions.
5. **Keep benchmark tasks versioned.** Every task has a version identifier.
   Changing a task (new hidden test, reworded description) creates a new
   version. Results record the task version so old and new runs are never
   silently mixed.
6. **Separate authorship from solving.** Whenever feasible, the party that
   authors a task's hidden tests is not the agent that will be evaluated on it.
   In self-referential mode this separation is enforced by a human reviewer.

---

## Summary

Honest evaluation comes from **role separation** (agent acts, framework
measures, human judges), **withheld ground truth** (hidden tests + review the
agent cannot see), **recorded evidence** (every artifact persisted and claims
verified), and **stable comparison** (same versioned task across agents). The
agent under test is never the final judge of its own output.
