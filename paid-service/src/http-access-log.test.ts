import assert from "node:assert/strict";
import test from "node:test";
import type { Request, Response } from "express";
import {
  accessLogRecord,
  clientIpFromForwardedFor,
  sanitizeLogValue,
} from "./http-access-log.js";

function mockRequest(overrides: Partial<Request> = {}): Request {
  return {
    method: "POST",
    path: "/paid/evaluate-agent-run",
    url: "/paid/evaluate-agent-run",
    headers: {},
    socket: { remoteAddress: "::1" },
    ...overrides,
  } as Request;
}

function mockResponse(overrides: Partial<Response> = {}): Response {
  return {
    statusCode: 200,
    headersSent: true,
    writableEnded: true,
    ...overrides,
  } as Response;
}

test("finished request record includes safe lifecycle fields", () => {
  const req = mockRequest({
    headers: {
      "x-forwarded-for": "198.211.104.56, 10.0.0.2",
      "user-agent": "agentcash@0.14.4",
      "content-type": "application/json",
      "x-client-id": "pilot-client-01",
    },
  });
  const res = mockResponse({ statusCode: 402 });

  const record = accessLogRecord(
    req,
    res,
    Date.now() - 12,
    "fixture-request-id",
    "request_finished",
  );

  assert.equal(record.event, "request_finished");
  assert.equal(record.request_id, "fixture-request-id");
  assert.equal(record.method, "POST");
  assert.equal(record.path, "/paid/evaluate-agent-run");
  assert.equal(record.status_code, 402);
  assert.equal(record.status_text, "Payment Required");
  assert.equal(record.client_ip, "198.211.104.56");
  assert.equal(record.proxy_ip, "::1");
  assert.equal(record.user_agent, "agentcash@0.14.4");
  assert.equal(record.content_type, "application/json");
  assert.equal(record.x_client_id, "pilot-client-01");
});

test("interrupted request records closed before finish without fake status", () => {
  const record = accessLogRecord(
    mockRequest(),
    mockResponse({ headersSent: false, writableEnded: false }),
    Date.now(),
    "interrupted",
    "request_closed_before_finish",
  );

  assert.equal(record.event, "request_closed_before_finish");
  assert.equal(record.status_code, null);
  assert.equal(record.status_text, "");
});

test("error event records status text without error details", () => {
  const record = accessLogRecord(
    mockRequest(),
    mockResponse({ statusCode: 500 }),
    Date.now(),
    "errored",
    "request_error",
  );
  const serialized = JSON.stringify(record);

  assert.equal(record.event, "request_error");
  assert.equal(record.status_code, 500);
  assert.equal(record.status_text, "Internal Server Error");
  assert.doesNotMatch(serialized, /stack|message|private|secret/i);
});

test("forwarded IP handling uses only a valid first value", () => {
  assert.equal(
    clientIpFromForwardedFor("203.0.113.42, 198.51.100.9"),
    "203.0.113.42",
  );
  assert.equal(clientIpFromForwardedFor("not-an-ip, 198.51.100.9"), "");
});

test("maliciously long forwarded header and user-agent are sanitized", () => {
  const longForwarded = `${"9".repeat(600)}, 203.0.113.42`;
  const req = mockRequest({
    headers: {
      "x-forwarded-for": longForwarded,
      "user-agent": `agent\r\n${"x".repeat(1000)}`,
    },
  });
  const record = accessLogRecord(
    req,
    mockResponse(),
    Date.now(),
    "long-headers",
    "request_finished",
  );

  assert.equal(record.client_ip, "");
  assert.ok(record.user_agent.length <= 300);
  assert.doesNotMatch(record.user_agent, /[\r\n\t]/);
});

test("sensitive headers and bodies are not serialized", () => {
  const req = mockRequest({
    headers: {
      authorization: "Bearer secret-token",
      cookie: "sessionid=secret-cookie",
      payment: "complete-payment-payload",
      "payment-signature": "secret-payment-signature",
      "user-agent": "safe-agent",
    },
    body: {
      private_key: "secret-private-key",
      payload: "secret-body",
    },
  } as Partial<Request>);
  const record = accessLogRecord(
    req,
    mockResponse(),
    Date.now(),
    "secret-check",
    "request_finished",
  );
  const serialized = JSON.stringify(record);

  assert.equal(record.payment_present, true);
  assert.doesNotMatch(serialized, /secret-token/);
  assert.doesNotMatch(serialized, /secret-cookie/);
  assert.doesNotMatch(serialized, /complete-payment-payload/);
  assert.doesNotMatch(serialized, /secret-payment-signature/);
  assert.doesNotMatch(serialized, /secret-private-key|secret-body/);
  assert.doesNotMatch(serialized, /authorization|cookie|payment-signature/i);
});

test("sanitizeLogValue strips controls and applies length limits", () => {
  const value = sanitizeLogValue(`abc\r\n\t${"z".repeat(20)}`, 8);
  assert.equal(value.length, 8);
  assert.doesNotMatch(value, /[\r\n\t]/);
});
