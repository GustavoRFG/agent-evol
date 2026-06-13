import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { getAuthHeaders } from "@coinbase/cdp-sdk/auth";
import { HTTPFacilitatorClient, type FacilitatorConfig } from "@x402/core/server";
import type { RouteConfig } from "@x402/core/server";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { paymentMiddleware, x402ResourceServer } from "@x402/express";
import { declareDiscoveryExtension } from "@x402/extensions/bazaar";
import { config as loadDotenv } from "dotenv";
import express, { type NextFunction, type Request, type Response } from "express";
import {
  createAccessLogMiddleware,
  markRequestError,
} from "./http-access-log.js";

const moduleDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(moduleDir, "..", "..");
loadDotenv({ path: resolve(repoRoot, "paid-service", ".env"), quiet: true });

type Caip2Network = `${string}:${string}`;

const TESTNET_NETWORK = "eip155:84532" as const;
const MAINNET_NETWORK = "eip155:8453" as const;
const TESTNET_FACILITATOR_URL = "https://x402.org/facilitator" as const;
const MAINNET_FACILITATOR_URL =
  "https://api.cdp.coinbase.com/platform/v2/x402" as const;

const PAID_ROUTE = "/paid/evaluate-agent-run" as const;
const PAYMENT_ASSET = "USDC" as const;
const PAYMENT_AMOUNT_ATOMIC = "10000" as const;
const PAYMENT_AMOUNT_USD = "0.01" as const;
const PAYMENT_PRICE_LABEL = "$0.01" as const;
const SERVICE_NAME = "AgentEval Forge" as const;
const SERVICE_DESCRIPTION =
  "Independent, audit-friendly Mode A evidence review of coding-agent run evidence." as const;

const PORT = Number.parseInt(process.env.PORT ?? "4081", 10);
const NETWORK = (
  process.env.X402_USE_MAINNET === "1" ? MAINNET_NETWORK : TESTNET_NETWORK
) as Caip2Network;
const FACILITATOR_URL =
  NETWORK === MAINNET_NETWORK
    ? MAINNET_FACILITATOR_URL
    : TESTNET_FACILITATOR_URL;
const BODY_LIMIT = process.env.EVALUATION_BODY_LIMIT ?? "256kb";
const PYTHON_COMMAND = process.env.PYTHON_COMMAND ?? "python";
const EVALUATOR_MODULE =
  process.env.EVALUATOR_MODULE ?? "agenteval.ingest.serve";
const EVALUATOR_TIMEOUT_MS = Number.parseInt(
  process.env.EVALUATOR_TIMEOUT_MS ?? "20000",
  10,
);
const EVALUATION_REVIEW_PRICE_USD =
  process.env.EVALUATION_REVIEW_PRICE_USD ?? PAYMENT_PRICE_LABEL;
const SELLER_RECEIVER_ADDRESS = process.env.SELLER_RECEIVER_ADDRESS ?? "";
const SELLER_RECEIVER_ADDRESS_TYPED =
  SELLER_RECEIVER_ADDRESS as `0x${string}`;

// Public HTTPS base advertised to Bazaar discovery. When set (e.g. an ngrok
// tunnel URL), the seller advertises this as the route `resource` so Bazaar
// accepts it (Bazaar rejects non-https resources). When unset, behaviour is
// unchanged: the x402 framework derives the resource from the request, i.e.
// the local http://localhost:<PORT> default.
const PUBLIC_RESOURCE_URL = (process.env.PUBLIC_RESOURCE_URL ?? "").replace(
  /\/+$/,
  "",
);
const ADVERTISED_RESOURCE_URL = PUBLIC_RESOURCE_URL
  ? `${PUBLIC_RESOURCE_URL}${PAID_ROUTE}`
  : undefined;
const BASE_RESOURCE_URL = PUBLIC_RESOURCE_URL || `http://localhost:${PORT}`;
const ADVERTISED_PAID_RESOURCE_URL =
  ADVERTISED_RESOURCE_URL ?? `${BASE_RESOURCE_URL}${PAID_ROUTE}`;
const GENERIC_EVIDENCE_INPUT_EXAMPLE = {
  schema_version: "1.0",
  run_id: "run_2026_06_06_001",
  task: {
    task_id: "optional-client-task-id",
    prompt: "Fix the off-by-one bug in the range validation function.",
  },
  patch: {
    format: "unified_diff",
    text: "--- a/file.py\n+++ b/file.py\n@@ ...",
  },
};

