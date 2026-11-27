---
title: "Lifecycle & Capability Negotiation"
description: "How the Agent spawns, initializes, calls, and shuts down an Executa plugin — including v2 reverse-RPC capability negotiation."
section: tools
slug: executa-lifecycle
order: 6
updated: 2026-11-25
estimated_minutes: 7
verified_runtime: "1.1.0-beta.135"
---

Every Executa plugin runs as a **single, long-running process** that the Matrix Agent owns end-to-end. Understanding the five lifecycle phases — and the v2 capability handshake that gates [Sampling](/developers/tools/executa-sampling) and [Persistent Storage](/developers/tools/executa-storage) — is the prerequisite for everything beyond `invoke`.

![Executa plugin lifecycle](/static/images/developers/executa-lifecycle.svg)

## Five phases

| # | Phase | Direction | Default timeout | Notes |
|---|---|---|---|---|
| 1 | **spawn** | Agent → OS | — | Process started with the user's environment; stdin / stdout / stderr piped. |
| 2 | **initialize** | Agent → Plugin | `5 s` | v2 handshake. Plugin replying with `Method not found` (or timing out) silently downgrades the session to v1. |
| 3 | **describe** | Agent → Plugin | `5 s` (`60 s` on first launch of a binary onefile) | Returns the manifest. The Agent caches it for the rest of the process's life. |
| 4 | **invoke** | Agent → Plugin (loop) | `60 s` per tool, overridable | Hot path. Each request also unlocks **reverse RPC** if v2 was negotiated. |
| 5 | **shutdown** | Agent closes stdin → `SIGTERM` → `SIGKILL` | `5 s` grace | The plugin must keep reading stdin until EOF. Never `exit()` after a single response. |

