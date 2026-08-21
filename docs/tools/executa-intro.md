---
title: "What is Executa"
description: "Anna's plugin extension system: standalone processes speaking JSON-RPC 2.0 over stdio."
section: tools
slug: executa-intro
order: 1
updated: 2026-04-24
estimated_minutes: 5
---

**Executa** is Anna's plugin extension system. You write a small program in any language; it speaks **JSON-RPC 2.0** over **stdio**; the Anna Agent spawns it, asks what tools it provides, and exposes them to the LLM via NATS RPC.

There is **no SDK** and no embedded runtime. Anything that can read a line and print a line can be an Executa plugin.

## What you'll implement

Three JSON-RPC methods (the third is optional):

| Method | Purpose | Default timeout |
|---|---|---|
| `describe` | Return the manifest (name, version, tools, parameters, credentials) | 5 s |
| `invoke` | Execute one tool with a dict of arguments | 60 s (per-tool overridable) |
| `health` | Optional liveness probe | 3 s |

The Agent runtime handles transport, request IDs, error wrapping, restart, and credential injection.

> [!IMPORTANT]
> **Your plugin must be a long-running stdio server.** It has to keep reading stdin in a loop and only exit on stdin EOF (or when the Agent kills it). A process that exits after answering one `describe` or `invoke` is the single most common bug — the Agent UI will show your plugin as **Stopped** even though `describe` succeeded, and every call pays a fresh cold-start. See [Common pitfalls](#common-pitfalls) below.

## The smallest working plugin

```python
import json, sys

MANIFEST = {
    "name": "hello",
    "display_name": "Hello",
    "version": "0.1.0",
    "description": "Echo text back.",
    "tools": [{
        "name": "echo",
        "description": "Echo input back",
        "parameters": [
            {"name": "text", "type": "string", "description": "Input", "required": True}
        ],
    }],
}

def handle(req):
    method = req["method"]
    if method == "describe":
        return {"result": MANIFEST}
    if method == "invoke":
        params = req.get("params") or {}
        tool = params.get("tool")
        args = params.get("arguments") or {}
        if tool == "echo":
            return {"result": {"success": True, "data": {"text": args.get("text", "")}}}
        return {"error": {"code": -32601, "message": f"Unknown tool: {tool}"}}
    return {"error": {"code": -32601, "message": f"Unknown method: {method}"}}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    payload = handle(req)
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req.get("id"), **payload}) + "\n")
    sys.stdout.flush()
```

Key conventions visible above:

- **`for line in sys.stdin:`** — the loop is mandatory. Never exit after a single request.
- `sys.stdout.flush()` after every response — without it, line-buffered Python may withhold the response until the buffer fills.
- The `invoke` request carries `params.tool` (the tool name) and `params.arguments` (the LLM-supplied dict).
- A successful invoke returns `{"success": true, "data": {...}}` inside `result`. The Agent decodes this into an `InvokeResult` and forwards `data` to the LLM.
- Errors use the JSON-RPC 2.0 `error` frame with standard codes.
- All log lines go to **stderr** — anything on stdout that is not a JSON-RPC frame breaks the protocol.

## Common pitfalls

| Symptom | Root cause | Fix |
|---|---|---|
| UI shows **Stopped** even though `describe` returned a manifest | Process exits after one request instead of looping | Wrap request handling in `for line in sys.stdin:` (or equivalent) and only exit on EOF |
| Plugin shows up under **Extra Agent Plugins** instead of the user-installed card | The Agent installed the plugin under a `tool_id` that differs from the one the user minted on `/executa` (e.g. a dev-registered plugin with no `expected_tool_id`) | Install / register the plugin under the **minted** `tool_id` so the UI can join them — see [Publishing → Stabilise the manifest](/developers/tools/executa-publish#1-stabilise-the-manifest) |
| `describe timeout` on first run for big PyInstaller bundles | Cold start exceeds the default 5 s timeout | Slim the bundle, or rely on the Agent's binary-cold-start timeout (60 s) which kicks in on first scan |
| Garbled responses / `JSON parse error` in Agent logs | Plugin printed a banner / progress text on **stdout** | Move all human-readable logs to **stderr** |

Quick smoke test that catches the long-running bug locally:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"describe"}' | ./my-plugin &
PID=$!
sleep 2
if kill -0 $PID 2>/dev/null; then echo OK; else echo BUG: exited after one request; fi
kill $PID 2>/dev/null
```

## Where to go next

- **Pick a language**: [Python](/developers/tools/executa-python), [Node.js](/developers/tools/executa-nodejs), [Go](/developers/tools/executa-go).
- **Read the spec**: [Protocol Spec](/developers/tools/executa-protocol).
- **Add credentials**: [Credentials](/developers/tools/executa-credentials).
- **Ship a binary**: [Binary Distribution](/developers/tools/executa-binary).
- **Publish**: [Publishing](/developers/tools/executa-publish).

> [!NOTE]
> Runnable samples — including credential and OAuth examples — live in [`whtcjdtc2007/anna-executa-examples`](https://github.com/whtcjdtc2007/anna-executa-examples). Snippets in this hub are extracted from that repo so you can cross-check against working code.