const GENERIC_EVIDENCE_INPUT_SCHEMA = {
  type: "object",
  properties: {
    schema_version: { const: "1.0" },
    run_id: { type: "string", minLength: 1 },
    producer: {
      type: "object",
      properties: {
        agent_name: { type: "string" },
        model: { type: "string" },
      },
      additionalProperties: true,
    },
    task: {
      type: "object",
      properties: {
        task_id: { type: "string" },
        prompt: { type: "string", minLength: 1 },
      },
      required: ["prompt"],
      additionalProperties: true,
    },
    patch: {
      type: "object",
      properties: {
        format: { const: "unified_diff" },
        text: { type: "string", minLength: 1 },
      },
      required: ["format", "text"],
      additionalProperties: false,
    },
    claims: {
      type: "object",
      properties: {
        public_tests_passed: { type: ["boolean", "null"] },
        hidden_tests_passed: { type: ["boolean", "null"] },
        all_tests_passed: { type: ["boolean", "null"] },
        summary: { type: "string" },
      },
      additionalProperties: true,
    },
    test_evidence: {
      type: "object",
      properties: {
        framework: { type: "string" },
        command: { type: "string" },
        exit_code: { type: ["integer", "null"] },
        summary: { type: "string" },
        stdout: { type: "string" },
        stderr: { type: "string" },
      },
      additionalProperties: true,
    },
    trace: {
      type: "object",
      properties: {
        commands: { type: "array", items: { type: "string" } },
        final_message: { type: "string" },
      },
      additionalProperties: true,
    },
    integrity: {
      type: "object",
      properties: {
        algorithm: { const: "sha256" },
        patch_sha256: { type: "string" },
        test_evidence_sha256: { type: "string" },
        bundle_sha256: { type: "string" },
      },
      additionalProperties: true,
    },
    metadata: {
      type: "object",
      additionalProperties: true,
    },
  },
  required: ["schema_version", "run_id", "task", "patch"],
  additionalProperties: true,
};

const MODE_A_VERDICT_EXAMPLE = {
  evaluation_id: "eval_run_2026_06_06_001",
  mode: "evidence_review",
  evidence_level: "self_reported_execution_evidence",
  verdict: "requires_review",
  scores: {
    task_alignment: 0.82,
    patch_minimality: 0.91,
    evidence_quality: 0.63,
    safety_signal: 0.88,
  },
  findings: [
    {
      severity: "warning",
      code: "EXECUTION_NOT_INDEPENDENTLY_VERIFIED",
      message:
        "Execution evidence was supplied by the caller and was not reproduced by AgentEval Forge.",
    },
  ],
  claims: {
    tests_claimed_passed: true,
    evidence_consistent_with_claim: true,
    independently_verified: false,
  },
  integrity: {
    hash_manifest_supplied: false,
    hashes_verified: false,
  },
  human_review: {
    recommended: true,
    reasons: ["Execution was not independently reproduced."],
  },
};

const MODE_A_VERDICT_SCHEMA = {
  type: "object",
  properties: {
    evaluation_id: { type: "string" },
    mode: { const: "evidence_review" },
    evidence_level: { type: "string" },
    verdict: { type: "string" },
    scores: {
      type: "object",
      properties: {
        task_alignment: { type: "number" },
        patch_minimality: { type: "number" },
        evidence_quality: { type: "number" },
        safety_signal: { type: "number" },
      },
      additionalProperties: true,
    },
    findings: { type: "array", items: { type: "object" } },
    claims: { type: "object" },
    integrity: { type: "object" },
    human_review: { type: "object" },
  },
  required: [
    "evaluation_id",
    "mode",
    "evidence_level",
    "verdict",
    "scores",
    "findings",
    "claims",
    "integrity",
    "human_review",
  ],
  additionalProperties: true,
};

interface FacilitatorEndpoint {
  method: "GET" | "POST";
  suffix: string;
}

const FACILITATOR_ENDPOINTS = {
  verify: { method: "POST", suffix: "/verify" },
  settle: { method: "POST", suffix: "/settle" },
  supported: { method: "GET", suffix: "/supported" },
} as const satisfies Record<string, FacilitatorEndpoint>;

