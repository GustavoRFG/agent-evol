import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { registerExactEvmScheme } from "@x402/evm/exact/client";
import { wrapFetchWithPayment, x402Client } from "@x402/fetch";
import { config as loadDotenv } from "dotenv";
import { privateKeyToAccount } from "viem/accounts";

const moduleDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(moduleDir, "..", "..");
loadDotenv({ path: resolve(repoRoot, "paid-service", ".env"), quiet: true });

const PAID_ROUTE = "/paid/evaluate-agent-run" as const;
const TESTNET_NETWORK = "eip155:84532" as const;
const TESTNET_USDC_ADDRESS =
  "0x036CbD53842c5426634e7929541eC2318f3dCF7e" as const;
const MAINNET_NETWORK = "eip155:8453" as const;
const MAINNET_USDC_ADDRESS =
  "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" as const;

// Single source of truth for the active network. Testnet is the default; Base
// mainnet is strictly opt-in via X402_USE_MAINNET=1. Every non-network safety
// guard below applies identically on both networks.
const USE_MAINNET = process.env.X402_USE_MAINNET === "1";
const ACTIVE_NETWORK = USE_MAINNET ? MAINNET_NETWORK : TESTNET_NETWORK;
const ACTIVE_USDC_ADDRESS = USE_MAINNET
  ? MAINNET_USDC_ADDRESS
  : TESTNET_USDC_ADDRESS;

const PAYMENT_AMOUNT_ATOMIC = "10000" as const;
const PAYMENT_AMOUNT_USD = "0.01" as const;
const MAX_PAYMENT_BEARING_REQUESTS = 1;
const USDC_DECIMALS = 6;

const RESOURCE_SERVER_URL = (
  process.env.RESOURCE_SERVER_URL ?? "http://localhost:4081"
).replace(/\/+$/, "");
const BUYER_PRIVATE_KEY = process.env.BUYER_PRIVATE_KEY ?? "";
const SELLER_RECEIVER_ADDRESS = process.env.SELLER_RECEIVER_ADDRESS ?? "";
const MAX_PAYMENT_USD = Number.parseFloat(
  process.env.MAX_PAYMENT_USD ?? PAYMENT_AMOUNT_USD,
);

interface AcceptEntry {
  scheme?: string;
  network?: string;
  amount?: string;
  maxAmountRequired?: string;
  asset?: string;
  payTo?: string;
  extra?: Record<string, unknown> & {
    name?: string;
    asset?: string;
    assetAddress?: string;
    tokenAddress?: string;
    contractAddress?: string;
  };
}

interface PaymentRequiredEnvelope {
  accepts?: AcceptEntry[];
}

function decodePaymentRequiredHeader(value: string): PaymentRequiredEnvelope {
  try {
    return JSON.parse(Buffer.from(value, "base64").toString("utf-8"));
  } catch (error) {
    throw new Error(
      `Failed to decode PAYMENT-REQUIRED header: ${(error as Error).message}`,
    );
  }
}

function atomicUsdcToUsd(amount: string | undefined): string {
  if (!amount) return "";
  try {
    const atomic = BigInt(amount);
    const whole = atomic / 1_000_000n;
    const fractional = (atomic % 1_000_000n).toString().padStart(6, "0");
    return `${whole}.${fractional}`.replace(/\.?0+$/, "");
  } catch {
    return "";
  }
}

function paymentAssetAddress(entry: AcceptEntry): string | undefined {
  const candidates = [
    entry.asset,
    entry.extra?.asset,
    entry.extra?.assetAddress,
    entry.extra?.tokenAddress,
    entry.extra?.contractAddress,
  ];
  return candidates.find((value): value is string => {
    return typeof value === "string" && value.startsWith("0x");
  });
}

function selectUsdcAccept(
  envelope: PaymentRequiredEnvelope,
  network: string,
  usdcAddress: string,
): AcceptEntry {
  const accepts = envelope.accepts ?? [];
  const matching = accepts.filter((entry) => {
    return (
      entry.network === network &&
      paymentAssetAddress(entry)?.toLowerCase() === usdcAddress.toLowerCase()
    );
  });
  if (matching.length === 0) {
    throw new Error(`No USDC payment rail was advertised for ${network}.`);
  }
  return matching.reduce((a, b) => {
    const aUsd = Number.parseFloat(
      atomicUsdcToUsd(a.amount ?? a.maxAmountRequired),
    );
    const bUsd = Number.parseFloat(
      atomicUsdcToUsd(b.amount ?? b.maxAmountRequired),
    );
    return aUsd <= bUsd ? a : b;
  });
}

const X402_PAYMENT_HEADER_NAMES = ["payment-signature", "x-payment"] as const;

function containsPaymentHeader(headers?: HeadersInit): boolean {
  if (!headers) return false;
  const hasName = (name: string): boolean =>
    X402_PAYMENT_HEADER_NAMES.includes(
      name.trim().toLowerCase() as (typeof X402_PAYMENT_HEADER_NAMES)[number],
    );

  if (headers instanceof Headers) {
    let found = false;
    headers.forEach((_value, name) => {
      if (hasName(name)) found = true;
    });
    return found;
  }
  if (Array.isArray(headers)) {
    return headers.some((entry) => hasName(String(entry[0])));
  }
  return Object.keys(headers).some(hasName);
}

