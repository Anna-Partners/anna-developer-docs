---
title: "App UI Host API"
description: "RPC namespaces and methods your iframe can call on the host, with current implementation status."
section: apps
slug: app-ui-host-api
order: 14
updated: 2026-10-23
estimated_minutes: 6
category: "App UI"
---

Every call from your iframe goes through `postMessage → Host Bridge → POST /api/v1/anna-apps/runtime/rpc → anna_app_rpc_dispatcher.dispatch`. The dispatcher does three things in order:

1. **Auth.** `decode_window_token(t)` against the JWT bound to `(window_uuid, user_id, app_id, version_id, scopes)` (TTL 120s, audience `anna-app-window`).
2. **ACL.** `host_api_allows(manifest, ns, method)` checks `manifest.ui.host_api[ns]` (with `*` and `<id>` wildcards). `window.*` is always allowed. Top-level `permissions` is **never** consulted (display-only legacy; rejected at `schema: 3`).
3. **Per-app grants.** Some namespaces are additionally gated by a user-controlled grant enforced inside the handler/facade: `image_grant`, `media_grant` (`video.*` / `music.*` / `audio.*`), `upload_grant`, `web_grant`, `credentials_grant`, and the install-time `storage_token` scopes for `storage`/`files`.

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
| `invoke` | ✅ | `{ tool_id, method?, args, timeoutMs? }` | `{ result }` — routes via NATS to the user's online Anna Agent; `timeoutMs` clamped to **1–180 s** (default 65 s) |
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

#### Result size and integrity