class EvaluatorBoundaryError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "EvaluatorBoundaryError";
    this.code = code;
  }
}

function createCdpFacilitatorConfig(
  facilitatorUrl: string,
  apiKeyId: string,
  apiKeySecret: string,
): FacilitatorConfig {
  const base = new URL(facilitatorUrl);
  const requestHost = base.host;
  const basePath = base.pathname.replace(/\/+$/, "");

  return {
    url: facilitatorUrl,
    createAuthHeaders: async () => {
      const headersFor = (endpoint: FacilitatorEndpoint) =>
        getAuthHeaders({
          apiKeyId,
          apiKeySecret,
          requestMethod: endpoint.method,
          requestHost,
          requestPath: `${basePath}${endpoint.suffix}`,
        });

      const [verify, settle, supported] = await Promise.all([
        headersFor(FACILITATOR_ENDPOINTS.verify),
        headersFor(FACILITATOR_ENDPOINTS.settle),
        headersFor(FACILITATOR_ENDPOINTS.supported),
      ]);

      return { verify, settle, supported };
    },
  };
}

function assertConfig(): void {
  const problems: string[] = [];

  if (!Number.isFinite(PORT) || PORT <= 0) {
    problems.push("PORT must be a positive integer.");
  }
  if (!SELLER_RECEIVER_ADDRESS || !SELLER_RECEIVER_ADDRESS.startsWith("0x")) {
    problems.push(
      "SELLER_RECEIVER_ADDRESS must be a 0x-prefixed Base address.",
    );
  }
  if (!EVALUATION_REVIEW_PRICE_USD.startsWith("$")) {
    problems.push(
      'EVALUATION_REVIEW_PRICE_USD must start with "$" (for example "$0.01").',
    );
  }
  if (PUBLIC_RESOURCE_URL && !PUBLIC_RESOURCE_URL.startsWith("https://")) {
    problems.push(
      'PUBLIC_RESOURCE_URL must start with "https://" when set ' +
        "(Bazaar rejects non-https resources).",
    );
  }
  if (NETWORK === MAINNET_NETWORK) {
    if (process.env.X402_USE_MAINNET !== "1") {
      problems.push("Base mainnet requires X402_USE_MAINNET=1.");
    }
    if (!process.env.CDP_API_KEY_ID) {
      problems.push("CDP_API_KEY_ID is required for the mainnet facilitator.");
    }
    if (!process.env.CDP_API_KEY_SECRET) {
      problems.push(
        "CDP_API_KEY_SECRET is required for the mainnet facilitator.",
      );
    }
  }

  if (problems.length > 0) {
    console.error("[agenteval-paid-service] configuration problems:");
    for (const problem of problems) console.error("  - " + problem);
    process.exit(1);
  }
}

function shortAddress(value: string): string {
  if (value.length < 12) return "(configured)";
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function evaluatorEnv(): NodeJS.ProcessEnv {
  const allow = new Set([
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "PYTHONHOME",
    "PYTHONPATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "VIRTUAL_ENV",
    "WINDIR",
  ]);
  const env: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined && allow.has(key.toUpperCase())) {
      env[key] = value;
    }
  }
  return env;
}

function parseBoundaryPayload(text: string): Record<string, unknown> {
  try {
    const payload = JSON.parse(text) as unknown;
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      return payload as Record<string, unknown>;
    }
  } catch {
    // handled below
  }
  throw new EvaluatorBoundaryError(
    "EVALUATOR_BAD_OUTPUT",
    "evaluator returned invalid JSON",
  );
}

