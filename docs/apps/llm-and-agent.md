---
title: "App-Side LLM & Agent API"
description: "Call llm.complete and run a multi-turn agent session from inside your bundled app."
section: apps
slug: llm-and-agent
order: 16
updated: 2026-06-07
estimated_minutes: 8
category: "App UI"
---

> **Audience:** app authors who want their bundled iframe / SPA to call
> the LLM (`anna.llm.complete`) or run a stateful tool-using agent
> (`anna.agent.session(...)`) from JavaScript.
>
> **Companion:** [Local dev with --llm](local-dev-llm.md) explains how to
> wire a developer PAT so these APIs work outside the desktop client.

This page covers what runs **inside the iframe**. For the auto-injected
UI orchestration tools (`open_app_view` / `update_app_view`), see
[App UI LLM Integration](app-ui-llm.md) — that's a separate, host-side
mechanism and does not require any host_api grant.

---

## 1. Manifest grants

The host enforces ACL by `manifest.ui.host_api`. Two independent grants:

```json
{
  "ui": {
    "bundle": { "entry": "index.html" },
    "views": [{ "name": "main", "default": true }],
    "host_api": {
      "llm": ["complete"],
      "agent": {
        "session": { "auto": true, "fixed": null },
        "tools":   ["tool-yourhandle-search-..."]
      }
    }
  }
}
```

| Field | Effect |
|---|---|
| `llm: ["complete"]` | Allows `anna.llm.complete(...)` from the iframe |
| `agent.session.auto: true` | Allows `anna.agent.session({ submode: "auto" })` |
| `agent.session.fixed: { client_ids: ["..."] }` | Allows `submode: "fixed"` with a pinned executa client_id |
| `agent.tools` | Subset of executa tool ids the agent may invoke |

If neither `auto` nor `fixed` is set, **all** `agent.session.*` calls
return `permission_denied` regardless of namespace.

---

## 2. `anna.llm.complete(req)` — single shot

Stateless completion. Counts against the user's quota; uses the user's
default model.

```js
const reply = await window.anna.llm.complete({
  messages: [
    { role: "user", content: { type: "text", text: "Say hi" } },
  ],
  maxTokens: 256,
});
console.log(reply.role, reply.content.text, reply.usage.totalTokens);
```

Response shape:

```ts
{
  role: "assistant",
  content: { type: "text", text: string },
  model: string,
  stopReason: "endTurn" | "stopSequence" | "maxTokens",
  usage: { inputTokens: number, outputTokens: number, totalTokens: number },
}
```

**Errors** are thrown as `HostRpcError`:

| `error.code` | When |
|---|---|
| `permission_denied` | Manifest doesn't include `llm: ["complete"]` |
| `not_implemented` | Host runtime didn't wire this method (e.g. local harness with `--no-llm`) |
| `quota_exceeded` | User has hit their daily/per-app cap |
| `invalid_arg` | Missing/empty `messages`, bad role, etc. |

---

## 3. `anna.agent.session(...)` — multi-turn tool-using agent

A **session** holds memory + access to a curated set of executa tools.
Ideal for chat-like UX or research workflows.

```js
// 1. Create (mints app_session_token; one per submode per window).
const sess = await window.anna.agent.session({
  submode: "auto",            // host picks the best tool list
  // submode: "fixed", fixed_client_id: "desktop-main"  // pin to one executa
});

// 2. Run a turn — returns a stream you can iterate.
const stream = sess.run({ content: "Find me 3 lunch options nearby" });
for await (const frame of stream) {
  // Status frames carry frame.event ∈ "queued" | "started" | "keepalive"
  //   | "run_meta" | "error" | "end". Token frames are tagged
  //   frame.event === "sse" and carry an OpenAI-style chunk.
  if (frame.event === "sse") {
    const delta = frame.choices?.[0]?.delta;
    if (delta?.content) render(delta.content);          // streamed token text
    // Final usage arrives at delta.task_complete.token_usage.
  }
  if (frame.event === "end") break;   // terminal { event: "end", run_id }, done=true
}

// 3. Optional: history, cancel, delete, list, refresh.
const past = await sess.history();
await sess.cancel(stream.runId);
await sess.delete();
```

