---
title: "Protocol Specification"
description: "JSON-RPC 2.0 over stdio — the wire format an Executa plugin must speak."
section: tools
slug: executa-protocol
order: 5
updated: 2026-04-24
estimated_minutes: 9
---

Anna's plugin protocol is **JSON-RPC 2.0 over stdio**, line-delimited (LF). It is intentionally minimal so that any language with stdin/stdout can implement it.

Protocol version: **1.1**.

## Transport

```
+----------+   stdin (request)    +----------+
|          | ------------------->|          |
|  Anna    |                     |  Plugin  |
|  Agent   |   stdout (response) |  Process |
|          | <-------------------|          |
|          |                     |          |
|          |   stderr (logs)     |          |
|          | <- - - - - - - - - -|          |
+----------+                     +----------+
```

### Constraints

1. **stdout is for protocol responses only.** Each line must be one JSON object. Non-JSON lines on stdout are tolerated (debug-logged) but are *never* interpreted as results.
2. **stderr is for logs.** The Agent captures it and surfaces it in the trace view.
3. **One message per line**, terminated by `\n`. No `Content-Length` headers.
4. **UTF-8** encoding.
5. **Single-line per response ≤ 2 MiB.** Beyond ~512 KiB use the [file transport](#file-transport-large-responses) escape hatch.
6. **The plugin process is long-running.** It MUST keep reading stdin in a loop and only exit on stdin EOF (the Agent closes stdin to request shutdown) or on an explicit signal. A process that exits after sending a single response is a protocol violation — the Agent will mark it as **Stopped** and pay a fresh cold-start on every subsequent invocation. After writing each response, **flush stdout** before looping back to read the next request.

## Methods

### `describe`

Called once after the runtime spawns the plugin.

**Request:**

```json
{ "jsonrpc": "2.0", "method": "describe", "id": 1 }
```

**Response (Manifest):**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "name": "my-tool",
    "display_name": "My Tool",
    "version": "1.0.0",
    "description": "What this plugin does.",
    "author": "Your Name",
    "homepage": "https://example.com/my-tool",
    "icon": "🔧",
    "category": "productivity",
    "license": "MIT",
    "tools": [
      {
        "name": "do_something",
        "description": "Description shown to the LLM.",
        "timeout": 60,
        "streaming": false,
        "parameters": [
          { "name": "input_text", "type": "string", "description": "Input.", "required": true },
          { "name": "count", "type": "integer", "description": "Repeat count.", "required": false, "default": 1 },
          { "name": "tags", "type": "array", "items": {"type": "string"}, "description": "Tag list.", "required": false }
        ]
      }
    ],
    "credentials": [
      {
        "name": "MY_API_KEY",
        "display_name": "My API Key",
        "description": "Get one at https://example.com/keys",
        "required": true,
        "sensitive": true
      }
    ],
    "runtime": { "type": "uv", "min_version": "0.1.0" }
  }
}
```

#### Manifest fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Lowercase kebab/snake label. **Not** the canonical identity — the registry mints a stable `tool_id` at publish time and the Agent joins installs to running plugins by that `tool_id`, so a mismatch between this `name` and the minted `tool_id` no longer matters. |
| `display_name` | string | no | Defaults to `name` |
| `version` | string | yes | SemVer (`MAJOR.MINOR.PATCH`) |
| `description` | string | yes | One-paragraph description |
| `author` | string | no | Free text |
| `homepage` | string | no | Documentation / source URL |
| `icon` | string | no | Emoji or URL (defaults to `🔧`) |
| `category` | string | no | Free-form grouping (`general` by default) |
| `license` | string | no | SPDX identifier |
| `tools` | list | yes | At least one tool definition |
| `credentials` | list | no | Declared secrets the Agent will inject — see [Credentials](/developers/tools/executa-credentials) |
| `runtime` | object | no | Free-form runtime hints (e.g. `{"type": "uv", "min_version": "0.1.0"}`) |

#### Tool definition

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Unique within the plugin |
| `description` | string | yes | Prompt the LLM uses to choose this tool |
| `parameters` | list | no | Empty list = no arguments |
| `timeout` | integer | no | Per-tool execute timeout in seconds (default 60) |
| `streaming` | boolean | no | Reserved for future use |

#### Parameter schema

Fields per parameter: `name`, `type`, `description`, `required` (default `true`), `default`, `enum`, plus `items` / `items_type` for arrays.

Supported `type` values: `string`, `integer`, `number`, `boolean`, `array`, `object`.

For `array`, declare element type either as the standard JSON Schema `"items": {"type": "string"}` or as the protocol shorthand `"items_type": "string"`. The Agent accepts both. If neither is provided, `array` defaults to a list of strings (so the LLM does not pass JSON-encoded strings).

### `invoke`

Invoke a tool. **Note the param shape uses `tool`, not `name`.**

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "invoke",
  "id": 2,
  "params": {
    "tool": "do_something",
    "arguments": { "input_text": "hello", "count": 3 },
    "context": { "credentials": { "MY_API_KEY": "sk_..." } }
  }
}
```

`params.context.credentials` is injected by the Agent only when the user has configured the plugin's credentials. The LLM never sees this object.

