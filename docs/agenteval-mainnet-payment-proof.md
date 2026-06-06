# AgentEval Forge — Base Mainnet Paid Evidence-Review Proof

The AgentEval Forge paid Mode A evidence-review endpoint was exercised once on
Base mainnet with a real x402 USDC payment. The on-chain transfer was confirmed
on basescan under the receiver's ERC-20 **Token Transfers** tab (the EIP-3009
transfer is submitted by the CDP facilitator, so it appears under token
transfers rather than the buyer's normal transactions list).

All values below are taken from the actual run and the confirmed on-chain
transaction. No values are estimated or invented.

## Transaction

| Field | Value |
| --- | --- |
| Transaction hash | `0x254f376bad7c71c61b5a3ffa66ae40f42fd4c563bb4bfccf54b1d57d2fe8f1fd` |
| Network | `eip155:8453` (Base mainnet) |
| Asset | USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) |
| Amount | 0.01 USDC (`10000` atomic, 6 decimals) |
| From (buyer) | `0xf75d...F392` |
| To (receiver, distinct from buyer) | `0x2986...fe71` |

The buyer and receiver are distinct wallets, so the payment is a genuine
buyer→seller transfer (no self-send).

## Endpoint result

| Field | Value |
| --- | --- |
| Endpoint | `POST /paid/evaluate-agent-run` |
| Paid HTTP status | 200 |
| Mode | `evidence_review` (Mode A) |
| Evidence level | `self_reported_execution_evidence` |
| Verdict | `requires_review` |
| `verified_pass` claimed | No |

## Verification

- Confirmed on basescan via the receiver's **Token Transfers (ERC-20)** tab.
- Look up the transaction hash above on basescan for block, timestamp, and the
  facilitator-submitted transfer details.

## Scope

This is an operational production proof only. The endpoint runs in Mode A
(evidence review): it never applies submitted patches, never runs submitted
tests, and never claims `verified_pass`. Exactly one payment-bearing request was
made; no retry.
