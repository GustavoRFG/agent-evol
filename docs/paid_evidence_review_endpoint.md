# Paid Evidence Review Endpoint

Milestone 2 exposes AgentEval Forge Mode A evidence review as an x402-paid
HTTP endpoint.

## Boundary choice

Chosen option: **B - TypeScript x402 seller + Python evaluator subprocess**.

The available, proven x402 server tooling in the existing payment lab is the
TypeScript `@x402/express` resource-server pattern. AgentEval Forge's evaluator
stays Python-native and unchanged; the payment service calls it through:

```powershell
python -m agenteval.ingest.serve
```

The boundary reads one JSON object from stdin and writes one JSON object to
stdout. It executes no submitted code, applies no patch, runs no tests, and
makes no network calls.

## Route

```text
POST /paid/evaluate-agent-run
```

Default network:

```text
eip155:84532
```

Build-phase price:

```text
$0.01 / 10000 atomic USDC
```

Mode:

```text
evidence_review
```

The route accepts the generic V1 evidence package documented in
[`generic_evidence_review_v1.md`](generic_evidence_review_v1.md). It returns the
Mode A verdict JSON produced by `evaluate_generic_agent_run`.

## Charging behavior

Malformed evidence packages are validated before x402 settlement. Invalid input
returns HTTP `400` with a sanitized error and is not charged in the pilot.

Valid unpaid input returns HTTP `402` with the x402 challenge. Valid paid input
returns HTTP `200` and the Mode A verdict.

## Guarantees

The paid endpoint provides independent, audit-friendly review of coding-agent
run evidence. It does not claim verified execution and never returns
`verified_pass` in Mode A.

Mode B sandboxed execution remains out of scope for this endpoint.
