---
title: "App UI Host API"
description: "RPC namespaces and methods your iframe can call on the host, with current implementation status."
section: apps
slug: app-ui-host-api
order: 14
updated: 2026-04-28
estimated_minutes: 6
category: "App UI"
---

Every call from your iframe goes through `postMessage → Host Bridge → POST /api/v1/anna-apps/runtime/rpc → anna_app_rpc_dispatcher.dispatch`. The dispatcher does three things in order:

1. **Auth.** `decode_window_token(t)` against the JWT bound to `(window_uuid, user_id, app_id, version_id, scopes)` (TTL 120s, audience `anna-app-window`).
2. **ACL.** `host_api_allows(manifest, ns, method)` checks `manifest.ui.host_api[ns]` (with `*` and `<id>` wildcards). `window.*` is always allowed.
3. **Permissions.** Top-level `permissions` are checked for write/append actions (e.g. `chat.write_message` requires `chat.write_message`).

Then it dispatches to the namespace handler. Any failure returns `{ ok: false, error: { code, message, details? } }`.

## RPC envelope

```jsonc
// Request (sent via postMessage; Host Bridge forwards to backend)
{
  "id":          "<correlation>",
  "window_uuid": "<wid>",
  "ns":          "<namespace>",
  "method":      "<method>",
  "args":        { … }
}

// Response
{
  "id": "<correlation>",
  "ok": true,
  "result": { … }
}
// or
{
  "id": "<correlation>",
  "ok": false,
  "error": { "code": "permission_denied", "message": "…", "details": {…} }
}
```

The SDK wraps this for you — see [App UI SDK](/developers/apps/app-ui-sdk).

## Namespaces

Status legend:
- ✅ implemented
- ⏳ stub (defined; returns `not_implemented`)

### `window` *(always granted)*

| method | status | args | result |
|---|---|---|---|
| `hello` | ✅ | `{ client_info? }` | `{ window_uuid, app_id, version_id, view_meta, capabilities, entry_payload, runtime_state, geometry }` — sent automatically by SDK |
| `ready` | ✅ | `{}` | `{}` — emitted after first paint |
| `heartbeat` | ✅ | `{}` | `{}` — every 10 s |
| `set_title` | ✅ | `{ title: string (1..120) }` | `{}` — broadcasts SSE `title_changed` |
| `resize` | ✅ | `{ w, h }` (clamped to view min/max) | `{ w, h }` — persists geometry |
| `focus` | ✅ | `{}` | `{}` — bumps z-index, broadcasts SSE `window_focus_changed` |
| `close` | ✅ | `{ reason?: string }` | `{}` — sets `status=closed`, broadcasts SSE `close_view` |
| `open_view` | ✅ | `{ view: string, payload?: any }` | `{ window_uuid }` — opens (or focuses) another view of the same app |
| `report_error` | ✅ | `{ message, stack?, context? }` | `{}` — logged server-side as `crashed` if fatal |

### `tools`