**Successful response (`InvokeResult` shape):**

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "success": true,
    "data": { "output": "hellohellohello" },
    "duration_ms": 12
  }
}
```

The Agent decodes `result` as `{success, data, error, duration_ms}`. Whatever you put under `data` is what the LLM will see. `duration_ms` is optional; the Agent measures wall-clock time on its end as well.

**Tool-level failure** (a recoverable error — the LLM should be told about it):

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": { "success": false, "error": "city not found" }
}
```

### `health`  *(optional)*

```json
{ "jsonrpc": "2.0", "method": "health", "id": 3 }
```

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": { "status": "ready", "message": "", "details": {} }
}
```

`status` must be one of `ready`, `error`, `initializing`. The runtime polls this when an admin triggers a health check; you may omit the method (the call returns method-not-found and is treated as healthy).

## JSON-RPC errors

For unrecoverable errors (parse failure, unknown method, runtime exception) return the standard JSON-RPC error frame:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": { "code": -32601, "message": "Unknown tool: do_something" }
}
```

| Code | Meaning |
|---|---|
| `-32700` | Parse error |
| `-32600` | Invalid request |
| `-32601` | Method / tool not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |
| `-32000` to `-32099` | Implementation-defined server error |

> [!TIP]
> Use `result.success = false` for *expected* failures ("city not found", "rate limited"). Use the JSON-RPC `error` frame for *programmer* errors ("unknown tool", "missing argument"). The Agent treats them differently in the trace view.

## Default timeouts

| Method | Default | Override |
|---|---|---|
| `describe` | 5 s | not configurable |
| `health` | 3 s | not configurable |
| `invoke` | 60 s | per-tool via `tools[].timeout` |

If your plugin needs longer for a specific tool, declare `"timeout": 600` on that tool entry. Plugins exceeding their declared timeout receive `SIGTERM` and the request resolves with a JSON-RPC timeout error.

## Lifecycle

1. The Agent spawns the plugin executable with the user's environment.
2. It immediately sends `describe` and waits up to 5 s.
3. Each tool invocation sends `invoke`; per-tool timeouts apply.
4. On idle / shutdown the runtime sends `SIGTERM` and waits up to 5 s before `SIGKILL`.
5. If the process exits unexpectedly, the runtime restarts it with exponential backoff (up to 3 attempts).

> [!IMPORTANT]
> Handle `SIGTERM` cleanly. Flush buffers, close file handles. Exit non-zero only if you actually crashed.

## Protocol v2 — `initialize` & reverse RPC

Executa **2.0** adds an `initialize` capability handshake and a reverse-RPC channel that lets a plugin ask the host for LLM completions or persistent storage. v1 plugins keep working: if a plugin returns `method-not-found` on `initialize`, the host falls back to v1 transparently.

The wire details, error codes, and worked examples live in dedicated pages:

- [Lifecycle & Capability Negotiation](/developers/tools/executa-lifecycle) — `initialize` handshake, per-invoke context injection.
- [Sampling](/developers/tools/executa-sampling) — `sampling/createMessage` reverse RPC.
- [Persistent Storage](/developers/tools/executa-storage) — `storage/*` and `files/*` reverse RPCs (scope-parameterised: `user` / `app` / `tool`).

### Reverse-RPC ↔ parent-invoke correlation

Every reverse RPC runs on behalf of exactly one in-flight `invoke`. The host injects `params.context.invoke_id` into each forward `invoke`; the plugin **must echo it back** in the reverse-RPC `params`:

```json
{
  "jsonrpc": "2.0",
  "id": "req-7",
  "method": "host/uploadFile",
  "params": {
    "mode": "confirm",
    "r2_key": "exec-uploads/…",
    "context": { "invoke_id": "<the parent invoke's invoke_id>" }
  }
}
```

The official SDKs stamp this automatically once the tool handler is wrapped (Python `with bind_invoke(params): …`, Node `bindInvoke(params, () => …)`, Go `InlineRequest.InvokeID` / `Client.SetInvokeID`). Host routing rules:

| Situation | Host behavior |
| --- | --- |
| `context.invoke_id` matches an active invoke | Route to that invoke's context (token, deadline, quota). |
| `context.invoke_id` unknown / already finished | Error `-32602` with `errorCode: UNKNOWN_INVOKE_CONTEXT`. |
| Field omitted, exactly **one** invoke active | Fall back to it (legacy-SDK compatible). |
| Field omitted, **multiple** invokes active | Error `-32602` with `errorCode: MISSING_INVOKE_CONTEXT` — the host never guesses. |

> [!IMPORTANT]
> Plugins that serve concurrent `tools.invoke` calls **must** propagate `context.invoke_id`, otherwise reverse RPCs fail deterministically with `MISSING_INVOKE_CONTEXT` instead of being silently attributed to the wrong invoke (e.g. `host/uploadFile confirm` rejecting with `r2_key does not belong to this invoke`).

## File transport (large responses)

For results larger than ~512 KiB you can write the full JSON-RPC response to a temporary file and send a pointer instead:

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "__file_transport": "/tmp/executa-resp-XXXXXX.json"
}
```

The Agent reads the file, decodes the response inside it, then deletes the file. Use this when you would otherwise blow past the 2 MiB readline ceiling. See the Python sample's `send_response()` for a reference implementation: [`examples/python/example_plugin.py`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/python/example_plugin.py).

## Reference

The normative protocol definition is the [protocol spec in `anna-executa-examples`](https://github.com/whtcjdtc2007/anna-executa-examples) together with the Anna Agent runtime that implements it. All field names, defaults, and error codes above match the runtime exactly.