### 3.0a Native image inputs (`attachments`)

`run()` accepts an optional `attachments` array so the session's model can
**see images directly** in the same inference as your prompt — no
`upload_local_file` → `analyze_image` tool round-trips, no lossy text
description in between:

```js
const stream = sess.run({
  content: "Check these slides for text overflow or layout issues.",
  attachments: [
    { type: "image/png", url: "https://example.com/slide-1.png" },
    { type: "image/png", url: "https://example.com/slide-2.png", detail: "high" },
    // base64 works too — the host uploads it to storage for you:
    { type: "image/jpeg", data: "<base64 or data: URI>", filename: "photo.jpg" },
  ],
});
```

Rules and semantics:

- **Images only** for now (`image/jpeg|png|gif|webp|bmp|svg+xml`), max **6**
  per run, ≤ 20 MB each. `url` and `data` are mutually exclusive per item.
- `url` must be a **public HTTPS** address (private/internal hosts are
  rejected — SSRF guard). For local files, read them in your app and send
  base64 `data` instead; the platform never reads paths out of `content`.
- Images are visible to the model **for the current run only**. Presigned
  URLs expire and history is stripped of image payloads, so re-attach the
  image if a later turn needs to look at it again.
- The selected model must be vision-capable, or the run fails fast with
  `errorCode: "APP_MODEL_NOT_VISION_CAPABLE"`. Combine with per-run
  `modelPreferences` (e.g. `{ hints: [{ name: "gemini" }] }`) to pick a
  vision model. There is **no** silent fallback to `analyze_image`.
- The same field works on the plugin path: `session.run(content,
  attachments=[...])` in the Python `executa_sdk`, and in the raw
  `POST /copilot/app/agent` body.

The `session({...})` result also carries lifecycle metadata so you can
schedule work around the session's deadlines:

```js
const sess = await window.anna.agent.session({ submode: "auto" });
sess.expiresAt;        // ISO-8601 — the authoritative idle deadline
sess.maxLifetimeAt;    // ISO-8601 — the absolute cap (created_at + max lifetime)
sess.idleTtlSeconds;   // e.g. 1800 — how long the window slides on each activity
sess.appSessionUuid;   // persist THIS (not the token) to resume later
```

### 3.0 Session lifetime — sliding idle window

A session is alive while **both** hold:

1. **Idle window**: it has been active within the last `idleTtlSeconds`
   (agent: 30 min, complete: 15 min by default). Every `run()` slides the
   window forward.
2. **Hard cap**: it is younger than its absolute max lifetime (agent: 24 h,
   complete: 1 h by default). Activity cannot extend a session past this.

`expiresAt = min(now + idleTtl, createdAt + maxLifetime)`.

When a session crosses either deadline it is **expired**. Expired sessions
no longer count toward your concurrency/quota (the host reaps them
automatically — see §4), and any call referencing one fails with
`APP_SESSION_EXPIRED` (HTTP 410). Create a fresh session to continue.

### 3.05 Resume by uuid (survives reloads & restarts)

Persist `appSessionUuid` (NOT the token — tokens are short-lived and
re-minted on demand). On an iframe reload or a CLI restart, hand the uuid
back to any session operation and the host re-mints a fresh token straight
from the live session row — no stale token required:

```js
// after a reload, the app remembers only the uuid
await window.anna.agent.refresh({ app_session_uuid: saved.uuid });
// → { app_session_uuid, expires_in, expires_at, max_lifetime_at, ... }
// or just call run/cancel/delete with the uuid — they self-heal the token.
```

`refresh` both re-mints the token AND slides the idle window. Use it
proactively (e.g. on a timer at ~80% of `idleTtlSeconds`) to keep a session
warm during long idle periods, or reactively on resume. It fails with
`APP_SESSION_EXPIRED` / `APP_SESSION_REVOKED` only when the underlying
session is genuinely gone.

### 3.06 Enumerate & recover sessions