async function callEvaluator(
  payload: unknown,
  options: { validateOnly?: boolean } = {},
): Promise<Record<string, unknown>> {
  const args = ["-m", EVALUATOR_MODULE];
  if (options.validateOnly) args.push("--validate-only");

  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(PYTHON_COMMAND, args, {
      cwd: repoRoot,
      env: evaluatorEnv(),
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (
      fn: typeof resolvePromise | typeof rejectPromise,
      value: Record<string, unknown> | Error,
    ) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      fn(value as never);
    };

    const timeout = setTimeout(() => {
      child.kill();
      finish(
        rejectPromise,
        new EvaluatorBoundaryError(
          "EVALUATOR_TIMEOUT",
          "evaluator timed out",
        ),
      );
    }, EVALUATOR_TIMEOUT_MS);

    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
      if (stdout.length > 1024 * 1024) {
        child.kill();
        finish(
          rejectPromise,
          new EvaluatorBoundaryError(
            "EVALUATOR_OUTPUT_TOO_LARGE",
            "evaluator output exceeded limit",
          ),
        );
      }
    });

    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk.slice(0, 4096);
    });

    child.on("error", (error) => {
      finish(
        rejectPromise,
        new EvaluatorBoundaryError(
          "EVALUATOR_START_FAILED",
          error.message || "failed to start evaluator",
        ),
      );
    });

    child.on("close", (code) => {
      if (settled) return;
      try {
        const result = parseBoundaryPayload(stdout);
        if (code === 0) {
          finish(resolvePromise, result);
          return;
        }

        const error = result.error;
        if (error && typeof error === "object") {
          const record = error as Record<string, unknown>;
          finish(
            rejectPromise,
            new EvaluatorBoundaryError(
              typeof record.code === "string"
                ? record.code
                : "EVALUATOR_REJECTED_INPUT",
              typeof record.message === "string"
                ? record.message
                : "invalid generic evidence package",
            ),
          );
          return;
        }

        finish(
          rejectPromise,
          new EvaluatorBoundaryError(
            "EVALUATOR_FAILED",
            stderr ? "evaluator failed" : "evaluator failed without details",
          ),
        );
      } catch (error) {
        finish(rejectPromise, error as Error);
      }
    });

    child.stdin.end(JSON.stringify(payload));
  });
}

async function validateEvidencePayload(payload: unknown): Promise<void> {
  await callEvaluator(payload, { validateOnly: true });
}

async function evaluateEvidencePayload(
  payload: unknown,
): Promise<Record<string, unknown>> {
  return callEvaluator(payload);
}

function exactPaymentAccept(price: string): RouteConfig["accepts"] {
  return [
    {
      scheme: "exact",
      price,
      network: NETWORK,
      payTo: SELLER_RECEIVER_ADDRESS_TYPED,
    },
  ];
}

function bazaarDiscovery(): Record<string, unknown> {
  return {
    ...declareDiscoveryExtension({
      bodyType: "json",
      input: GENERIC_EVIDENCE_INPUT_EXAMPLE,
      inputSchema: GENERIC_EVIDENCE_INPUT_SCHEMA,
      output: {
        example: MODE_A_VERDICT_EXAMPLE,
        schema: MODE_A_VERDICT_SCHEMA,
      },
    }),
    discoverable: true,
  };
}

function healthPayload(): Record<string, unknown> {
  return {
    status: "ok",
    service: SERVICE_NAME,
    mode: "evidence_review",
    network: NETWORK,
    paidRoute: PAID_ROUTE,
  };
}

function networkLabel(): string {
  return NETWORK === MAINNET_NETWORK ? "Base mainnet" : "Base Sepolia testnet";
}

function llmsText(): string {
  return [
    "# AgentEval Forge",
    "",
    "AgentEval Forge is an independent, audit-friendly evaluation service for coding-agent runs. It provides Mode A, read-only evidence review.",
    "",
    "Given a generic agent-run evidence package with a task, a unified diff, and optional claims, test evidence, operational trace, and integrity hashes, it returns a structured verdict with task_alignment, patch_minimality, evidence_quality, and safety_signal scores, an evidence_level, findings, and a human_review recommendation.",
    "",
    "AgentEval Forge never executes submitted code, never applies submitted patches, never reruns client tests, and never claims verified_pass in Mode A.",
    "",
    `Use it by sending POST application/json to ${PAID_ROUTE}. Payment is handled by x402 with ${PAYMENT_ASSET} on ${networkLabel()} at ${PAYMENT_PRICE_LABEL} (${PAYMENT_AMOUNT_ATOMIC} atomic units). Unpaid requests receive HTTP 402 with payment requirements.`,
    "",
    "See /openapi.json for the full schema and /.well-known/x402 for x402 discovery metadata.",
    "",
  ].join("\n");
}

