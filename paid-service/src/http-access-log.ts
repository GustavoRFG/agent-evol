import { randomUUID } from "node:crypto";
import { appendFile, mkdir } from "node:fs/promises";
import { STATUS_CODES } from "node:http";
import { isIP } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { NextFunction, Request, Response } from "express";

const moduleDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(moduleDir, "..", "..");

export const ACCESS_LOG_DIR = resolve(repoRoot, "paid-service", "logs");
export const ACCESS_LOG_PATH = resolve(ACCESS_LOG_DIR, "http-access.jsonl");

const SAFE_REQUEST_ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;
const PAYMENT_REQUEST_HEADER_NAMES = [
  "payment",
  "payment-signature",
  "x-payment",
] as const;

const LOG_LIMITS = {
  requestId: 128,
  method: 16,
  path: 512,
  statusText: 64,
  ip: 128,
  userAgent: 300,
  contentType: 160,
  clientId: 128,
} as const;

export type AccessLogEvent =
  | "request_started"
  | "request_finished"
  | "request_closed_before_finish"
  | "request_error";

export type AccessLogRecord = {
  timestamp: string;
  request_id: string;
  event: AccessLogEvent;
  method: string;
  path: string;
  status_code: number | null;
  status_text: string;
  duration_ms: number;
  client_ip: string;
  proxy_ip: string;
  user_agent: string;
  content_type: string;
  payment_present: boolean;
  x_client_id?: string;
};

type HeaderValue = string | string[] | undefined;

type AccessLogTerminal = (event: AccessLogEvent) => void;

export function sanitizeLogValue(value: unknown, limit = 300): string {
  const first = Array.isArray(value) ? value[0] : value;
  if (typeof first !== "string") return "";
  return first
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, Math.max(0, limit));
}

export function clientIpFromForwardedFor(value: HeaderValue): string {
  const raw = sanitizeLogValue(value, 1024);
  if (!raw) return "";
  const first = sanitizeLogValue(raw.split(",")[0] ?? "", LOG_LIMITS.ip);
  if (!first || isIP(first) === 0) return "";
  return first;
}

export function clientIpFromRequest(req: Request): string {
  return clientIpFromForwardedFor(req.headers["x-forwarded-for"]);
}

export function requestIdFrom(req: Request): string {
  const raw =
    sanitizeLogValue(req.headers["x-request-id"], LOG_LIMITS.requestId) ||
    sanitizeLogValue(req.headers["request-id"], LOG_LIMITS.requestId);
  return SAFE_REQUEST_ID_RE.test(raw) ? raw : randomUUID();
}

export function hasPaymentMetadata(req: Request): boolean {
  return PAYMENT_REQUEST_HEADER_NAMES.some((name) => {
    const value = req.headers[name];
    return value !== undefined && sanitizeLogValue(value) !== "";
  });
}

function statusCodeForEvent(
  res: Response,
  event: AccessLogEvent,
): number | null {
  if (event === "request_started") return null;
  if (event === "request_closed_before_finish" && !res.headersSent) return null;
  const statusCode = Number.isInteger(res.statusCode) ? res.statusCode : 0;
  return statusCode > 0 ? statusCode : null;
}

function statusText(statusCode: number | null): string {
  if (statusCode === null) return "";
  return sanitizeLogValue(
    STATUS_CODES[statusCode] ?? "Unknown Status",
    LOG_LIMITS.statusText,
  );
}

export function accessLogRecord(
  req: Request,
  res: Response,
  startedAtMs: number,
  requestId: string,
  event: AccessLogEvent,
): AccessLogRecord {
  const statusCode = statusCodeForEvent(res, event);
  const xClientId = sanitizeLogValue(
    req.headers["x-client-id"],
    LOG_LIMITS.clientId,
  );
  const record: AccessLogRecord = {
    timestamp: new Date().toISOString(),
    request_id: sanitizeLogValue(requestId, LOG_LIMITS.requestId),
    event,
    method: sanitizeLogValue(req.method, LOG_LIMITS.method),
    path: sanitizeLogValue(req.path || req.url, LOG_LIMITS.path),
    status_code: statusCode,
    status_text: statusText(statusCode),
    duration_ms: Math.max(0, Date.now() - startedAtMs),
    client_ip: clientIpFromRequest(req),
    proxy_ip: sanitizeLogValue(req.socket.remoteAddress ?? "", LOG_LIMITS.ip),
    user_agent: sanitizeLogValue(
      req.headers["user-agent"],
      LOG_LIMITS.userAgent,
    ),
    content_type: sanitizeLogValue(
      req.headers["content-type"],
      LOG_LIMITS.contentType,
    ),
    payment_present: hasPaymentMetadata(req),
  };
  if (xClientId) record.x_client_id = xClientId;
  return record;
}

export function appendAccessLog(
  record: AccessLogRecord,
  logPath = ACCESS_LOG_PATH,
): void {
  void mkdir(dirname(logPath), { recursive: true })
    .then(() => appendFile(logPath, JSON.stringify(record) + "\n", "utf8"))
    .catch(() => {
      console.error("[agenteval-paid-service] failed to write access log");
    });
}

export function markRequestError(req: Request, res: Response): void {
  const terminal = res.locals.accessLogTerminal;
  if (typeof terminal === "function") {
    (terminal as AccessLogTerminal)("request_error");
  }
}

export function createAccessLogMiddleware(
  logPath = ACCESS_LOG_PATH,
): (req: Request, res: Response, next: NextFunction) => void {
  return (req: Request, res: Response, next: NextFunction): void => {
    const startedAtMs = Date.now();
    const requestId = requestIdFrom(req);
    res.setHeader("X-Request-Id", requestId);

    appendAccessLog(
      accessLogRecord(req, res, startedAtMs, requestId, "request_started"),
      logPath,
    );

    let terminalLogged = false;
    const logTerminal: AccessLogTerminal = (event) => {
      if (terminalLogged) return;
      terminalLogged = true;
      appendAccessLog(
        accessLogRecord(req, res, startedAtMs, requestId, event),
        logPath,
      );
    };

    res.locals.accessLogTerminal = logTerminal;

    req.on("error", () => logTerminal("request_error"));
    res.on("error", () => logTerminal("request_error"));
    res.on("finish", () => logTerminal("request_finished"));
    res.on("close", () => {
      if (!terminalLogged && !res.writableEnded) {
        logTerminal("request_closed_before_finish");
      }
    });

    next();
  };
}
