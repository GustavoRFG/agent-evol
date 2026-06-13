# AgentEval Forge 30-hour local pilot runbook

This runbook keeps the public pilot local-first and manually controlled. The
seller and ngrok are started by a human. The monitoring tools below are passive:
they do not restart the seller, restart ngrok, install a Windows Service, create
scheduled tasks, or persist secrets.

The primary observability source is the seller-side append-only JSONL log:

```text
paid-service/logs/http-access.jsonl
```

The ngrok Inspector remains optional for visual debugging only. It is not the
primary source of request truth.

## Window 1 - seller

```powershell
cd D:\agenteval-forge
& .\.venv\Scripts\Activate.ps1
npm.cmd --prefix paid-service run dev
```

## Window 2 - ngrok

```powershell
ngrok http 4081 `
  --url https://contessa-awkward-vocatively.ngrok-free.dev
```

## Window 3 - live seller viewer

```powershell
powershell `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File "D:\agenteval-forge\paid-service\scripts\show-http-live.ps1"
```

The live viewer reads only `paid-service/logs/http-access.jsonl`. It prints the
latest finished requests on startup, then stays silent until new relevant
seller-side events arrive.

## Window 4 - optional health watcher

```powershell
powershell `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File "D:\agenteval-forge\paid-service\scripts\watch-pilot-health.ps1"
```

The health watcher checks:

```text
http://localhost:4081/health
https://contessa-awkward-vocatively.ngrok-free.dev/health
```

It writes only initial status, failures, recoveries, and status transitions to:

```text
paid-service/logs/pilot-health.jsonl
```

It does not restart anything.

## Session summary

```powershell
powershell `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File "D:\agenteval-forge\paid-service\scripts\show-http-session-summary.ps1"
```

Optional timestamp filter:

```powershell
powershell `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File "D:\agenteval-forge\paid-service\scripts\show-http-session-summary.ps1" `
  -Since "2026-06-10T04:00:00-03:00"
```

The summary groups finished requests by method, status, route, client IP, and
user agent. It also lists unpaid `402` gates, paid `200` completions with
`payment_present = true`, and lifecycle anomalies such as started requests with
no terminal event, closed-before-finish requests, and request errors.

## Logged fields

The seller log stores bounded, sanitized observability fields:

```text
timestamp
request_id
event
method
path
status_code
status_text
duration_ms
client_ip
proxy_ip
user_agent
content_type
x_client_id
payment_present
```

`client_ip` is the first syntactically valid value from `X-Forwarded-For`.
`proxy_ip` preserves the socket remote address. These fields are for
observability only and must not be used for authorization decisions.

The log never stores request bodies, response bodies, complete headers,
authorization headers, cookies, payment signatures, private keys, CDP
credentials, buyer credentials, session IDs, or complete payment payloads.
