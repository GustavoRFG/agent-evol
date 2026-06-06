# AgentEval Forge Product Modes

AgentEval Forge has two evaluation paths with different guarantees. They must
be named distinctly in documentation, output, and product language.

## Mode A - Evidence Review

Mode A reads a submitted evidence package, validates internal consistency and
integrity, analyzes the patch and evidence quality, and returns a structured
verdict.

Mode A executes nothing:

- no patch application;
- no command replay;
- no test execution;
- no network calls;
- no mutation of client workspaces.

Mode A is safe to expose as the public evidence-review surface. Its commercial
promise is:

> Independent, audit-friendly review of coding-agent run evidence.

Mode A may assess:

- whether the package satisfies the declared schema;
- which files the patch appears to change;
- whether the patch appears small or broad;
- whether caller claims are internally consistent with supplied logs;
- whether supplied hashes bind the submitted package;
- whether visible evidence contains safety or review signals.

Mode A must not claim:

- submitted code is guaranteed to work;
- tests truly passed unless AgentEval Forge independently ran them;
- the original execution was truthful;
- hash binding proves provenance or author honesty.

## Mode B - Sandboxed Verified Execution

Mode B applies a patch in an isolated workspace and runs tests independently.
This is the stronger verified-execution path.

Mode B can support claims such as independently reproduced test outcomes, but it
requires real sandbox infrastructure before public exposure. Mode B is not the
generic public input surface introduced by the V1 evidence-review adapter.

## Evidence Levels

### Level 0 - `patch_only_review`

Input contains task text and a unified diff only.

May claim:

- the package is structurally valid;
- patch scope and minimality were reviewed from the diff;
- apparent task alignment and safety signals were inspected.

Must not claim:

- tests passed;
- execution happened;
- code correctness was verified.

### Level 1 - `self_reported_execution_evidence`

Input includes caller-supplied claims and/or test evidence.

May claim:

- caller-supplied execution evidence was reviewed;
- claims and logs appear internally consistent or inconsistent;
- evidence quality is higher than patch-only review.

Must state:

- the test evidence was supplied by the caller;
- AgentEval Forge did not independently reproduce execution.

Must not claim:

- the tests truly passed;
- the execution log is truthful.

### Level 2 - `hash_bound_evidence_review`

Input includes a sha256 integrity manifest that verifies against the submitted
evidence package.

May claim:

- the submitted package is internally consistent;
- the reviewed evidence is hash-bound and auditable;
- the package has not changed since the manifest was produced.

Must state:

- hash binding proves integrity, not origin veracity.

Must not claim:

- the original run was truthful;
- the submitting client is trusted;
- tests were independently reproduced.

### Level 3 - `independently_verified_execution`

Reserved for Mode B. Not selectable by the generic V1 Mode A adapter.

Level 3 requires AgentEval Forge to independently apply the patch and execute
verification commands inside a controlled sandbox.
