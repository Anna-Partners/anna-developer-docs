---
title: "Quickstart — Python"
description: "Build, smoke-test, and run a Python Executa plugin in under five minutes."
section: tools
slug: executa-python
order: 2
updated: 2026-04-22
estimated_minutes: 5
---

This quickstart walks you through writing a Python plugin from scratch. You'll end with a working `text-tools` plugin that exposes two tools and passes a smoke test.

## Prerequisites

- Python 3.10+
- A terminal

## 1. Create the plugin

```bash
mkdir text-tools && cd text-tools
touch plugin.py
chmod +x plugin.py
```

```python
#!/usr/bin/env python3
"""text-tools — a tiny Anna Executa plugin."""
import json, sys, hashlib

MANIFEST = {
    "name": "text-tools",
    "display_name": "Text Tools",
    "version": "0.1.0",
    "description": "Reverse strings and hash text.",
    "author": "you@example.com",
    "tools": [
        {
            "name": "reverse",
            "description": "Reverse a string.",
            "parameters": [
                {"name": "text", "type": "string", "description": "Input text", "required": True}
            ],
        },
        {
            "name": "sha256",
            "description": "Compute SHA-256 of input text.",
            "parameters": [
                {"name": "text", "type": "string", "description": "Input text", "required": True}
            ],
        },
    ],
}

def invoke(tool: str, args: dict) -> dict:
    if tool == "reverse":
        return {"success": True, "data": {"output": args["text"][::-1]}}
    if tool == "sha256":
        return {"success": True, "data": {"output": hashlib.sha256(args["text"].encode()).hexdigest()}}
    raise ValueError(f"unknown tool: {tool}")

def handle(req: dict) -> dict:
    method = req.get("method")
    if method == "describe":
        return {"result": MANIFEST}
    if method == "invoke":
        params = req.get("params") or {}
        try:
            return {"result": invoke(params.get("tool", ""), params.get("arguments") or {})}
        except ValueError as exc:
            return {"error": {"code": -32601, "message": str(exc)}}
        except Exception as exc:  # noqa: BLE001
            return {"error": {"code": -32603, "message": str(exc)}}
    if method == "health":
        return {"result": {"status": "ready"}}
    return {"error": {"code": -32601, "message": f"unknown method: {method}"}}

def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            payload = {"error": {"code": -32700, "message": str(exc)}}
            req_id = None
        else:
            payload = handle(req)
            req_id = req.get("id")
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, **payload}) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
```

## 2. Smoke-test the protocol

```bash
echo '{"jsonrpc":"2.0","method":"describe","id":1}' | python plugin.py
```

You should see the manifest. Now invoke a tool — note `params.tool` (not `params.name`):

```bash
echo '{"jsonrpc":"2.0","method":"invoke","id":2,"params":{"tool":"reverse","arguments":{"text":"anna"}}}' | python plugin.py
```

Expected response:

```json
{"jsonrpc": "2.0", "id": 2, "result": {"success": true, "data": {"output": "anna"}}}
```

> [!TIP]
> Always send protocol traffic through stdin and route logs to stderr (`print("debug", file=sys.stderr)`). Anything you `print()` to stdout that isn't a valid JSON-RPC message will be ignored — making it the #1 cause of "the plugin loaded but never replies".

## 3. Install on the Agent

Your Agent admin can register the plugin in one of three ways:

- **`uv tool install .`** — publishes a CLI entry point; the Agent picks it up via `uv` distribution.
- **`pipx install .`** — alternative for Python plugins.
- **Local archive** — build a `.tar.gz` (PyInstaller `--onedir` is the recommended path for plugins with native deps), copy it to the Agent, and paste the absolute archive path into the Executa admin form (`distribution_type: local`). The Agent runs the [full v2 install pipeline](/developers/tools/executa-binary#local-archive-distribution-no-urls-no-upload) (extract → versioned dir → atomic symlink), so multi-file binaries with `lib/`, `_internal/`, etc. all work.

See [Publishing](/developers/tools/executa-publish) for the public Hub flow.

## 4. Where to next

- **Add credentials** — [Credentials](/developers/tools/executa-credentials).
- **Ship a single-file binary** — [Binary Distribution](/developers/tools/executa-binary).
- **Read the full spec** — [Protocol Spec](/developers/tools/executa-protocol).
- **See it in context** — [`examples/python/example_plugin.py`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/python/example_plugin.py).
