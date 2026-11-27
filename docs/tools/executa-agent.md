---
title: "Agent Sessions — Multi-turn Tool-using Runs"
description: "Drive stateful, tool-using Anna Agent sessions from a stdio plugin via reverse JSON-RPC, with the same surface area as in-iframe anna-apps."
section: tools
slug: executa-agent
order: 10
updated: 2026-11-27
estimated_minutes: 8
---

Sampling ([previous chapter](/developers/tools/executa-sampling)) is **one request → one response**. Agent sessions extend that pattern to **persistent threads, host-executed tools, streaming frames, and cancellation** — the same things an iframe `anna-app` can already do today.

The goal is **plugin/app parity**: a Python plugin and a TypeScript anna-app should be drop-in interchangeable for the same agentic workload. Agent sessions ride the standard v2 handshake (`protocolVersion: "2.0"`) — there is no separate protocol version or capability to negotiate.

## Two API levels

| Level | Method                | Stateful? | Tool calls? | Use case                               |
|------:|-----------------------|:---------:|:-----------:|----------------------------------------|
|   L1  | `agent/complete`      |  no       |  no         | one-shot completion (sugar over sampling) |
|   L2  | `agent/session.*`     |  yes      |  yes        | multi-turn agent runs                  |

L1 is a convenience wrapper — if you only need single-turn text, prefer plain [sampling](/developers/tools/executa-sampling). L2 is what unlocks parity with anna-apps.

## Pre-conditions

