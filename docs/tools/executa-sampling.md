---
title: "Sampling — LLM Calls Without an API Key"
description: "Let your plugin ask the host to perform an LLM completion on the user's behalf, with billing and model selection handled by Anna."
section: tools
slug: executa-sampling
order: 9
updated: 2026-06-10
estimated_minutes: 11
---

Sampling lets your plugin invoke an LLM **on the user's behalf** without shipping your own API key, picking a model, or metering quota. The plugin describes the completion in protocol-neutral terms; Anna routes it through the user's preferred provider, charges the user's plan, and returns the result.

It's the Executa equivalent of MCP's [`sampling/createMessage`][mcp]. Available from protocol **v2** onward.

> **Need multi-turn agent runs with tool calls?** Sampling is one request → one response. For stateful, tool-using sessions (and parity with iframe anna-apps), see [Agent Sessions](/developers/tools/executa-agent).

[mcp]: https://modelcontextprotocol.io/

![Sampling reverse RPC flow](/static/images/developers/executa-sampling.svg)

## Why sampling exists

Without sampling, every plugin that wants to summarize / classify / plan would need to:

- ship its own API key (security & compliance liability),
- pick a model and chase deprecations,
- meter usage it cannot see (the user's plan, quotas, billing).

Sampling collapses all three into one capability advertised by the host.

## Three pre-conditions

End-to-end sampling needs **all** of the following:

1. **v2 negotiation.** The host sends `initialize`; the plugin replies with the same `protocolVersion: "2.0"` and lists `capabilities.sampling = {}`. See [Lifecycle](/developers/tools/executa-lifecycle#v2-capability-handshake).
2. **Manifest declaration.** The plugin's `describe` manifest includes `host_capabilities: ["llm.sample"]`. The Anna App publish validator rejects unknown capability strings.
3. **User grant.** The end user enabled sampling for this Executa in their Anna Admin panel. The grant carries `maxCalls` and `maxTokensTotal` per-invoke caps.

If any condition is missing, the host returns `-32008 SAMPLING_NOT_NEGOTIATED` and your reverse RPC is rejected before reaching a model.

## Wire protocol

After v2 is live, every `invoke` request also carries `invoke_id` and `sampling_token` inside `params.context` — see [Lifecycle](/developers/tools/executa-lifecycle#per-invoke-context-injection). While processing the invoke, your plugin **emits a reverse JSON-RPC request on stdout**:

```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "sampling/createMessage",
  "params": {
    "messages": [
      { "role": "user", "content": { "type": "text", "text": "Summarize:\n…" } }
    ],
    "maxTokens": 400,
    "systemPrompt": "You are a concise assistant.",
    "temperature": 0.3,
    "stopSequences": ["\n\n###"],
    "modelPreferences": {
      "hints": [{ "name": "claude-sonnet" }],
      "costPriority": 0.4,
      "speedPriority": 0.4,
      "intelligencePriority": 0.2
    },
    "includeContext": "none",
    "metadata": { "executa_invoke_id": "<the invoke_id>" }
  }
}
```

| Field | Required | Notes |
|---|---|---|
| `messages` | yes | Non-empty array, max **64** entries. Each entry is `{role, content:{type:"text", text}}`. Roles: `user`, `assistant`, `system`. |
| `maxTokens` | yes | Positive integer, capped at host's `maxTokensPerCall` (currently **8 192**). |
| `systemPrompt` | no | Plain text. |
| `temperature` | no | Number. |
| `stopSequences` | no | Array of strings. |
| `modelPreferences` | no | See [Model selection](#model-selection-precedence). Omit to use the user's saved preference. |
| `includeContext` | no | **Phase 1 only accepts `"none"`.** Plugins cannot read the conversation context. |
| `metadata` | no | Free dict. Convention: include `executa_invoke_id` for trace stitching. |
| `responseFormat` | no | Structured-output constraint — `{"type":"json_object"}` or `{"type":"json_schema", "json_schema":{…}}`. See [Structured output](#structured-output-responseformat). |
| `onUnsupported` | no | What to do when the selected model can't honour `json_schema`: `"error"` (default), `"json_object"`, or `"text"`. |

The host replies on stdin (the same channel) with the result:

```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "result": {
    "role": "assistant",
    "content": { "type": "text", "text": "…" },
    "model": "claude-3-5-sonnet-20241022",
    "stopReason": "endTurn",
    "usage": { "inputTokens": 312, "outputTokens": 187, "totalTokens": 499 },
    "_meta": { "provider": "anthropic", "latencyMs": 1432 }
  }
}
```

> [!IMPORTANT]
> The same stdin reader receives **both** Agent-initiated requests and host responses to your reverse RPCs. Distinguish them by the presence of a `method` field — responses have only `id` + `result|error`. The official SDKs do this for you.

## Model selection precedence

When the plugin sends `modelPreferences`, Nexus resolves the model in this order:

```
1. hints[*].name → first active model whose model_name CONTAINS the hint
                   (case-insensitive substring). With costPriority > 0,
                   ties break to cheapest.
2. (no hints / no match) → user.settings.preferred_model
3. (preferred_model unset) → default provider's cheapest active model
```

> [!TIP]
> Plugins should normally **omit `modelPreferences` entirely** so the user's saved preference applies. Hints are for tools whose quality strictly requires a particular model family.

## Structured output (`responseFormat`)

When your tool needs machine-readable output (extraction, classification, anything you'll `JSON.parse`), prompt engineering alone is fragile. `responseFormat` pushes the constraint down to the provider's decoding layer.

Two levels:

**L1 — JSON mode** (`json_object`). Guarantees syntactically valid JSON, no particular shape. Broadly compatible — works with any OpenAI-compatible model and is **not** capability-gated:

```json
{ "responseFormat": { "type": "json_object" } }
```

> [!NOTE]
> With `json_object` the provider requires the word "JSON" to appear in your prompt — keep an instruction like *"Reply with a JSON object containing …"* in the message or system prompt.

**L2 — strict JSON Schema** (`json_schema`). The model output conforms to your schema (provider-enforced constrained decoding):

```json
{
  "responseFormat": {
    "type": "json_schema",
    "json_schema": {
      "name": "summary_analysis",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "summary":  { "type": "string" },
          "keywords": { "type": "array", "items": { "type": "string" } },
          "sentiment": { "type": "string", "enum": ["positive", "neutral", "negative"] }
        },
        "required": ["summary", "keywords", "sentiment"],
        "additionalProperties": false
      }
    }
  },
  "onUnsupported": "json_object"
}
```

### Capability gating & downgrade

Not every model supports strict schemas. `json_schema` is gated on the selected model's `supports_structured_output` flag (set by the Anna admin per model; missing = unsupported). `json_object` is never gated. When the model can't honour `json_schema`, `onUnsupported` decides:

| `onUnsupported` | Behaviour |
|---|---|
| `"error"` *(default)* | Request fails with `-32010 SAMPLING_UNSUPPORTED_RESPONSE_FORMAT`; `error.data` carries `{requested, modelName}`. |
| `"json_object"` | Downgrade to L1 JSON mode. |
| `"text"` | Drop the constraint entirely — plain text generation. |

The host advertises support in its `initialize` request: `capabilities.sampling.responseFormat: ["json_object", "json_schema"]`. Hosts older than this feature simply ignore the params — design accordingly (or check the capability list).

### Schema hard limits

Validated twice (locally by the Matrix agent for fast failure, then authoritatively by Nexus). Violations are `-32004 SAMPLING_INVALID_REQUEST`:

| Limit | Value |
|---|---|
| Serialized schema size | ≤ **32 KB** |
| Nesting depth | ≤ **8** |
| Total nodes (objects + arrays + leaves) | ≤ **512** |
| `json_schema.name` | must match `^[a-zA-Z0-9_-]{1,64}$` |

### Reading the result

`content.text` **stays a string** — parse it yourself. When the request carried `responseFormat`, the response `_meta` gains an informational block:

```json
"_meta": {
  "responseFormat": {
    "requested": "json_schema",
    "applied": "json_object",
    "structuredValid": true,
    "downgraded": true
  }
}
```

- `applied` — what was actually sent to the provider (`null` if dropped via `"text"`).
- `structuredValid` — whether `content.text` parsed as JSON (informational only; **always run your own `json.loads` with a fallback**).
- `downgraded` — `true` when `applied != requested`.

```python
result = await sampling.create_message(
    messages=[...],
    max_tokens=512,
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "summary_analysis", "strict": True, "schema": SCHEMA},
    },
    on_unsupported="json_object",   # degrade gracefully instead of -32010
)
try:
    data = json.loads(result["content"]["text"])
except json.JSONDecodeError:
    data = None   # even with responseFormat, the final parse is yours
```

See the runnable [`summarize_structured` tool in sampling-summarizer](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/python/sampling-summarizer) for the full pattern.

### Testing locally

The dev harness validates `responseFormat` with the same rules as production and synthesises `_meta.responseFormat` in mock mode. To exercise your `onUnsupported` branches without a real model, drive the harness from a mock fixture whose responses omit `json_schema` support:

```bash
anna-app executa dev --dir ./my-plugin --mock-sampling ./sampling-fixture.jsonl
```

## Per-invoke caps

| Cap | Default | Where enforced |
|---|---|---|
| `maxTokens` per call | **8 192** | `DEFAULT_SAMPLING_MAX_TOKENS_PER_CALL` (host) |
| Calls per `invoke_id` | **8** | `sampling_grant.maxCalls`, host-capped at 8 |
| Total tokens per `invoke_id` | **32 000** | `sampling_grant.maxTokensTotal`, host-capped at 32 000 |
| `sampling_token` TTL | **600 s** | JWT `aud=executa-sampling` |
| `includeContext` values | only `"none"` | host rejects others as `-32004 SAMPLING_INVALID_REQUEST` |

Both call-count and total-token caps are **terminal** within the same `invoke_id` — your plugin cannot retry past them; it must shrink the workload or exit gracefully.

## Error codes

All sampling errors come back as JSON-RPC errors with stable codes:

| Code | Name | Meaning |
|---|---|---|
| `-32001` | `SAMPLING_NOT_GRANTED` | User has not enabled sampling for this Executa. |
| `-32002` | `SAMPLING_QUOTA_EXCEEDED` | User account quota exhausted. |
| `-32003` | `SAMPLING_PROVIDER_ERROR` | Upstream LLM provider failed. |
| `-32004` | `SAMPLING_INVALID_REQUEST` | Malformed params (e.g. `includeContext != "none"`, `messages` empty, `responseFormat` schema over limits). |
| `-32005` | `SAMPLING_TIMEOUT` | The completion did not finish in time. |
| `-32006` | `SAMPLING_MAX_CALLS_EXCEEDED` | Per-invoke call-count cap reached. |
| `-32007` | `SAMPLING_MAX_TOKENS_EXCEEDED` | Per-invoke cumulative token cap reached. |
| `-32008` | `SAMPLING_NOT_NEGOTIATED` | Host didn't negotiate v2, or manifest missing `host_capabilities: ["llm.sample"]`. |
| `-32009` | `SAMPLING_USER_DENIED` | User explicitly rejected this sampling request. |
| `-32010` | `SAMPLING_UNSUPPORTED_RESPONSE_FORMAT` | Model can't honour the requested `responseFormat` and `onUnsupported` is `"error"`. `data` = `{requested, modelName}`. |

The structured `error.data.errorCode` carries the symbolic name above for easy switch / match.

## Minimal Python example

```python
import json, sys, uuid, threading, queue

# Two queues — one for Agent requests, one for our own reverse-RPC responses.
agent_requests: queue.Queue = queue.Queue()
host_responses: dict[str, queue.Queue] = {}

def reader():
    for line in sys.stdin:
        msg = json.loads(line)
        if "method" in msg:                 # Agent → us
            agent_requests.put(msg)
        else:                               # response to a reverse RPC
            q = host_responses.pop(msg["id"], None)
            if q is not None:
                q.put(msg)

threading.Thread(target=reader, daemon=True).start()

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()

def sample(invoke_id: str, prompt: str, *, max_tokens: int = 400) -> str:
    rid = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    host_responses[rid] = q
    send({
        "jsonrpc": "2.0", "id": rid, "method": "sampling/createMessage",
        "params": {
            "messages": [{ "role": "user",
                           "content": { "type": "text", "text": prompt } }],
            "maxTokens": max_tokens,
            "includeContext": "none",
            "metadata": { "executa_invoke_id": invoke_id },
        },
    })
    resp = q.get(timeout=90)
    if "error" in resp:
        raise RuntimeError(resp["error"])
    return resp["result"]["content"]["text"]

while True:
    req = agent_requests.get()
    if req["method"] == "describe":
        send({"jsonrpc": "2.0", "id": req["id"], "result": {
            "name": "summarizer", "version": "0.1.0",
            "host_capabilities": ["llm.sample"],
            "tools": [{"name": "summarize", "description": "Summarize text",
                       "parameters": [{"name": "text", "type": "string", "required": True}]}],
        }})
    elif req["method"] == "initialize":
        send({"jsonrpc": "2.0", "id": req["id"], "result": {
            "protocolVersion": "2.0",
            "serverInfo": {"name": "summarizer", "version": "0.1.0"},
            "capabilities": {"sampling": {}},
        }})
    elif req["method"] == "invoke":
        ctx = (req["params"].get("context") or {})
        text = req["params"]["arguments"]["text"]
        try:
            summary = sample(ctx["invoke_id"], f"Summarize:\n{text}")
            send({"jsonrpc": "2.0", "id": req["id"],
                  "result": {"success": True, "data": {"summary": summary}}})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": req["id"],
                  "result": {"success": False, "error": str(e)}})
```

For a polished version with retries, see the upstream
[`examples/python/sampling-summarizer/`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/python/sampling-summarizer).

## SDK summary

| Language | Entry point |
|---|---|
| Python  | [`executa_sdk.SamplingClient.create_message`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/sdk/python/executa_sdk/sampling.py) |
| Node.js | [`new SamplingClient().createMessage()`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/sdk/nodejs/sampling.js) |
| Go      | [`sampling.New(nil).CreateMessage()`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/sdk/go/sampling/sampling.go) |

All three SDKs ship a single-reader / multi-writer dispatcher so you don't have to wire it yourself, and all three expose `responseFormat` / `onUnsupported` (Python: `response_format=` / `on_unsupported=` kwargs; Node: request options; Go: `ResponseFormat` / `OnUnsupported` struct fields).

## Common pitfalls

- **Don't `process.exit()` after writing the invoke result.** Sampling responses arrive asynchronously; exiting early drops in-flight reverse RPCs. Keep the long-running stdin loop. ([Pitfall #1](/developers/tools/executa-pitfalls#1-plugin-process-exits-after-one-request))
- **Always echo `invoke_id` in `metadata`.** Nexus uses it to attribute usage and enforce per-invoke caps.
- **Don't ship API keys.** If you reach for `OPENAI_API_KEY` from env, you almost certainly want sampling instead.
- **Treat `SAMPLING_MAX_TOKENS_EXCEEDED` and `SAMPLING_USER_DENIED` as terminal** — not retryable inside the same invoke.
- **Don't trust `structuredValid` as a parse.** It's informational; always `json.loads` with a fallback — and prefer `onUnsupported: "json_object"` over the default `"error"` unless your tool is useless without strict schemas.

## See also

- [Agent Sessions](/developers/tools/executa-agent) — multi-turn / tool-using extension of this same wire pattern
- [Lifecycle & Capability Negotiation](/developers/tools/executa-lifecycle)
- [Protocol Specification](/developers/tools/executa-protocol)
- [Persistent Storage](/developers/tools/executa-storage) — sister reverse-RPC capability
- [Common Pitfalls](/developers/tools/executa-pitfalls#8-sampling-host_capabilities-not-declared)
