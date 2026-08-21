---
title: "Agent Sessions — Multi-turn Tool-using Runs"
description: "Drive stateful, tool-using Anna Agent sessions from a stdio plugin via reverse JSON-RPC, with the same surface area as in-iframe anna-apps."
section: tools
slug: executa-agent
order: 10
updated: 2026-05-15
estimated_minutes: 8
---

Sampling ([previous chapter](/developers/tools/executa-sampling)) is **one request → one response**. Agent sessions extend that pattern to **persistent threads, host-executed tools, streaming frames, and cancellation** — the same things an iframe `anna-app` can already do today.

The goal is **plugin/app parity**: a Python plugin and a TypeScript anna-app should be drop-in interchangeable for the same agentic workload. Available from protocol **v2.1** onward.

## Two API levels

| Level | Method                | Stateful? | Tool calls? | Use case                               |
|------:|-----------------------|:---------:|:-----------:|----------------------------------------|
|   L1  | `agent/complete`      |  no       |  no         | one-shot completion (sugar over sampling) |
|   L2  | `agent/session.*`     |  yes      |  yes        | multi-turn agent runs                  |

L1 is a convenience wrapper — if you only need single-turn text, prefer plain [sampling](/developers/tools/executa-sampling). L2 is what unlocks parity with anna-apps.

## Pre-conditions

End-to-end agent sessions need **all** of:

1. **v2 negotiation.** Same handshake as sampling — see [Lifecycle](/developers/tools/executa-lifecycle#v2-capability-handshake).
2. **Manifest declares both grants:**
   ```json
   { "host_capabilities": ["llm.sample", "llm.agent.auto"] }
   ```
   `llm.sample` unlocks L1 (`agent/complete`); `llm.agent.auto` unlocks L2 (`agent/session.*`). Without `llm.agent.auto` the host returns `-32041 AGENT_NOT_GRANTED`.
3. **User grant.** The end user enabled the agent capability for this Executa in Anna Admin. The grant carries the same per-invoke token caps as sampling, plus a `granted_tools` whitelist.

## Auth chain (no bearer token in the plugin)

Just like sampling, every `invoke` carries a `sampling_token` in `params.context`. The host uses **that token** to mint an `app_session_token` against nexus's `POST /copilot/app/sessions/from_sampling` endpoint, then **caches the token in-process** keyed by `(user_id, plugin_name)`. The plugin only ever sees opaque `app_session_uuid`s.

```
plugin                     matrix host                       nexus
  │                             │                              │
  │── agent/session.create ────►│                              │
  │  (sampling_token in ctx)    │── POST /sessions/            │
  │                             │     from_sampling            │
  │                             │     Bearer = sampling_token  │
  │                             │◄── {app_session_uuid, token, │
  │                             │     thread_id, ...}          │
  │                             │   (host caches token)        │
  │◄── {app_session_uuid, ...} ─│   (token stripped from result)│
```

This is **symmetric to sampling** — the plugin is never trusted with a long-TTL credential. The cache is bounded (LRU, ~4096 entries) and an `agent/session.delete` immediately evicts the entry.

## Reverse RPC methods

| Method                  | Purpose                                              |
|-------------------------|------------------------------------------------------|
| `agent/session.create`  | Mint an app session, return `{app_session_uuid, thread_id, agent_submode, granted_tools}` |
| `agent/session.run`     | Send a user message, receive an array of frames     |
| `agent/session.cancel`  | Abort an in-flight `run_id`                         |
| `agent/session.history` | (deferred — returns `[]` until v2.2)                |
| `agent/session.delete`  | Idempotent teardown; evicts the cached token        |
| `agent/complete`        | Single-turn completion (L1)                         |

### `agent/session.create` params

| Field             | Required | Notes                                                                  |
|-------------------|:--------:|-----------------------------------------------------------------------|
| `kind`            | yes      | `"agent"` (multi-turn agent) or `"fixed"` (single-tool agent)         |
| `agent_submode`   | for `kind=agent`  | `"auto"` (LLM picks tools) only in v2.1                  |
| `fixed_client_id` | for `kind=fixed`  | Tool's `client_id` to single-call against                |
| `label`           | no       | Free-text trace label                                                 |

### Frame shapes (from `agent/session.run`)

```json
{ "event": "delta",       "text": "..." }
{ "event": "tool_call",   "name": "search_web", "args": {...}, "call_id": "..." }
{ "event": "tool_result", "call_id": "...", "ok": true, "data": {...} }
{ "event": "final",       "text": "...", "usage": {...} }
```

## Streaming choice — buffered v2

`agent/session.run` is **buffered** in v2.1: the host accumulates SSE frames until `done=true`, then returns the whole array in a single JSON-RPC response. The SDK exposes them as `async for frame in session.run(...)` so business code does not change when the host switches to true real-time streaming in v2.2.

Hard cap: **4096 frames per run**. Exceeding returns `-32047 AGENT_RUN_TOO_LARGE`.

## Error codes

| Code     | Name                              | Meaning                                        |
|----------|-----------------------------------|------------------------------------------------|
| `-32041` | `AGENT_NOT_GRANTED`               | Manifest missing `llm.agent.auto`              |
| `-32042` | `AGENT_INVALID_SUBMODE`           | `kind=agent` without a valid submode           |
| `-32043` | `AGENT_FIXED_REQUIRES_CLIENT_ID`  | `kind=fixed` without `fixed_client_id`         |
| `-32044` | `AGENT_UNKNOWN_SESSION`           | `app_session_uuid` not in the host cache       |
| `-32045` | `AGENT_INVALID_UUID`              | uuid not owned by `(this user, this plugin)`   |
| `-32046` | `AGENT_NEXUS_ERROR`               | Upstream nexus failure                         |
| `-32047` | `AGENT_RUN_TOO_LARGE`             | Run exceeded the 4096-frame buffer cap         |
| `-32048` | `AGENT_TOOL_NOT_GRANTED`          | Requested a tool not in `granted_tools`        |

`AgentError` shares its base class with `SamplingError` in the Python / Node SDKs, so a single `except SamplingError` covers both surfaces.

## Minimal Python example

```python
import sys
from executa_sdk import (
    SamplingClient, AgentSessionClient, AgentError,
)

agent = AgentSessionClient()
sampling = SamplingClient()  # share the stdout writer
agent.attach_writer(_write_frame)
sampling.attach_writer(_write_frame)

# multi-turn (L2)
session = await agent.create(kind="agent", agent_submode="auto")
async for frame in session.run("Plan my week."):
    if frame["event"] == "delta":
        sys.stderr.write(frame["text"])
    elif frame["event"] == "tool_call":
        ...
await session.delete()

# single-turn (L1) — sugar over sampling
text = await agent.complete(prompt="Summarize: ...", max_tokens=200)
```

In your stdin dispatch loop, route responses by trying both clients in order:

```python
if not agent.dispatch_response(msg):
    sampling.dispatch_response(msg)
```

For a polished version (manifest, grant flags, both tools `ask_agent` and `ask_complete`), see the upstream [`examples/python/executa-agent-demo/`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/python/executa-agent-demo).

## Symmetry with anna-app

Same lifecycle, same frame shapes, same grant gating — only the transport differs (postMessage in iframe, stdio JSON-RPC in plugin):

```ts
// inside an anna-app iframe
const session = await anna.agent.session({ submode: "auto" });
for await (const frame of session.run("Plan my week.")) {
  if (frame.event === "delta") process.stdout.write(frame.text);
}
await session.delete();
```

## SDK summary

| Language | Entry point                                                                                                                                       |
|----------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| Python   | [`executa_sdk.AgentSessionClient`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/sdk/python/executa_sdk/agent.py)               |
| Node.js  | _(planned for v2.2)_                                                                                                                              |
| Go       | _(planned for v2.2)_                                                                                                                              |

## Common pitfalls

- **Always declare both `llm.sample` and `llm.agent.auto`.** L1 (`agent/complete`) is gated by `llm.sample`; L2 by `llm.agent.auto`. Missing either gives `-32041` with no further hint.
- **Never persist the `app_session_uuid` across plugin process restarts.** The host's token cache is in-process; a restart invalidates every uuid → next call returns `-32044 AGENT_UNKNOWN_SESSION`. Re-create on demand.
- **Don't `process.exit()` between `create` and `delete`.** Same rule as sampling — the dispatch loop must stay alive.
- **Treat `AGENT_RUN_TOO_LARGE` as terminal.** Shrink the workload (lower `max_tokens`, narrower toolset) rather than retrying.

## See also

- [Sampling — LLM Calls Without an API Key](/developers/tools/executa-sampling) — the L1 wire pattern this builds on
- [Lifecycle & Capability Negotiation](/developers/tools/executa-lifecycle)
- [Persistent Storage](/developers/tools/executa-storage) — sister reverse-RPC capability
- [App-Side LLM & Agent API](/developers/apps/llm-and-agent) — the same surface from the iframe-app side (parity reference)