> [!IMPORTANT]
> If your plugin terminates after one response, the Agent UI marks it **Stopped** even though `describe` returned a valid manifest, and every subsequent call pays a fresh cold-start. See [Common Pitfalls #1](/developers/tools/executa-pitfalls#1-plugin-process-exits-after-one-request).

The Agent also restarts the plugin with exponential backoff on unexpected exit (max **3 attempts**, base delay **1 s**).

## v2 capability handshake

The Agent always tries v2 first. The handshake exchanges two pieces of information:

- **what the host can do for the plugin** — sampling caps, file-transport support, etc.
- **what the plugin will use** — the subset of host capabilities it actually depends on.

### Request (Agent → Plugin)

```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": "2.0",
    "clientInfo": { "name": "matrix-agent", "version": "1.0" },
    "capabilities": {
      "sampling": {
        "modalities": ["text"],
        "maxTokensPerCall": 8192,
        "responseFormat": ["json_object", "json_schema"]
      },
      "fileTransport": true
    }
  }
}
```

### Response (Plugin → Agent)

```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "result": {
    "protocolVersion": "2.0",
    "server_info": { "name": "my-tool", "version": "0.1.0" },
    "capabilities": { "sampling": {} }
  }
}
```

The plugin echoes the negotiated `protocolVersion` and lists the **subset** of host capabilities it intends to invoke. An empty object (`{}`) is fine — it means "I'm aware of this capability, no extra options."

### Fallback to v1

The Agent transparently falls back to protocol **1.1** when:

- the plugin times out on `initialize`,
- the response is a JSON-RPC error with code `-32601` (method not found),
- any other error frame is returned.

v1 plugins keep working, but **lose access to all reverse-RPC features** (sampling, storage, future logging/progress).

## Negotiation is the only gate

The `initialize` handshake is all a plugin needs to use the reverse-RPC surface. There is **no** `host_capabilities` declaration and no per-user toggle: on **every** `invoke` of an installed, enabled Executa the host mints the full token set — `sampling_token`, `storage_token`, `image_token`, `media_token`, `upload_token` (plus `credentials_token` when the manifest maps credentials to OAuth providers). Which reverse RPC you call (`sampling/*`, `storage/*`, `files/*`, `image/*`, `video/*`, `music/*`, `audio/*`, `host/uploadFile`, `agent/*`) is up to you; the user's CU quota is the usage gate.

The one thing a plugin manifest can still declare is a **cross-boundary storage scope**: by default `storage_token.allowed_scopes` is `["tool"]` (your private bucket); declaring `"storage": { "scopes": { "user": "rw" } }` (or the legacy `aps.scope.user.read` / `.write` strings, still accepted) adds `"user"`. See [Persistent Storage](/developers/tools/executa-storage#scopes). Legacy `host_capabilities` strings such as `llm.sample` / `aps.kv` / `aps.files` are ignored (not rejected) — `anna-app validate` warns so you can delete them.

The remaining `*_NOT_GRANTED` errors (`-32001` sampling, `-32021` storage, `-32101` image, `-32201` upload, `-3212x` / `-3214x` / `-3216x` media) mean the Executa is not installed or the user disabled it. On a reverse RPC issued outside an invoke they can also mean the background credentials could not be obtained — see [Background execution](#background-execution).

## Per-invoke context injection

Once v2 is live, every `invoke` request also carries a `context` block beside `tool` and `arguments`:

```json
{
  "method": "invoke",
  "params": {
    "tool": "summarize",
    "arguments": { "text": "…" },
    "context": {
      "credentials":    { "OPENAI_API_KEY": "sk-…" },
      "invoke_id":      "8f1c…",
      "sampling_token": "eyJ…",
      "storage_token":  "eyJ…"
    }
  }
}
```

| Field | Source | Used for |
|---|---|---|
| `credentials` | [Platform Authorization](/developers/tools/executa-authorization) + per-plugin overrides | Talking to third-party APIs |
| `invoke_id` | Auto-minted by the Agent (UUID hex) | Audit correlation; matching reverse RPCs to their invoke |
| `sampling_token` | Nexus, JWT `aud=executa-sampling`, TTL 600 s | `sampling/createMessage` and `agent/*` authorization |
| `storage_token`  | Nexus, JWT `aud=aps-storage`, TTL 600 s | `storage/*` & `files/*` authorization (`allowed_scopes` claim) |
| `image_token` / `media_token` / `upload_token` | Nexus, per-invoke JWTs | `image/*`, `video/*` / `music/*` / `audio/*`, `host/uploadFile` |

Tokens are bound to (`user_id`, `executa_tool_id`, `tool_invoke_id`) and expire shortly after the invoke completes — **never** persist them across invocations. For an Executa bundled with an Anna App, the `storage_token` additionally carries host-attested `app_id`/`app_slug` claims that unlock that App's own `scope="app"` bucket — see [Persistent Storage § Scopes](/developers/tools/executa-storage#scopes) for the exact conditions.

## Background execution

A plugin process outlives every single invoke, and it may issue reverse RPCs at any time: when it starts, from a timer, or from work that continues after an invoke has returned. The host serves those with **background credentials** — the same token set an invoke gets, issued to the Executa itself.

**What counts as outside an invoke.** The Agent matches every reverse RPC to an invoke:

| The request… | Served with |
|---|---|
| carries the `context.invoke_id` of an active invoke | that invoke's tokens |
| carries no `invoke_id` while exactly one invoke is active | that invoke's tokens |
| carries no `invoke_id` while no invoke, or more than one, is active | background credentials |
| carries the `invoke_id` of an invoke that has already finished | background credentials |

The SDKs stamp `invoke_id` on everything issued inside `bind_invoke` (Python) / `bindInvoke` (Node). A task started inside a handler inherits that binding, so work meant to outlive its invoke should detach explicitly:

```python
async def long_running_work():
    with bind_invoke(None):
        ...  # reverse RPCs here are background
```

**What you get**

- **Every reverse RPC an invoke can issue** — storage, files, web, sampling, agent sessions, embeddings, image, video, music, audio, host upload, credentials. There is no separate allow-list.
- **From process start.** It does not depend on an earlier invoke.
- **The same identity as an invoke.** An Executa bundled with an App acts as that App: `scope="app"` is the App's bucket and agent sessions it creates belong to the App. Any other Executa gets its `tool` scope plus the `user` scope it declares.
- **Nothing to manage.** The Agent holds the tokens (valid for 30 minutes) and replaces them ahead of expiry. The plugin never sees them.

**What it costs.** Background calls are billed in CU exactly like calls inside an invoke, and there is no cumulative cap — a loop that keeps calling keeps spending. The user's CU balance is the only limit.

**When it stops**

- **The user disables or uninstalls the Executa.** The next credential rotation is refused; tokens already issued stay valid for at most 30 minutes.
- **The Agent is not running.** A Cloud Agent suspends 120 minutes after its last invoke, and background activity does not keep it awake. The process is frozen with its memory intact and continues on the next invoke.
- **The process restarts** (Agent upgrade, crash). In-memory state is gone — persist what you need.

When background credentials are unavailable, a reverse RPC outside an invoke fails with its family's `*_NOT_GRANTED` code. Agents that predate background execution answer the same way, so code written for it degrades cleanly.

### Backend-owned tasks

Background execution is what lets an Executa own a long task instead of the page:

| Situation | How | Who owns the task and its state |
|---|---|---|
| Ask and answer | `tools.invoke`; reverse RPCs inside the invoke | — |
| **Backend-owned task** — the page only triggers; work continues after the window closes; reopening shows the complete current state | `tools.invoke` to trigger (returns a task id at once), work outside any invoke, `tools.invoke` to read by id | Your Executa |
| Host-managed job — you want the host's progress stream, cancel, timeout and cleanup | [`tools.invokeAsync`](/developers/apps/app-ui-sdk) | The host |
| Work nobody triggers — periodic sync, backup, startup checks | Background, from process start | Your Executa |

Owning the task means owning its progress, cancellation, timeouts and retries, and writing its state somewhere durable (workspace or [Persistent Storage](/developers/tools/executa-storage)). The reference implementation is [`anna-app-background-demo`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/anna-app-background-demo): a health check that runs every reverse RPC family in the background and reports the task's complete state whenever the page asks.

## Health probe (optional)

```json
{ "jsonrpc": "2.0", "method": "health", "id": 99 }
```

```json
{ "jsonrpc": "2.0", "id": 99,
  "result": { "status": "ready", "message": "", "details": {} } }
```

`status` is one of `ready`, `error`, `initializing`. Plugins that omit `health` are treated as healthy (the Agent receives `-32601` and ignores it).

## Shutdown contract

When the Agent wants the plugin gone, it:

1. closes stdin — your loop's `for line in sys.stdin:` should exit cleanly,
2. waits up to 5 s,
3. sends `SIGTERM`, waits another 5 s,
4. sends `SIGKILL`.

> [!TIP]
> Flush buffers and close file handles when stdin closes. Exit non-zero **only** if you actually crashed — the Agent treats non-zero as a fault and counts it against the restart budget.

## See also

- [Protocol Specification](/developers/tools/executa-protocol) — line-delimited JSON-RPC 2.0 wire format.
- [Sampling](/developers/tools/executa-sampling) — `sampling/createMessage` reverse RPC.
- [Persistent Storage](/developers/tools/executa-storage) — `storage/*` & `files/*` reverse RPC.
- [Common Pitfalls](/developers/tools/executa-pitfalls) — including the long-running-process bug.