function openApiDocument(): Record<string, unknown> {
  return {
    openapi: "3.1.0",
    info: {
      title: "AgentEval Forge Paid Evidence Review API",
      version: "0.1.0",
      description:
        `${SERVICE_DESCRIPTION} The paid route runs Mode A only and requires x402 payment.`,
    },
    servers: [{ url: BASE_RESOURCE_URL }],
    paths: {
      [PAID_ROUTE]: {
        post: {
          summary: "Evaluate coding-agent run evidence",
          operationId: "evaluateAgentRunPaid",
          description:
            "Runs read-only Mode A evidence review for a generic V1 evidence package. Requires x402 payment. Unpaid requests receive HTTP 402 with payment requirements. The service does not execute submitted code and never returns verified_pass in Mode A.",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: GENERIC_EVIDENCE_INPUT_SCHEMA,
                examples: {
                  minimal: { value: GENERIC_EVIDENCE_INPUT_EXAMPLE },
                },
              },
            },
          },
          responses: {
            "200": {
              description: "Mode A evidence-review verdict.",
              content: {
                "application/json": {
                  schema: MODE_A_VERDICT_SCHEMA,
                  examples: {
                    requiresReview: { value: MODE_A_VERDICT_EXAMPLE },
                  },
                },
              },
            },
            "400": {
              description: "Invalid generic evidence package.",
            },
            "402": {
              description: "x402 payment required.",
            },
            "413": {
              description: "Request body exceeds configured limit.",
            },
          },
        },
      },
    },
  };
}

function x402Descriptor(): Record<string, unknown> {
  const routeConfig = paidRouteConfig();
  return {
    service: SERVICE_NAME,
    description: SERVICE_DESCRIPTION,
    paidRoutes: [
      {
        method: "POST",
        path: PAID_ROUTE,
        resource: ADVERTISED_PAID_RESOURCE_URL,
        network: NETWORK,
        asset: PAYMENT_ASSET,
        price: EVALUATION_REVIEW_PRICE_USD,
        amountUsd: PAYMENT_AMOUNT_USD,
        amountAtomic: PAYMENT_AMOUNT_ATOMIC,
        payTo: SELLER_RECEIVER_ADDRESS,
        scheme: "exact",
        accepts: routeConfig.accepts,
        mimeType: routeConfig.mimeType,
        extensions: routeConfig.extensions,
      },
    ],
    links: {
      openapi: "/openapi.json",
      llms: "/llms.txt",
      health: "/health",
    },
  };
}

function apiCatalog(): Record<string, unknown> {
  return {
    name: SERVICE_NAME,
    description: SERVICE_DESCRIPTION,
    apis: [
      {
        name: "AgentEval Forge Paid Evidence Review",
        description:
          "x402-paid Mode A evidence review for coding-agent run evidence.",
        paidRoute: {
          method: "POST",
          path: PAID_ROUTE,
        },
        links: [
          { rel: "openapi", href: "/openapi.json", type: "application/json" },
          {
            rel: "x402",
            href: "/.well-known/x402",
            type: "application/json",
          },
          { rel: "llms", href: "/llms.txt", type: "text/plain" },
        ],
      },
    ],
  };
}

function landingPayload(): Record<string, unknown> {
  return {
    service: SERVICE_NAME,
    description: SERVICE_DESCRIPTION,
    links: {
      llms: "/llms.txt",
      openapi: "/openapi.json",
      x402: "/.well-known/x402",
      health: "/health",
    },
  };
}

function paidRouteConfig(): RouteConfig {
  return {
    accepts: exactPaymentAccept(EVALUATION_REVIEW_PRICE_USD),
    // When PUBLIC_RESOURCE_URL is set, advertise the public HTTPS resource so
    // Bazaar can index it; when undefined, the framework falls back to the
    // request-derived local URL (unchanged behaviour).
    resource: ADVERTISED_RESOURCE_URL,
    description:
      "Independent, audit-friendly Mode A evidence review of coding-agent run evidence. " +
      "Read-only: does not apply patches, run tests, or claim verified execution.",
    mimeType: "application/json",
    extensions: bazaarDiscovery(),
  };
}

function createFacilitatorConfig(): FacilitatorConfig {
  if (NETWORK === MAINNET_NETWORK) {
    return createCdpFacilitatorConfig(
      FACILITATOR_URL,
      process.env.CDP_API_KEY_ID!,
      process.env.CDP_API_KEY_SECRET!,
    );
  }
  return { url: FACILITATOR_URL };
}

assertConfig();