Successful `tools.invoke` results are delivered to the bundle **verbatim** —
the platform never truncates or rewrites string fields inside a result.
(An earlier server-side 32 000-character clamp, designed for LLM chat context
and mistakenly applied to app data, corrupted HTML and base64 payloads while
still reporting success — removed, forum #320.)

The size contract is instead explicit:

| Channel | Limit | Over-limit behavior |
|---|---|---|
| `tools.invoke` (sync) | **~4 MiB** for the full serialized result (payload + envelopes), bounded by the NATS transport `max_payload` (4 194 304 bytes) | Call rejects with `result_too_large`; `error.details` carries `{size, max, retriable: false}` |
| `tools.invokeAsync` (job) | **256 KB** result cap | Job fails with `result_too_large` |

Content larger than these caps must not be returned inline: upload it via
`host/uploadFile` (Executa side) or APS `files/*` and return a reference
instead. There is **no** intermediate per-string-field limit — payloads such
as a 100 KB HTML document or a 200 KB base64 data URL pass through unchanged
as long as the whole result fits the channel cap.

**Request arguments.** Synchronous `tools.invoke` arguments ride the same
NATS channel as results, so the same **~4 MiB** ceiling (args + envelopes)
applies to the request side. The async channel caps args at **64 KB**
(`invalid_arg` on excess). Ship large inputs by reference (APS `files/*` /
`host/uploadFile`), not inline.

**Local dev parity.** `anna-app dev` (CLI ≥ 0.1.54, `anna-app-runtime-local`
≥ 0.2.0a24) enforces the same **~4 MiB** sync-result boundary with the same
`result_too_large` error — an app hits the limit on your laptop, not in
review. The harness's stdio transport additionally caps any single JSON-RPC
frame at **16 MiB** (sized for inline `host/uploadFile` reverse-RPC frames);
oversized frames are rejected with a structured `frame_too_large` error
(`data: {frame_bytes, max_frame_bytes}`) while the bridge and the plugin
process keep serving subsequent calls. Earlier harness versions failed at
64 KiB with misleading `python bridge exited` / `executa process exited`
errors (forum #338) — upgrade the CLI if you see those.

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
    case "job_quota_exceeded": /* 50 active jobs per user — err.details.{active,max_active,scope} */ break;
    case "long_job_capacity":  /* agent admitted (running+queued) long jobs full —
                                  retry after err.details.retry_after_ms */ break;
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
- Per-user active job quota: **50** (`job_quota_exceeded`; per user, shared
  across apps / windows / agents; counts `queued` + `running`; `details`
  carries `active` / `max_active` / `scope`).
- Per-agent long-job slots: **30 running** (same as the sync `tools.invoke`
  channel); further jobs **queue on the agent** — you receive a progress
  event `{type: "queued", data: {position, max_concurrent}}` and the job stays
  `queued` until a slot frees — up to **100 admitted**; beyond that
  `long_job_capacity` with `details.{max_concurrent, max_admitted, active,
  queued, retry_after_ms}`. In practice the per-user quota is hit first.
  Queue time counts against `timeoutMs`.
- Progress: plugins emit via the Executa SDK's `emit_progress` (budget: 50/s
  per job **and 200/s per user**, excess dropped — heartbeats, `queued` and
  terminal events are never dropped; latest 500 events kept; ≤8 KB each;
  history readable via `getJob` for 24 h after the deadline). Heartbeats
  update `lastHeartbeatAt` but are not pushed.
- **Concurrency is not speed.** Slots only guarantee a burst is never
  rejected. Heavy per-invoke resources (headless browsers, GPU) run inside
  your executa on the agent's sandbox (cloud agents: 4 vCPU / 4 GB) and are
  **not** throttled by the platform beyond these slots — cap them inside
  your executa (e.g. 3–4 concurrent Chrome renders, queue the rest); 30
  parallel renders will OOM the whole agent, not just one job.
- Need more? Post on the forum with your app id and workload shape.
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
| `append_artifact` | ✅ | `{ artifact: { kind: "app_event"\|"text"\|"image"\|…, summary?, data?, payload_ref?, app_slug? } }` — note the **nested `artifact` wrapper** and the `data` field (inline JSON); a flat arg object or a `payload` field is silently dropped | `{ artifact_id }` — attaches a transient card to the current conversation (realtime-only: not persisted, not part of the assistant turn / LLM context yet — thread persistence is a later phase) |
| `read_history` | ⏳ | `{ limit?, before? }` | future |
| `write_message` | ⏳ | `{ role, content }` | future |

### `storage` (per-window `runtime_state`, or APS in nexus)

In the local-dev harness (`anna-app dev`) these handlers operate on the
window's 256 KB `runtime_state` blob. In production they are
overridden at startup to talk to **Anna Persistent Storage (APS)** —
`scope='app'`, `owner_id=window.app_id` — so values are durable across
window lifetimes. ACL: `manifest.ui.host_api.storage` must list the called
method — `storage.get` / `storage.set` / `storage.delete` / `storage.list`
map to `["get", "set", "delete", "list"]` (or `*`).

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
| `session.catalog` | ✅ | `{}` | `{ … }` — the tool/model surface available to sessions of this window |

### `image`

Host-mediated image generation / editing — no provider key in the bundle.
Gated by `host_api.image` (method surface) **plus** the per-app
`image_grant` enforced inside the facade.

| method | status | args | result |
|---|---|---|---|
| `generate` | ✅ | `{ prompt, n?, size?, aspect_ratio?, model?, params?, fit?, reference_image_urls?, modelPreferences? (legacy) }` | `{ images: [{ url, r2_key, width, height, … }], model, requestedSize, size, sizeAdjusted, aspectRatio, fit, params, ignoredParams, usage }` |
| `edit` | ✅ | `{ prompt, image_url, mask_url?, n?, size?, aspect_ratio?, model?, params?, fit? }` | same shape as `generate` |
| `generateAsync` | ✅ 0.29.0 | same as `generate` + `{ clientTag?, idempotencyKey? }` | `{ jobId: 'ijob_…', kind: 'image', state: 'queued', estimatedCostCU, deadlineAt, idempotentReplay }` — async job, see [media page](/developers/apps/app-ui-media#image-async-jobs-re-signing) |
| `editAsync` | ✅ 0.29.0 | same as `edit` + `{ clientTag?, idempotencyKey? }` | same as `generateAsync` (needs `image_grant.allowEdit`) |
| `getJob` | ✅ 0.29.0 | `{ jobId }` | `ImageJobView` — `result.images[].url` re-signed on every call |
| `cancelJob` | ✅ 0.29.0 | `{ jobId }` | `{ jobId, state: 'cancelled', refunded: true }` \| `{ jobId, state: 'running', cancelPending: false }` |
| `listJobs` | ✅ 0.29.0 | `{ state?, clientTag?, limit?, cursor? }` | `{ jobs, nextCursor }` — image jobs only |
| `resign` | ✅ 0.29.0 | `{ r2Keys: string[] }` (1–20) | `{ urls: [{ r2Key, url, expiresIn }] }` — re-sign already-paid artifacts for 7 days; any foreign key → whole call `IMAGE_ASSET_NOT_FOUND` |

**Model selection** mirrors `audio.speak`: `model` (exact, case-insensitive name
from `llm.catalog({ serviceType: 'image_gen' })`) → `modelPreferences.hints`
(legacy, miss falls back silently) → the user's `image_gen` preference →
platform default. An unknown / non-image `model` fails with
`IMAGE_MODEL_UNAVAILABLE (-32110)` and `data.allowed` lists the valid names.

**Size semantics.** Each model declares its size space in
`capabilities.options` (`size.values` + optional `size.custom` constraints,
`aspect_ratio.values`, `resolution.values`; `capabilities.sizeInput` tells you
which one drives the output). `fit` picks the policy:

- `fit: "nearest"` (default — unchanged for existing Apps): the host picks the
  closest supported size **without changing orientation** (a 9:16 request never
  becomes a square), and echoes `requestedSize` / `size` / `sizeAdjusted`.
  If no same-orientation candidate exists it fails rather than silently
  switching orientation.
- `fit: "strict"`: anything outside the declared space fails with
  `IMAGE_SIZE_UNSUPPORTED (-32111)` and `data.allowed = { values, custom }` (or
  `{ aspectRatios, resolutions }` for aspect-ratio models).

Recommended flow: read `options.size.values` (or `aspect_ratio.values`) from the
catalogue, build your picker from it, then request with `fit: "strict"`. The
default may become `strict` in a future Host API major version.

**Params.** `params` carries any key from `capabilities.options`
(`quality`, `resolution`, `output_format`, `enable_web_search`,
`thinking_level`, …; the same keys are still accepted top-level for
compatibility, `params` wins). Values are validated against the model's schema
(`IMAGE_OPTION_INVALID (-32112)`, `data.{key, reason, allowed}`); keys the model
does not declare are dropped and listed in `ignoredParams`. `n` above the
model's `maxN` or your grant's `maxPerCallGenerate` fails with
`IMAGE_PER_CALL_EXCEEDED (-32107)` and `data.allowed.maxN`.

Catalogue entries also carry `isPlatformDefault` (who the host routes to when
the user has no `image_gen` preference) and per-image CU pricing
(`pricing.cuPerImage`, `cuByResolution`, `cuBySizeQuality`, `cuByMaxPixels`,
`surcharges`). Users set an account-level default under `/llm → Specialized
Models`.

### `video`

Host-mediated **async** video generation. Gated by `host_api.video` (method
surface) **plus** the per-app `media_grant.video.enabled`. CU is pre-charged on
submit and settled / refunded at the terminal state; progress arrives as
`media_job` SSE events. Full guide: [App UI Media](/developers/apps/app-ui-media).

| method | status | args | result |
|---|---|---|---|
| `generate` | ✅ | `{ prompt, durationSec?, resolution?, aspectRatio?, imageUrl?, modelHint?, clientTag? }` | `{ jobId, state: 'queued', estimatedCostCU, model, … }` |
| `getJob` | ✅ | `{ jobId }` | `{ jobId, state, progress?, result?: { url, expiresIn, … }, billedCostCU? }` |
| `cancelJob` | ✅ | `{ jobId }` | `{ jobId, state, cancelPending }` |
| `listJobs` | ✅ | `{ state?, limit? }` | `{ jobs: [...] }` |

### `music`

Host-mediated **async** music generation — the video surface in a different
modality. Gated by `host_api.music` **plus** the per-app `media_grant.music.enabled`.
CU is pre-charged on submit (per song / per second / per started minute,
whichever unit the model bills in) and settled / refunded at the terminal state;
progress arrives as the same `media_job` SSE events. Every field is validated
against the resolved model's catalogue entry and a feature it cannot deliver
fails with `MUSIC_FEATURE_UNSUPPORTED` (`data.alternatives`) — never a silent
downgrade. `idempotencyKey` replays the same job for 24 h without a second
charge. Full guide: [App UI Media → Music](/developers/apps/app-ui-media#music-async-jobs).

| method | status | args | result |
|---|---|---|---|
| `generate` | ✅ | `{ prompt, lyrics?, instrumental?, durationSec?, format?, referenceImageUrl?, options?, model?, clientTag?, idempotencyKey? }` | `{ jobId: 'mjob_…', kind: 'music', state: 'queued', estimatedCostCU, deadlineAt, idempotentReplay }` |
| `getJob` | ✅ | `{ jobId }` | `{ jobId, state, progress?, result?: { url, mimeType, durationSec, lyrics?, seed?, expiresIn }, billedCostCU? }` |
| `cancelJob` | ✅ | `{ jobId }` | `{ jobId, state: 'cancelled', refunded: true }` · `{ jobId, state: 'running', cancelPending: false }` |
| `listJobs` | ✅ | `{ state?, clientTag?, limit?, cursor? }` | `{ jobs: [...], nextCursor? }` |

### `audio`

Host-mediated **synchronous** speech synthesis and transcription, plus the
**realtime voice session**. Gated by `host_api.audio` **plus**
`media_grant.audio.{enabled, speak, transcribe}` — each sync operation has its
own user flag; `session` needs **both**. Full guides: [App UI Media](/developers/apps/app-ui-media)
(sync) · [App UI Audio Session](/developers/apps/app-ui-audio-session) (realtime).

| method | status | args | result |
|---|---|---|---|
| `speak` | ✅ | `{ text, voice?, format?, speed?, delivery?, modelHint? }` | `{ url \| audioBase64, durationSec, model, billedCostCU }` |
| `transcribe` | ✅ | `{ audioBase64 \| audioUrl, format?, language?, modelHint? }` | `{ text, language, durationSec, model, billedCostCU }` |
| `session` | ✅ **bridge-local** | `anna.audio.session({ llm: 'agent' \| 'none', system?, context?, voice?, language?, speed?, maxDurationSec? })` | `VoiceSession` — `sendAudio` / `flushAudio` / `setContext` / `say` / `interrupt` / `end`; events `asr_* llm_* tts_* say_* interrupted ended …` |

`session` is not a dispatcher RPC: the SDK posts `audio.session.{open, send,
flush, context, say, interrupt, close}` and the **host page's bridge** handles
them locally over its own WebSocket to `/api/v1/anna-apps/runtime/voice`
(nothing reaches `/runtime/rpc`). Declaring `session` also implies the
`microphone` browser permission (iframe `allow="microphone 'src'"` +
`Permissions-Policy: microphone=(self)`); `llm: 'agent'` additionally
requires a `host_api.agent.session` submode. Recording for `transcribe`
without a session needs an explicit `"browser_permissions": ["microphone"]`
in `manifest.ui` — `host_api` is the RPC ACL, browser features are declared
separately. See [App UI Browser Permissions](/developers/apps/app-ui-browser-permissions).

### `upload`

Invoke-scoped, transient artifact upload to host R2. Gated by
`host_api.upload` (method surface) **plus** the per-app `upload_grant`.

| method | status | args | result |
|---|---|---|---|
| `inline` | ✅ | `{ bytes_b64, mime, purpose, filename? }` | `{ file_ref, url }` |
| `negotiate` | ✅ | `{ mime, purpose, size_bytes }` | `{ upload_url, file_ref }` |
| `confirm` | ✅ | `{ file_ref }` | `{ url, … }` |

### `artifact`, `fs`, `prefs`

Declared in the dispatcher but stubbed today (`not_implemented`). Plan for Phase 3:

- `artifact.create` / `update` / `delete`
- `fs.read` / `fs.write` (R2-backed workspace, mirrors the Anna Agent FS)
- `prefs.get` (read user preference keys)

`llm.complete` / `llm.stream` / `llm.embed` are **implemented** (host-side calls bound to the user's quota) — see [LLM & Agent](/developers/apps/llm-and-agent); `llm.catalog` (media capability / CU-pricing discovery, returns only the service types this App is granted) is covered in [App UI Media](/developers/apps/app-ui-media#discover-before-you-call). `files.*` (APS object storage), `web.*` (host-managed search/fetch), `apps.*` (launcher) and `credentials.*` (platform accounts) are implemented nexus-side; `mobile.*` executes only inside the anna-mobile shell. See the namespace table in [App UI Manifest](/developers/apps/app-ui-manifest#host_api) for their method lists.

## ACL & per-app grants

What actually gates a call, in order:

1. **`ui.host_api.<ns>`** must list the method name (or `*`); `window.*` is always allowed; `agent` uses an object spec (`session.auto` / `session.fixed`).
2. **Per-app user grants** for some namespaces, enforced inside the facade: `image_grant` (`image.*`), `media_grant` (`video.*` / `music.*` / `audio.*`), `upload_grant` (`upload.*`), `web_grant` (`web.*`), `credentials_grant` (`credentials.*`), and the install-time `storage_token` `allowed_scopes` claim for non-default `storage`/`files` scopes.

The top-level manifest `permissions` list is **not** part of this chain — it has zero enforcement sites, is display-only on `schema ≤ 2`, and is rejected at `schema: 3` (permission display is derived from `ui.host_api` + the storage declaration instead).

Anything not declared is rejected with `permission_denied` before reaching the handler.

**Which manifest supplies the ACL?** The one projected onto the window's
bound version row. For published installs that is the installed (frozen)
version. For **working-draft installs** (`0.0.0-draft`) the manifest is
re-projected on every `anna-app apps push` — newly declared `ui.host_api`
methods take effect immediately for already-open draft windows, no
reinstall or refresh needed. Per-app **grants** (llm / image / upload /
executa installs) are still written only at `apps install`, so a brand-new
grant-backed namespace needs one install even though the ACL gate already
passes.

## Error codes

| Code | When |
|---|---|
| `invalid_token` | JWT expired, signature mismatch, or `wid` does not match `window_uuid` |
| `permission_denied` | `(ns, method)` not in `host_api`, per-app grant disabled, or `tool_id` not in `host_api.tools` allow-list |
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
