# AgentEval Forge — Public Bazaar Pilot Proof

## Summary

AgentEval Forge Mode A was exposed publicly through a local-first ngrok HTTPS tunnel and cataloged successfully in the CDP x402 Bazaar.

## Architecture

Internet
→ ngrok HTTPS public URL
→ local TypeScript x402 seller
→ Python AgentEval Forge Mode A evidence-review core
→ structured JSON verdict

## Public endpoint

- Route: `POST /paid/evaluate-agent-run`
- Network: Base mainnet (`eip155:8453`)
- Asset: native Base USDC
- Price: `0.01 USDC` (`10000` atomic units)
- Mode: `evidence_review`
- Evidence level: `self_reported_execution_evidence`
- Verdict: `requires_review`
- `verified_pass` claimed: `No`

## Public smoke result

The public HTTPS endpoint completed the expected x402 flow:

- unpaid request → HTTP `402 Payment Required`
- exactly one payment-bearing request
- paid request → HTTP `200 OK`
- Mode A evidence-review verdict returned
- no submitted patch was applied
- no submitted test command was executed
- no `verified_pass` claim was returned

## Bazaar discovery result

The endpoint was indexed successfully by the CDP x402 Bazaar.

Confirmed through:

- merchant lookup by `payTo` address;
- filtered search by `payTo`;
- filtered search by `payTo` and Base mainnet network;
- semantic search for `coding-agent run evidence`.

The indexed metadata includes:

- a natural-language description;
- price and Base mainnet payment metadata;
- JSON input schema;
- JSON output example;
- explicit read-only safety boundary;
- `discoverable: true`.

## Secret separation

The public seller loads:

`paid-service/.env`

The supervised local smoke client loads:

`paid-service/.env.smoke`

The seller environment does not require or load `BUYER_PRIVATE_KEY`.

Both local env files are gitignored and must never be committed.

## Availability boundary

This is an experimental local-first public pilot.

The service is available only while:

- the local seller process is running;
- the ngrok tunnel is running;
- the host computer is online;
- the local internet connection is available.

This milestone proves technical viability and public discoverability. It does not yet prove external demand or production-grade availability.