function createPaymentBearingGuard() {
  let paymentBearingRequests = 0;
  return {
    inspect(input: RequestInfo | URL, init?: RequestInit): void {
      if (containsPaymentHeader(init?.headers)) paymentBearingRequests += 1;
      if (input instanceof Request && containsPaymentHeader(input.headers)) {
        paymentBearingRequests += 1;
      }
      if (paymentBearingRequests > MAX_PAYMENT_BEARING_REQUESTS) {
        throw new Error("refusing more than one payment-bearing HTTP request");
      }
    },
    count(): number {
      return paymentBearingRequests;
    },
  };
}

async function loadExampleRequest(): Promise<string> {
  return readFile(
    resolve(repoRoot, "examples", "generic_evidence_review_request.json"),
    "utf8",
  );
}

async function main(): Promise<void> {
  if (USE_MAINNET) {
    console.log(
      "network mode: MAINNET — Base mainnet is a REAL-MONEY path; " +
        "a successful run will move real USDC.",
    );
  }
  if (!BUYER_PRIVATE_KEY.startsWith("0x") || BUYER_PRIVATE_KEY.length < 66) {
    throw new Error("BUYER_PRIVATE_KEY is required for paid smoke.");
  }
  if (!SELLER_RECEIVER_ADDRESS.startsWith("0x")) {
    throw new Error("SELLER_RECEIVER_ADDRESS is required for paid smoke.");
  }

  const signer = privateKeyToAccount(BUYER_PRIVATE_KEY as `0x${string}`);
  if (signer.address.toLowerCase() === SELLER_RECEIVER_ADDRESS.toLowerCase()) {
    throw new Error("Seller receiver must differ from buyer address.");
  }

  const body = await loadExampleRequest();
  const unpaidResponse = await fetch(`${RESOURCE_SERVER_URL}${PAID_ROUTE}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-AgentEval-Request-Id": crypto.randomUUID(),
    },
    body,
  });

  if (unpaidResponse.status !== 402) {
    throw new Error(`Expected unpaid HTTP 402; got ${unpaidResponse.status}.`);
  }
  const paymentRequired = unpaidResponse.headers.get("payment-required");
  if (!paymentRequired) {
    throw new Error("Unpaid response did not include PAYMENT-REQUIRED.");
  }

  const accept = selectUsdcAccept(
    decodePaymentRequiredHeader(paymentRequired),
    ACTIVE_NETWORK,
    ACTIVE_USDC_ADDRESS,
  );
  const amountAtomic = accept.amount ?? accept.maxAmountRequired ?? "";
  const amountUsd = atomicUsdcToUsd(amountAtomic);

  if (amountAtomic !== PAYMENT_AMOUNT_ATOMIC || amountUsd !== PAYMENT_AMOUNT_USD) {
    throw new Error("Advertised payment amount does not match build price.");
  }
  if (Number.parseFloat(amountUsd) > MAX_PAYMENT_USD) {
    throw new Error("Advertised payment amount exceeds MAX_PAYMENT_USD.");
  }

  const client = new x402Client();
  registerExactEvmScheme(client, { signer, networks: [ACTIVE_NETWORK] });

  const guard = createPaymentBearingGuard();
  const guardedFetch: typeof fetch = async (input, init) => {
    guard.inspect(input, init);
    return fetch(input, init);
  };
  const fetchWithPayment = wrapFetchWithPayment(guardedFetch, client);

  const paidResponse = await fetchWithPayment(`${RESOURCE_SERVER_URL}${PAID_ROUTE}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-AgentEval-Request-Id": crypto.randomUUID(),
    },
    body,
  });
  const verdict = (await paidResponse.json()) as Record<string, unknown>;
  const verdictText = JSON.stringify(verdict);

  if (paidResponse.status !== 200) {
    throw new Error(`Expected paid HTTP 200; got ${paidResponse.status}.`);
  }
  if (verdict.mode !== "evidence_review") {
    throw new Error("Paid response was not a Mode A evidence-review verdict.");
  }
  if (verdictText.includes("verified_pass")) {
    throw new Error("Mode A response must not claim verified_pass.");
  }

  console.log("RESULT: AGENTEVAL_PAID_ENDPOINT_SMOKE_PASSED");
  console.log(`unpaid HTTP: ${unpaidResponse.status}`);
  console.log(`paid HTTP: ${paidResponse.status}`);
  console.log(`network mode: ${USE_MAINNET ? "MAINNET" : "testnet"}`);
  console.log(`network: ${ACTIVE_NETWORK}`);
  console.log("asset: USDC");
  console.log(`amountAtomic: ${amountAtomic}`);
  console.log(`amountUsd: ${amountUsd}`);
  console.log(`payment-bearing HTTP requests: ${guard.count()}`);
  console.log(`mode: ${String(verdict.mode)}`);
  console.log(`evidence_level: ${String(verdict.evidence_level)}`);
  console.log(`verdict: ${String(verdict.verdict)}`);
  console.log("verified_pass claimed: No");
}

main().catch((error) => {
  console.error(`[agenteval-paid-smoke] ${String((error as Error).message)}`);
  process.exitCode = 1;
});