| method | status | args | result |
|---|---|---|---|
| `list` | ✅ | `{}` | `{ tools: [{ tool_id, plugin_name, tool_name, description, input_schema }] }` filtered to your `host_api.tools` allow-list |
| `invoke` | ✅ | `{ tool_id, method?, args, timeoutMs? }` | `{ result }` — routes via NATS to the user's online Anna Agent; **≤ 90 s** |
| `invokeAsync` | ✅ | `{ tool_id, method?, args?, timeoutMs?, clientTag? }` | `{ jobId, state: "queued", deadlineMs }` — returns immediately; see [Async tool jobs](#async-tool-jobs-invokeasync) |
| `getJob` | ✅ | `{ jobId, sinceSeq?, limit? }` | `JobSnapshot` — authoritative state + incremental progress slice |
| `cancelJob` | ✅ | `{ jobId, reason? }` | `{ jobId, state, cancelled }` — idempotent |
| `listJobs` | ✅ | `{ tool_id?, state?, clientTag?, since?, limit? }` | `{ jobs: JobSnapshot[], truncated }` — reload-recovery entry point |

`host_api.tools` is an **optional narrowing** allow-list. When omitted (or empty), the window may invoke **any** `tool_id` declared in `required_executas` / `optional_executas`. Provide explicit refs (e.g. `["required:bundled:foo"]`, `["required:*"]`) only when a window should reach a *subset* of the app's declared executas. Prefer `required:*` over pinning a concrete `tool_id`, since bundled handles are rewritten to concrete ids at publish/dev time and a pinned id will drift.

`method` is **required** when `tool_id` was minted ad-hoc (`tool-{handle}-{slug}-{uniq}` form). For Executas with a registered `(plugin_name, tool_name)`, the dispatcher resolves it from the catalogue and `method` is optional.

#### Per-call timeout (`timeoutMs`)

`tools.invoke` accepts an optional `timeoutMs` integer that bounds the host wait for a single call:

| Bound | Value | Source |
|---|---|---|
| Hard minimum | `1000` ms | `InvokeTimeoutPolicy.min_ms` |
| Hard maximum | `90000` ms | `InvokeTimeoutPolicy.max_ms` |
| Default (omitted or `null`) | `65000` ms | `InvokeTimeoutPolicy.default_ms` (fallback: manifest `tool.timeout`) |
| Host grace | `+2000` ms | added to the plugin-facing deadline so cancel/ack can land |

> **Why 90 s?** `tools.invoke` rides a single held-open HTTP request from
> the browser through the public edge (Cloudflare), whose held-request
> ceiling is ≈100 s. A larger budget could never deliver its result: the
> edge would cut the connection first and the app would receive an opaque
> HTML error page instead of JSON. Tools that legitimately need more than
> 90 s must use the async job channel — see
> [Async tool jobs](#async-tool-jobs-invokeasync) below.

Values below `min_ms` are rejected with `invalid_arg`; values above `max_ms` are clamped. When a clamped call later times out, `error.details` carries both `timeout_ms` (effective) and `requested_timeout_ms` / `max_timeout_ms` so the app can tell its requested budget was reduced. The clamped value is forwarded to the matrix Agent as `params.timeout`, and a wall-clock `params.deadline_ms` is propagated to the plugin so reverse-RPC subcalls (storage / image / upload) can size their own waits via the SDK's `ctx.remaining_s()` (Python) / `ctx.remainingS()` (Node) helpers.

When the host wait elapses the call rejects with:

| Code | Meaning |
|---|---|
| `tool_timeout` | The plugin did not return a response within the (clamped) `timeoutMs` window. The host also sends a best-effort `_cancel_invoke` command to the Agent, which stops the in-flight invocation and reaps the plugin's whole subprocess tree (e.g. a hung headless Chrome). |
| `subcall_timeout` | A reverse-RPC subcall (storage/image/upload) timed out while the outer `tools.invoke` was still within its deadline. Same wire shape, but `error.details.subcall` identifies the channel. |

Example:

```ts
import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const anna = await AnnaAppRuntime.connect();
try {
  const { result } = await anna.tools.invoke({
    tool_id: "tool-acme-summarize",
    args: { text },
    timeoutMs: 30_000,
  });
  render(result);
} catch (err) {
  if (err.code === "tool_timeout") {
    showRetryBanner("The tool took too long — try a shorter input.");
  } else {
    throw err;
  }
}
```

#### Async tool jobs (`invokeAsync`)

> Design: `docs/design/anna-app-tools-invoke-async-jobs.md`. Requires
> dispatcher ≥ 0.19.0 (SDK `@anna-ai/app-runtime` ≥ 0.15.0); older hosts
> reject the new methods with `not_implemented`.

**When to use which channel:**

| Situation | Channel |
|---|---|
| Tool finishes in < 90 s | `tools.invoke` (simplest) |
| Tool may exceed 90 s, or you don't want to block the UI | `tools.invokeAsync` / `invokeAsyncAwait` |
| Need progress UI / cancel / survive page reloads | `tools.invokeAsync` family only |

`invokeAsync` creates a **job** and returns `{jobId, state: "queued",
deadlineMs}` immediately — no long-held HTTP request anywhere in the
chain. The job's lifecycle is
`queued → running → succeeded | failed | cancelled | expired`; state is
owned by the host (survives reloads) and is delivered to the app two ways:

1. **Push** — the host emits `tool_job` window events
   (`{job_id, tool_id, state, seq, event, terminal}`) as progress folds in.
   Events are a latency optimisation: they never carry the result, and
   losing one is harmless because of …
2. **Poll** — `getJob({jobId, sinceSeq})` is the single source of truth:
   authoritative `state`, the `result` (on `succeeded`), a structured
   `error` (on `failed`/`cancelled`/`expired`) and the progress slice with
   `seq > sinceSeq`.

**The easy path** — `anna.tools.invokeAsyncAwait(args, opts?)` wraps all of
the above (event subscription + adaptive polling fallback + abort wiring)
and resolves with the plugin's result payload:

```ts
const ctl = new AbortController();
cancelBtn.onclick = () => ctl.abort();          // → cancelJob

try {
  const result = await anna.tools.invokeAsyncAwait(
    {
      tool_id, method: "run_steps",
      args: { steps: 100 },
      timeoutMs: 30 * 60_000,                   // job deadline (60s..24h)
      clientTag: "render-batch-7",              // your recovery key
    },
    {
      onProgress: (ev) => bar.update(ev.data),  // {seq, type, data}
      signal: ctl.signal,
    },
  );
  render(result);
} catch (err) {
  switch (err.code) {
    case "cancelled":     /* user aborted */ break;
    case "tool_timeout":  /* job hit its deadline (state=expired) */ break;
    case "tool_failed":   /* plugin returned failure; err.details */ break;
    case "wait_timeout":  /* client wall clock elapsed — the job may
                             still be running; recover via err.jobId */ break;
    case "job_quota_exceeded": /* ≤5 active jobs per user */ break;
    case "long_job_capacity":  /* agent long-job slots busy — retry */ break;
    default: throw err;
  }
}
```

**Reload recovery recipe** — job state lives on the host, so a reloaded
iframe can re-adopt its jobs:

```ts
const { jobs } = await anna.tools.listJobs({
  clientTag: "render-batch-7",
  state: ["queued", "running"],
});
for (const job of jobs) {
  let seq = 0;                                   // or job.lastSeq to skip history
  for (;;) {
    const snap = await anna.tools.getJob({ jobId: job.jobId, sinceSeq: seq });
    snap.progress.forEach(renderProgress);
    if (snap.progress.length) seq = snap.lastSeq;
    if (["succeeded", "failed", "cancelled", "expired"].includes(snap.state)) break;
    await sleep(2000);
  }
}
```

**Limits & behaviours to design for:**

- `timeoutMs` is the **job deadline**: default 30 min, clamped to
  [60 s, 24 h]. Deadline elapsed → `state: "expired"`, error
  `tool_timeout`, and the host cancels the agent-side execution.
- Per-user active job quota: **5** (`job_quota_exceeded`); per-agent
  long-job concurrency: **3** (`long_job_capacity`, retryable).
- Progress: plugins emit via the Executa SDK's `emit_progress` (rate limit
  50/s per job; latest 500 events kept; ≤8 KB each). Heartbeats update
  `lastHeartbeatAt` but are not pushed.
- Result cap: 256 KB. Bigger payloads must go through `host/uploadFile`
  and return a reference (`result_too_large` otherwise).
- Cancel is **cooperative and idempotent**: the agent first cancels the
  command task gracefully (the plugin process and its other invokes are
  untouched), falling back to process-group kill after 500 ms.
- `jobId` matches `^tjob_[0-9a-f]{32}$` and equals the plugin-side
  `invoke_id` — one id across app, host, agent and audit logs.
- Cross-user access is always `job_not_found` (no existence oracle).
- Local dev parity: `anna-app dev` implements the full job lifecycle
  in-process (only difference: jobs are not persisted across harness
  restarts). See the official demo `anna-app-long-task-demo`.

### `chat`

| method | status | args | result |
|---|---|---|---|
| `append_artifact` | ✅ | `{ kind: "app_event"\|"text"\|"image"\|…, summary?, payload?, payload_ref? }` | `{ artifact_id }` — attaches a card to the current conversation |
| `read_history` | ⏳ | `{ limit?, before? }` | future |
| `write_message` | ⏳ | `{ role, content }` | future |

### `storage` (per-window `runtime_state`, or APS in nexus)

In the local-dev harness (`anna-app dev`) these handlers operate on the
window's 256 KB `runtime_state` blob. In production they are
overridden at startup to talk to **Anna Persistent Storage (APS)** —
`scope='app'`, `owner_id=window.app_id` — so values are durable across
window lifetimes.

| method | status | args | result |
|---|---|---|---|
| `get` | ✅ | `{ key }` | `{ value, etag?, generation?, exists? }` |
| `set` | ✅ | `{ key, value, if_match?, metadata?, tags?, ttl_seconds? }` | `{ ok: true }` (runtime_state) or `{ etag, generation, size_bytes }` (APS) |
| `delete` | ✅ | `{ key, if_match? }` | `{ ok: true }` / `{ deleted: true }` |
| `list` | ✅ | `{ prefix?, cursor?, limit?=100 }` | `{ items: [{ key, etag, size_bytes, metadata, tags, updated_at }], next_cursor }` |

`list` always returns the APS shape; the runtime_state backend fills
`metadata`/`tags`/`updated_at` with `null` and synthesises a weak
`W/"1-<digest>"` etag from the value. `if_match` lets `set` and `delete`
fail with `precondition_failed` instead of silently clobbering a
concurrent write.

### `agent`

Multi-turn, tool-using agent sessions bound to the user's quota. See
[LLM & Agent](/developers/apps/llm-and-agent) for the streaming frame shape.
The ACL is **structured** (`host_api.agent = { session: { auto, fixed }, tools: [...] }`),
not a flat method list — a session is granted when at least one submode
(`auto` / `fixed`) is enabled.

| method | status | args | result |
|---|---|---|---|
| `session.create` | ✅ | `{ submode: "auto"\|"fixed", fixed_client_id? }` | `{ app_session_uuid, … }` — mints an `app_session_token` (one per submode per window) |
| `session.run` | ✅ | `{ content, allowed_tools? }` | streaming frames (see [LLM & Agent](/developers/apps/llm-and-agent)) |
| `session.cancel` | ✅ | `{ run_id }` | `{}` |
| `session.history` | ✅ | `{ limit?, before? }` | `{ messages: […] }` |
| `session.list` | ✅ | `{ include_expired? }` | `{ sessions: […] }` |
| `session.delete` | ✅ | `{}` | `{ deleted: true }` |
| `session.refresh` | ✅ | `{}` | `{ … }` — re-mints the session token before expiry |

### `image`

Host-mediated image generation / editing — no provider key in the bundle.
Gated by `host_api.image` (method surface) **plus** the per-app
`image_grant` enforced inside the facade.

| method | status | args | result |
|---|---|---|---|
| `generate` | ✅ | `{ prompt, n?, size?, model_hint? }` | `{ images: [{ url, … }] }` |
| `edit` | ✅ | `{ prompt, image_ref, n?, size? }` | `{ images: [{ url, … }] }` |

### `upload`

Invoke-scoped, transient artifact upload to host R2. Gated by
`host_api.upload` (method surface) **plus** the per-app `upload_grant`.

| method | status | args | result |
|---|---|---|---|
| `inline` | ✅ | `{ bytes_b64, mime, purpose, filename? }` | `{ file_ref, url }` |
| `negotiate` | ✅ | `{ mime, purpose, size_bytes }` | `{ upload_url, file_ref }` |
| `confirm` | ✅ | `{ file_ref }` | `{ url, … }` |

### `artifact`, `llm`, `fs`, `prefs`

All declared in the dispatcher but stubbed today (`not_implemented`). Plan for Phase 3:

- `artifact.create` / `update` / `delete`
- `llm.complete` (host-side completion bound to the user's quota)
- `fs.read` / `fs.write` (R2-backed workspace, mirrors the Anna Agent FS)
- `prefs.get` (read user preference keys)

## Permissions matrix

`permissions` (top-level on the manifest) acts as a coarse capability gate; `ui.host_api` is the fine-grained ACL. Both are checked.

| Permission | Required for |
|---|---|
| `tools.invoke` | `tools.invoke` |
| `chat.read` | `chat.read_history` |
| `chat.write_message` | `chat.write_message` |
| `chat.append_artifact` | `chat.append_artifact` |
| `artifact.create` / `update` / `delete` | matching `artifact.*` calls |
| `llm.complete` | `llm.complete` |
| `fs.read` / `fs.write` | matching `fs.*` calls |
| `storage.read` | `storage.get`, `storage.list` |
| `storage.write` | `storage.set`, `storage.delete` |
| `prefs.read` | `prefs.get` |
| `ui.svg` | rendering inline SVG inside chat artifacts your app appends |

`agent.session.*`, `image.*`, and `upload.*` are gated by their
`ui.host_api.{agent,image,upload}` entries (the method-level surface) **plus**
the per-app grant enforced inside the facade (`image_grant` / `upload_grant`,
and for agent the user's session quota) — not by a coarse top-level
`permissions` verb.

Anything not declared is rejected with `permission_denied` before reaching the handler.

## Error codes

| Code | When |
|---|---|
| `invalid_token` | JWT expired, signature mismatch, or `wid` does not match `window_uuid` |
| `permission_denied` | `(ns, method)` not in `host_api`, missing top-level permission, or `tool_id` not in `host_api.tools` allow-list |
| `invalid_arg` | Pydantic validation failure on `args` |
| `not_found` | window closed; storage key missing |
| `agent_unavailable` | `tools.invoke` could not route to the user's Anna Agent (no NATS listener) |
| `executa_error` | Executa returned a non-zero error |
| `tool_timeout` | `tools.invoke` exceeded the per-call `timeoutMs` (clamped by `InvokeTimeoutPolicy`); host emitted a best-effort cancel on `matrix.cancel.{client_id}` |
| `subcall_timeout` | A reverse-RPC subcall (storage / image / upload) timed out while the outer `tools.invoke` was still alive; `details.subcall` names the channel |
| `bundle_not_ready` | Returned by `open_view` if the target version's bundle is still `draft` |
| `rate_limited` | Too many in-flight RPCs (per-window cap) |
| `state_too_large` | `storage.set` / runtime_state would exceed 256 KB |
| `not_implemented` | Method exists in the contract but is still a stub |
| `internal_error` | Unhandled server exception (logged) |

For the LLM-facing side of the same surface (`open_app_view` etc.), see [App UI LLM Integration](/developers/apps/app-ui-llm).