End-to-end agent sessions need only **v2 negotiation** — the same handshake as sampling; see [Lifecycle](/developers/tools/executa-lifecycle#v2-capability-handshake). There is nothing to declare in the manifest and no user toggle: every installed, enabled Executa receives a `sampling_token` on each invoke, and that token is what unlocks both L1 (`agent/complete`) and L2 (`agent/session.*`). There are no per-invoke call or token caps; usage is billed to the user's CU balance.

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
| `agent/session.create`  | Mint an app session, return `{app_session_uuid, thread_id, agent_submode, granted_tools}` (`granted_tools` = the session's effective tool set) |
| `agent/session.run`     | Send a user message; frames arrive live while the run is in flight, and the response carries the whole turn as `frames[]` (see *Streaming choice* below) |
| `agent/session.cancel`  | Abort an in-flight `run_id`                         |
| `agent/session.history` | Read the persisted transcript: `{messages, next_cursor, _meta}` (`limit` 1–200, opaque `cursor`) |
| `agent/session.delete`  | Idempotent teardown; evicts the cached token        |
| `agent/session.list`    | List the user's live sessions this Executa can reach: `{sessions: [...]}` (see *Session ownership* below) |
| `agent/session.refresh` | Re-mint the session token by `app_session_uuid` and slide its idle window; also the first call when you pick up a session you did not create |
| `agent/session.run.status` | Point-in-time status of one `run_id` (`queued` / `running` / `completed` / `failed` / `cancelled`) plus its archived `stream_id` |
| `agent/session.frames`  | Replay a run's archived stream by `seq`: `{frames: [{seq, payload, done}], complete}` |
| `agent/session.catalog` | Which platform tools a session created right now would resolve: `{platform_tools, manifest_declared, declared_wildcard, inherit_host_tools?}`. No params; mints no session, consumes no quota |
| `agent/complete`        | Single-turn completion (L1)                         |

The host also sends one **notification** in the other direction — `agent/session.frame`, a live frame of an in-flight `run`. It has no `id` and expects no reply.

### `agent/session.create` params

| Field             | Required | Notes                                                                  |
|-------------------|:--------:|-----------------------------------------------------------------------|
| `kind`            | yes      | `"agent"` (multi-turn agent) or `"fixed"` (single-tool agent)         |
| `agent_submode`   | for `kind=agent`  | `"auto"` (LLM picks tools) only in v2.1                  |
| `fixed_client_id` | for `kind=fixed`  | Tool's `client_id` to single-call against                |
| `label`           | no       | Free-text trace label                                                 |

### Frame shapes (from `agent/session.run`)

`agent/session.run` answers with `{run_id, stream_id, frames, final, frame_count}`. Every frame carries `seq` (0-based, in order) and `stream_id`:

```json
{ "event": "started" }
{ "event": "run_meta", "run_id": "...", "granted_tools": ["..."], "model": "..." }
{ "event": "delta",    "text": "...", "raw": { "choices": [ ... ] } }
{ "event": "complete", "task_complete": { "status": "completed" }, "raw": { ... } }
{ "event": "final",    "text": "<full assistant text>", "synthesized": true }
```

- **`delta`** — one streamed text chunk. The host normalizes the upstream OpenAI-style chunk for you; the original is kept under `raw`.
- **`complete`** — end of the turn (`task_complete` carries status and token usage).
- **`final`** — appended by the host: the concatenation of every `delta`. Also returned as the top-level `final`, so "give me the reply" is `result["final"]["text"]`.
- **`raw`** — any other upstream chunk (for example tool-call activity), passed through under `raw` so it is never mistaken for text.
- Status frames (`queued`, `started`, `run_meta`, `error`) pass through unchanged; `keepalive` is dropped.

## Streaming choice — live frames, authoritative response

`agent/session.run` hands you a turn twice, over the same stdio pipe:

1. **Live.** While the run is in flight, the host pushes each frame to the plugin as an `agent/session.frame` notification as soon as it arrives from upstream. You opt in per request with `stream: true`, and you must send your own `run_id` with it — `run_id` is the only key that ties a notification to its run before the response exists. The Python SDK does both for you.
2. **Complete.** When the turn ends, the JSON-RPC response carries every frame as `frames[]`, in the shape described above.

**The response stays authoritative.** Live frames are the same frames delivered early, never a second stream: `seq` in a notification always equals the frame's index in the response `frames`, and `frame` is identical to `frames[seq]`. Whatever did not reach the plugin live is in the response, so correctness never depends on the live path.

The notification travels host → plugin and has no `id`:

```json
{"jsonrpc":"2.0","method":"agent/session.frame",
 "params":{"run_id":"run_3f9a1c0b7d2e4a55","seq":1,
           "frame":{"event":"delta","text":"Got ","raw":{"choices":[{"delta":{"content":"Got "},"index":0}],"event":"sse"},
                    "seq":1,"stream_id":"strm_8c1d0e2f4a6b7c90"}}}
```

- **`run_id`** — correlates the notification with its run; it is also the key for `agent/session.cancel`.
- **`seq`** — starts at 0; equals `frame.seq` and the frame's index in the response `frames`.
- **`frame`** — a normalized frame, exactly as listed under *Frame shapes*.

Every live notification of a run is written before that run's response. The synthesized `final` frame only exists once the turn closes, so it is never pushed live — it arrives with the response.

### Wire the notification into your stdin loop

The SDK can only yield live frames if your stdin loop hands it the notifications. That is one extra branch next to the response routing you already have:

```python
def handle_message(msg: dict) -> None:
    if "method" not in msg:                    # reply to one of your reverse RPCs
        if not agent.dispatch_response(msg):
            sampling.dispatch_response(msg)
        return
    if agent.dispatch_notification(msg):       # live agent/session.frame
        return
    ...                                        # initialize / describe / invoke / ...
```

`dispatch_notification` returns `True` when it consumed the message and is safe to call from any thread. Business code does not change: `async for frame in session.run(...)` now yields each frame as it arrives and, once the response lands, yields whatever was not delivered live. Frames always come out in `seq` order, without gaps or duplicates — even when your loop handles stdin lines on a thread pool and two notifications overtake each other.

### Fallbacks

There is no capability to negotiate and the protocol version stays `"2.0"`: the plugin asks per request, and a side that does not know about live frames simply behaves as before. Every combination is correct, so the SDK, your plugin, and the host can be upgraded in any order.

| Plugin side | Host side | What you get |
|-------------|-----------|--------------|
| SDK with live frames, stdin loop wired | Host with live frames | Live frames, then the complete response |
| SDK with live frames, stdin loop **not** wired | Host with live frames | Your loop drops the notifications → response only (buffered) |
| SDK with live frames | Older host (ignores `stream`) | Response only (buffered) |
| Older SDK (never sends `stream`) | Host with live frames | The host pushes nothing → response only (buffered) |

Three more behaviors to design for:

- **A slow plugin loses live delivery, not frames.** The host never blocks on a live frame. The first time one cannot be written — more than 1 MiB is already queued on the plugin's stdin, or stdin is closed — the host stops pushing for that run, with no retry and no catch-up. What was pushed is always a contiguous prefix `seq = 0..k`; the rest arrives with the response.
- **Leaving the loop early cancels the run.** If you `break` out of `async for` before the turn ends, the SDK sends a best-effort `agent/session.cancel` for that `run_id`, so the upstream run stops spending quota.
- **A failed run can still have delivered frames.** The response is the usual error and frames that were already pushed are not retracted: business code may see a few frames and then an `AgentError`.

### Limits and recovery

Hard cap: **4096 frames per run**. Exceeding it aborts the run (the host cancels it upstream) with `-32046`.

A single `run` call is bounded by the reverse-RPC budget (600 s). If it times out or the response is lost, do not blindly re-run: ask `agent/session.run.status` whether the run completed (and was charged), then page its output with `agent/session.frames` using the `stream_id` that `run.status` returns. `frames` replays the **archived** stream, so each `payload` is the un-normalized upstream frame (`{"event": "sse", "choices": [...]}` for text), the same shape an iframe app sees.

## Session ownership

**A session belongs to the App that hosts the invoke.** The Executa that calls `agent/session.create` is recorded as the session's *creator*, not as its owner. The platform records the hosting App in the per-invoke `sampling_token`; a plugin cannot choose or override it.

| Where the invoke comes from | The session belongs to |
|-----------------------------|------------------------|
| An App window calling `tools.invoke`, or an async tool job | That App |
| The agent of an agent session calling your tool during a run | Whatever hosts that session |
| The agent calling your tool in the conversation | The conversation |

Sessions that an App's page creates with `anna.agent.session(...)` are unaffected — they belong to that App, as before.

### Tool surface follows the hosting App

| The invoke is hosted by | Tools a session created by your Executa resolves |
|-------------------------|--------------------------------------------------|
| An App | Exactly what a session created by that App's page resolves: server-side tools, plus the host-kit tools the **App** declares in `ui.host_api.agent.tools`. Nothing is inherited from the conversation. See [Tool surface — declaration is consent](/developers/apps/llm-and-agent#11-tool-surface-declaration-is-consent). |
| The conversation | The Executa's own `agent_tools` declaration plus, by default, the conversation's tool kit (`granted_tools` is `["*"]`). |

`agent/session.catalog` answers "what would a session created right now resolve?" for the invoke you are in. Inside an App it reports that App's declaration — a host-kit tool the App did not declare shows `blocked_by: "manifest"`. In the conversation it adds `inherit_host_tools: true`, meaning sessions also get the conversation's tool kit, which the catalog does not enumerate.

### Who can reach a session

- **Inside an App, sessions are shared** between the App's page and every Executa the App invokes. The page's `anna.agent.list()` includes sessions your Executa created, `agent/session.list` returns every live session of that App, and either side can continue a session the other one started. There is no per-creator isolation inside an App: invoking an Executa entrusts it with that App's sessions.
- **In the conversation, each Executa sees only the sessions it created there.** Executas that happen to be called from the same conversation cannot list or reach each other's sessions.
- **Sessions never leave the App that hosts them.** An invoke hosted by one App cannot reach another App's sessions or sessions created in the conversation, and an invoke from the conversation cannot reach an App's sessions — not even sessions the same Executa created there.

A session outside your reach is reported as *not found*; the platform does not reveal whether it exists. Storage scopes are separate and unchanged — see [Persistent Storage](/developers/tools/executa-storage).

To continue a session you did not create — for example one the App's page created — call `agent/session.refresh` with its uuid first. The Anna Agent then holds a token for it, and `run` / `cancel` / `history` / `delete` work as usual. The Python SDK wraps this as `attach`:

```python
session = await agent.attach(app_session_uuid)   # refresh first, then a usable handle
async for frame in session.run("Continue from the page's last message."):
    ...
```

`refresh` does not report the tool surface, so do not rely on `granted_tools` of an attached handle — read the `run_meta` frame of a run instead.

### Migration: declare the tools your sessions need

One behavior changes for existing code: **inside an App, a session created by a bundled Executa no longer inherits the conversation's tools.** It used to get the conversation's full tool kit by default — a wider surface than the App itself was granted. It now resolves the App's declaration, like any other session of that App. The change arrives with the Anna server release that introduces session ownership; there is no flag to opt in or out.

If your App relied on inheritance, declare the tools in the App manifest:

```json
{
  "ui": {
    "host_api": {
      "agent": { "tools": ["fs_read_file", "exec_run"] }
    }
  }
}
```

Use `"tools": ["*"]` for every host-kit tool. The signal that you are affected is in the `warnings` array of the `run_meta` frame:

| `code` | Meaning |
|--------|---------|
| `INHERIT_IGNORED` | The session was created with an explicit `quota_caps.inherit_host_tools: true`, which is ignored for a session hosted by an App. |
| `NO_TOOLS_AVAILABLE` | The run resolved zero tools. Whatever side effects the model claims did not happen. |

Sessions created in the conversation behave as before. Sessions that an Executa created inside an App *before* the change are not recorded as belonging to that App, so they can no longer be reached from it — create a new session (agent sessions expire after 30 minutes of inactivity in any case).

## Local development

Each capability starts at these versions. On anything older, live frames fall back to the buffered response (see *Fallbacks*) and `agent/session.catalog` is rejected as an unknown method (`-32601`).

| Capability | Production | `anna-app dev` | Python `executa-sdk` |
|------------|------------|----------------|----------------------|
| Live frames (`stream: true` → `agent/session.frame`) | The next Anna Agent release | CLI **0.1.68** (local runtime `0.2.0a39`) | **0.4.0** |
| `agent/session.catalog` | The next Anna Agent release, together with the next Anna server release | CLI **0.1.68** (local runtime `0.2.0a39`) | **0.4.0** — `catalog()` |
| `attach()` | Already available — it calls `agent/session.refresh` | CLI **0.1.68** (local runtime `0.2.0a39`) | **0.4.0** |
| Session ownership | The next Anna server release | CLI **0.1.68** — the page and its bundled Executas run as one dev App and share its sessions | — |

Notes for the local tools:

- Sessions minted by `anna-app dev` are dev sessions: their tools are not derived from your manifest declaration. Check the [migration](#migration-declare-the-tools-your-sessions-need) against the platform, not the harness.
- `anna-app executa dev` runs a single Executa without an App. From CLI **0.1.68** it pushes live frames in real mode (a `--mock-agent` fixture is already the complete answer, so nothing is pushed live), but it only implements `create` / `run` / `cancel` / `history` / `delete` and `agent/complete` — use `anna-app dev` for everything else, including `agent/session.catalog` and `attach()`.
- CLI **0.1.68** is also the first version in which `anna-app dev` and `anna-app executa dev` answer `run` in the production shape. Earlier versions of `anna-app dev` answered a bundled Executa with only `{stream_id, run_id}` and routed the frames to the page instead, reported `agent/session.history` as `not_supported`, and rejected `agent/session.list` / `refresh` / `run.status` / `frames` with `-32601` — upgrade rather than working around it.

## Error codes

| Code     | Name                              | Meaning                                        |
|----------|-----------------------------------|------------------------------------------------|
| `-32041` | `AGENT_NOT_GRANTED`               | No `sampling_token` in the invoke context — cannot happen for an installed, enabled Executa |
| `-32042` | `AGENT_INVALID_SUBMODE`           | `kind=agent` without a valid submode           |
| `-32043` | `AGENT_FIXED_REQUIRES_CLIENT_ID`  | `kind=fixed` without `fixed_client_id`         |
| `-32044` | `AGENT_UNKNOWN_SESSION`           | `app_session_uuid` not in the host cache       |
| `-32045` | `AGENT_INVALID_UUID`              | uuid not owned by `(this user, this plugin)`   |
| `-32046` | `AGENT_NEXUS_ERROR`               | Upstream nexus failure                         |
| `-32047` | `AGENT_RUN_TOO_LARGE`             | Run exceeded the 4096-frame buffer cap         |
| `-32048` | `AGENT_TOOL_NOT_GRANTED`          | Requested a tool outside the session's effective tool set (`granted_tools`) |

`AgentError` shares its base class with `SamplingError` in the Python / Node SDKs, so a single `except SamplingError` covers both surfaces.

## Minimal Python example

```python
import sys
from executa_sdk import (
    SamplingClient, AgentSessionClient, AgentError,
)

# both clients share your stdout writer
agent = AgentSessionClient(write_frame=_write_frame)
sampling = SamplingClient(write_frame=_write_frame)

# multi-turn (L2)
session = await agent.create(kind="agent", agent_submode="auto")
async for frame in session.run("Plan my week."):   # yields each frame as it arrives
    if frame["event"] == "delta":
        sys.stderr.write(frame["text"])
    elif frame["event"] == "final":
        reply = frame["text"]
await session.delete()

# continue an existing session by uuid — your own, or one the hosting App's page created
session = await agent.attach(saved_uuid)

# which tools would a session created in this invoke resolve?
catalog = await agent.catalog()

# single-turn (L1) — sugar over sampling
res = await agent.complete(
    messages=[{"role": "user", "content": {"type": "text", "text": "Summarize: ..."}}],
    max_tokens=200,
)
text = res["content"]["text"]
```

In your stdin dispatch loop, route responses by trying both clients in order:

```python
if not agent.dispatch_response(msg):
    sampling.dispatch_response(msg)
```

Messages that do carry a `method` go to `agent.dispatch_notification(msg)` first, so live frames reach `session.run` — see [Wire the notification into your stdin loop](#wire-the-notification-into-your-stdin-loop).

Two complete examples:

- [`examples/anna-app-session-demo`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/anna-app-session-demo) — the authoritative session example: an App that drives every session method over both channels (the page's Host API and a bundled Executa's reverse RPC) and continues the same session across them.
- [`examples/python/executa-agent-demo/`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/python/executa-agent-demo) — a minimal standalone plugin (manifest, both tools `ask_agent` and `ask_complete`).

## Symmetry with anna-app

Same lifecycle and the same underlying stream — the transport and the frame envelope differ. An iframe receives each upstream frame live over `rpc.stream`, in its raw shape; a plugin receives the same frames normalized — live as `agent/session.frame` notifications, and again as the complete array in the response:

```ts
// inside an anna-app iframe
const session = await anna.agent.session({ submode: "auto" });
for await (const frame of session.run({ content: "Plan my week." })) {
  const text = frame.event === "sse" ? frame.choices?.[0]?.delta?.content : undefined;
  if (text) render(text);
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
- **Re-attach a stored `app_session_uuid` before you use it.** The host's token cache is in-process, so after the host restarts — or for a session you did not create — `run` / `cancel` / `history` fail as an unknown session until you call `agent.attach(uuid)` (`agent/session.refresh`). If the session has expired, create a new one.
- **Don't `process.exit()` between `create` and `delete`.** Same rule as sampling — the dispatch loop must stay alive.
- **Treat `AGENT_RUN_TOO_LARGE` as terminal.** Shrink the workload (lower `max_tokens`, narrower toolset) rather than retrying.

## See also

- [Sampling — LLM Calls Without an API Key](/developers/tools/executa-sampling) — the L1 wire pattern this builds on
- [Lifecycle & Capability Negotiation](/developers/tools/executa-lifecycle)
- [Persistent Storage](/developers/tools/executa-storage) — sister reverse-RPC capability
- [App-Side LLM & Agent API](/developers/apps/llm-and-agent) — the same surface from the iframe-app side (parity reference)