const facilitatorClient = new HTTPFacilitatorClient(createFacilitatorConfig());
const resourceServer = new x402ResourceServer(facilitatorClient).register(
  NETWORK,
  new ExactEvmScheme(),
);

const paymentRoutes: Record<string, RouteConfig> = {
  [`POST ${PAID_ROUTE}`]: paidRouteConfig(),
};

const app = express();
app.use(createAccessLogMiddleware());
app.use(express.json({ limit: BODY_LIMIT }));

app.head("/", (_req: Request, res: Response) => {
  res.status(200).end();
});

app.get("/", (_req: Request, res: Response) => {
  res.status(200).json(landingPayload());
});

app.head("/health", (_req: Request, res: Response) => {
  res.status(200).end();
});

app.get("/health", (_req: Request, res: Response) => {
  res.status(200).json(healthPayload());
});

app.head("/llms.txt", (_req: Request, res: Response) => {
  res.status(200).type("text/plain").end();
});

app.get("/llms.txt", (_req: Request, res: Response) => {
  res.status(200).type("text/plain").send(llmsText());
});

app.head("/openapi.json", (_req: Request, res: Response) => {
  res.status(200).end();
});

app.get("/openapi.json", (_req: Request, res: Response) => {
  res.status(200).json(openApiDocument());
});

app.head("/.well-known/x402", (_req: Request, res: Response) => {
  res.status(200).end();
});

app.get("/.well-known/x402", (_req: Request, res: Response) => {
  res.status(200).json(x402Descriptor());
});

app.head("/apis.json", (_req: Request, res: Response) => {
  res.status(200).end();
});

app.get("/apis.json", (_req: Request, res: Response) => {
  res.status(200).json(apiCatalog());
});

app.head("/.well-known/api-catalog", (_req: Request, res: Response) => {
  res.status(200).end();
});

app.get("/.well-known/api-catalog", (_req: Request, res: Response) => {
  res.status(200).json(apiCatalog());
});

app.post(
  PAID_ROUTE,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      await validateEvidencePayload(req.body);
      next();
    } catch (error) {
      if (error instanceof EvaluatorBoundaryError) {
        res.status(400).json({
          error: "invalid_generic_evidence",
          code: error.code,
          message: error.message,
        });
        return;
      }
      next(error);
    }
  },
);

app.use(paymentMiddleware(paymentRoutes, resourceServer));

app.post(PAID_ROUTE, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const verdict = await evaluateEvidencePayload(req.body);
    res.status(200).json(verdict);
  } catch (error) {
    if (error instanceof EvaluatorBoundaryError) {
      res.status(400).json({
        error: "invalid_generic_evidence",
        code: error.code,
        message: error.message,
      });
      return;
    }
    next(error);
  }
});

app.use((err: unknown, req: Request, res: Response, _next: NextFunction) => {
  const message =
    err instanceof Error && "type" in err && err.type === "entity.too.large"
      ? "request body exceeds configured limit"
      : "internal_error";
  const status = message === "internal_error" ? 500 : 413;
  if (status === 500) {
    console.error("[agenteval-paid-service] unhandled error");
  }
  res.status(status);
  markRequestError(req, res);
  res.json({ error: message });
});

const server = app.listen(PORT, () => {
  console.log(
    `[agenteval-paid-service] listening on http://localhost:${PORT} ` +
      `route=${PAID_ROUTE} mode=evidence_review network=${NETWORK} ` +
      `${NETWORK === MAINNET_NETWORK ? "MAINNET" : "testnet"} ` +
      `facilitator=${FACILITATOR_URL} price=${EVALUATION_REVIEW_PRICE_USD} ` +
      `amountAtomic=${PAYMENT_AMOUNT_ATOMIC} payTo=${shortAddress(
        SELLER_RECEIVER_ADDRESS,
      )} ` +
      `resource=${ADVERTISED_RESOURCE_URL ?? `http://localhost:${PORT}${PAID_ROUTE} (request-derived default)`}`,
  );
});

// Bound incomplete or idle public-pilot connections so external probes
// cannot hold sockets indefinitely.
server.headersTimeout = 10_000;
server.requestTimeout = 15_000;
server.keepAliveTimeout = 5_000;
server.maxRequestsPerSocket = 100;

server.setTimeout(15_000, (socket) => {
  socket.destroy();
});
