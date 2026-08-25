---
title: "Lifecycle & Capability Negotiation"
description: "How the Agent spawns, initializes, calls, and shuts down an Executa plugin — including v2 reverse-RPC capability negotiation."
section: tools
slug: executa-lifecycle
order: 6
updated: 2026-08-25
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
        "maxCallsPerInvoke": 8,
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

## Manifest declarations vs. runtime capabilities

The negotiation in `initialize` is necessary but not sufficient. To actually use a host capability the plugin must **also** declare it in the `describe` manifest:

```json
{
  "name": "my-tool",
  "version": "0.1.0",
  "host_capabilities": ["llm.sample", "aps.kv"],
  "tools": [ /* ... */ ]
}
```

| Capability string | Unlocks | Reverse RPC methods |
|---|---|---|
| `llm.sample` | [Sampling](/developers/tools/executa-sampling) | `sampling/createMessage` |
| `aps.kv` | [APS](/developers/tools/executa-storage) — KV store | `storage/*` |
| `aps.files` | APS — object/file store | `files/*` |

Which APS *scopes* a plugin may touch (`user` / `tool`) is pinned by the user's storage grant (`allowedScopes`), not by extra capability strings — `storage.user` / `storage.app` / `storage.tool` are **not** valid `host_capabilities` values. See [Persistent Storage](/developers/tools/executa-storage#three-pre-conditions) for the full accepted allow-list.

Without the manifest declaration, Nexus refuses the corresponding reverse RPC at the gate (`-32008 not_negotiated` for sampling, `-32021 not_granted` for storage).

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
| `invoke_id` | Auto-minted by the Agent (UUID hex) | Audit correlation; reverse-RPC budget keying |
| `sampling_token` | Nexus, JWT `aud=executa-sampling`, TTL 600 s | `sampling/createMessage` authorization |
| `storage_token`  | Nexus, JWT `aud=aps-storage`, TTL 600 s | `storage/*` & `files/*` authorization |

Tokens are bound to (`user_id`, `executa_tool_id`, `tool_invoke_id`) and expire shortly after the invoke completes — **never** persist them across invocations.

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