`anna.agent.list({ include_expired?, limit? })` returns the sessions this
app owns (scoped to your app — never another origin's), newest-first:

```js
const { sessions } = await window.anna.agent.list();
for (const s of sessions) {
  // s.app_session_uuid, s.kind, s.submode, s.expires_at, s.max_lifetime_at, ...
}
```

Use it to rebuild UI after losing in-memory handles (multi-tab, reload), or
to clean up leftovers via `refresh`/`delete`.


### 3.1 Each create is a distinct session

Calling `session({ submode, fixed_client_id })` returns a **new**
`app_session_uuid` every time — there is no idempotency collapsing. Two
concurrent `auto` sessions from the same window are two real sessions, which
is what multi-pane / parallel-research UIs need.

If you want to *reuse* a session across re-mounts or reloads, persist its
`appSessionUuid` and resume it via `refresh` (§3.05) — don't rely on
create-time dedupe. Keep your own handle and `delete()` (or let it idle out)
when finished so you don't accumulate sessions.

### 3.2 Stream framing

Each `stream.run()` allocates a `stream_id` (`strm_…`). The host emits
`rpc.stream` events with monotonically increasing `seq` numbers; the SDK
reorders out-of-order frames within a 256-frame buffer. You should **not**
need to deal with this directly — the `for await` loop yields frames in
order and ends after the `done: true` frame.

### 3.3 Concurrency

There is no fixed per-window session cap — create as many concurrent
sessions as your workflow needs. Usage is bounded by your account's quota
(`quota_caps` on each session) rather than a hard count. **Expired sessions
do not count** toward usage: the idle reaper (§4) revokes them, so a session
you forgot to `delete()` frees its slot once it crosses the idle deadline.


---

## 4. Cancellation & cleanup

| Action | Effect |
|---|---|
| `sess.cancel(runId)` | Aborts the in-flight turn; emits a final `complete` frame with `aborted: true` |
| `sess.delete()` | Revokes the `AnnaAppSession` row, frees the concurrency/quota slot. **Works even on an expired session** — release is identity-authed, not token-authed |
| `sess.refresh()` | Re-mints the token and slides the idle window (see §3.05) |
| Idle/hard expiry | A background reaper revokes expired sessions so they stop counting toward quota — you don't have to call `delete()` for *expired* ones |
| Window close | Host auto-revokes sessions belonging to that `window_uuid` after a short grace period |

`delete()` is **token-free**: you can always release a session by its
`app_session_uuid` even after its token expired. This fixes the previous
trap where an expired session could neither be used nor deleted and kept
occupying a quota slot.

After revocation, the row lingers briefly (default 24 h) so it stays
visible/auditable in `list({ include_expired: true })`, then the reaper
hard-deletes it and its conversation checkpoint.

Still, `delete()` sessions you're done with rather than waiting for the idle
timeout — it frees the slot immediately.

---

## 5. Token lifecycle (under the hood)

1. App calls `anna.agent.session(...)` → host mints an
   `app_session_token` (JWT, audience `aps-llm`, type
   `anna_app_session`, ~10 min TTL).
2. Token includes the `app_session_uuid` and the submode/fixed grant.
3. `sess.run()` posts to `/api/v1/copilot/app/agent` with that token.
4. The **token TTL is decoupled from the session lifetime** (§3.0). The
   token is a short-lived *capability*; the `AnnaAppSession` row is the
   durable *identity*. The runtime re-mints the token on demand — on each
   `run()`, on `refresh()`, or automatically when resuming by uuid — so the
   short token TTL never limits how long your session can live (only the
   idle window + hard cap do).

You normally don't see the token at all — it lives in the runtime, keyed by
`app_session_uuid`. Persist the **uuid**, never the token.
For local dev see [local-dev-llm.md](local-dev-llm.md).

### 5.1 Error codes

| `error.name` | code | HTTP | Meaning / what to do |
|---|---|---|---|
| `APP_SESSION_EXPIRED` | `-32017` | 410 | Session crossed its idle or hard deadline. Create a new session. |
| `APP_SESSION_TOKEN_EXPIRED` | `-32018` | 401 | The capability token lapsed but the session is alive. Call `refresh()` (or just retry — `run`/`cancel`/`delete` self-heal the token). |
| `APP_SESSION_REVOKED` | `-32011` | 410 | Session was deleted/revoked. Create a new one. |

Branch on `error.name` (the stable string), not the numeric code.

---

## 6. Quick reference

| Iframe call | Host endpoint | Manifest grant required |
|---|---|---|
| `anna.llm.complete(req)` | `POST /api/v1/copilot/app/complete` | `llm: ["complete"]` |
| `anna.agent.session({...})` | `POST /api/v1/copilot/app/sessions` | `agent.session.auto` or `.fixed` |
| `sess.run({content})` | `POST /api/v1/copilot/app/agent` (SSE) | (covered by session grant) |
| `sess.cancel(runId)` | `POST /api/v1/copilot/app/agent/cancel` | (covered) |
| `sess.refresh()` | `POST /api/v1/copilot/app/sessions/{uuid}/refresh` | (covered) |
| `sess.delete()` | `DELETE /api/v1/copilot/app/sessions/{uuid}` | (covered) |
| `anna.agent.list({...})` | `GET /api/v1/copilot/app/sessions` | (covered) |

> The iframe SDK reaches all of these over its `postMessage` → `/runtime/rpc`
> relay, so the browser never holds an `app_session_token`. The HTTP routes
> above are what the SDK / `matrix` agent / standalone executas call directly.


---

## 7. Testing locally

- Vitest harness: `mountBundle({ manifest })` with `mocks: { "llm.complete": ... }` — see
  [tests/llm-complete-mock.test.ts](https://github.com/talentai/anna-app-cli/blob/main/tests/llm-complete-mock.test.ts).
- CLI: `anna-app dev --llm real|mock|off` — see
  [local-dev-llm.md](local-dev-llm.md).

---

## 8. Plugin parity (stdio Executa plugins)

Stdio Executa plugins reach the **same** `/copilot/app/*` surface as iframe apps,
but never hold a bearer themselves. Use the `executa_sdk` Python SDK:

```python
from executa_sdk import AgentSessionClient, dispatch_message

agent = AgentSessionClient(write_frame=write_frame)

# Wire response routing — same loop you already use for SamplingClient/StorageClient
def on_msg(msg: dict) -> bool:
    return agent.dispatch_response(msg) or sampling.dispatch_response(msg)

# Inside an `invoke`:
session = await agent.create(kind="agent", agent_submode="auto", label="my plugin")
async for frame in session.run("hello world"):
    if frame["event"] == "delta":
        ...
    elif frame["event"] == "final":
        result_text = frame.get("text", "")
await session.delete()
```

Or for L1 stateless completion:

```python
res = await agent.complete(messages=[
    {"role": "user", "content": {"type": "text", "text": "Say hi."}},
], max_tokens=64)
print(res["content"]["text"])
```

**Auth model**: the matrix host injects a per-invoke `sampling_token` into the
plugin's reverse-RPC `ctx`. The host's `ExecutaAgentHandler` uses it to mint
an `app_session_token` against `POST /copilot/app/sessions/from_sampling`,
caches the token internally keyed by `(user_id, plugin_name, app_session_uuid)`,
and **never** returns it to the plugin. All subsequent `agent/session.run|cancel|delete`
calls look the cached token up by `app_session_uuid`.

**Wire format**: `agent/session.run` uses *buffered streaming* in v2 — the host
accumulates SSE frames and returns `{run_id, stream_id, frames: [...], final}`
once the run completes. The SDK iterates those frames so your code is identical
to anna-app's `agent.session().run()`. A future protocol bump will switch to
real-time push without changing the SDK API.

**Manifest**: declare `host_capabilities: ["llm.sample", "llm.agent.auto"]` in
your plugin manifest so users see exactly what they're authorizing. See the
[`executa-agent-demo` example](https://github.com/talentai/anna-executa-examples/tree/main/examples/executa-agent-demo)
for an end-to-end working plugin.

---

## 9. Related

- Design spec: `docs/design/app-llm-and-agent-access.md` (host-side details, security; plugin parity in §17).
- Auto-injected UI tools: [app-ui-llm.md](app-ui-llm.md).
- Manifest reference: [app-ui-manifest.md](app-ui-manifest.md).
