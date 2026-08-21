---
title: "Testing the Plugin"
description: "Test the executa plugin under `executas/` with `anna-executa-test` — pytest fixtures that spawn the plugin under uv run."
section: apps
slug: testing-plugin
order: 18
updated: 2026-04-29
estimated_minutes: 4
category: "Local Development & Testing"
---

# Testing the Executa Plugin

`anna-executa-test` is a **pytest** plugin for the Python (or any
JSON-RPC over stdio) plugin that lives under `executas/<name>/` in your
app project. It spawns your plugin the same way Anna Agent will at
runtime, then drives it with one-shot calls and Hypothesis-generated
fuzz cases.

## Install

```bash
uv pip install anna-executa-test
# or
pip install anna-executa-test
```

The package's own README is the most up-to-date public-API reference;
this page is the integration guide for an Anna App project.

## Project layout

```
my-focus-flow/
├── manifest.json
├── bundle/
└── executas/
    └── timer/
        ├── pyproject.toml          # devDeps: anna-executa-test, pytest
        └── tests/
            └── test_smoke.py
```

## Minimal smoke test

```python
# executas/timer/tests/test_smoke.py
from pathlib import Path
import pytest
from anna_executa_test import executa, assert_jsonrpc_ok

PLUGIN_DIR = Path(__file__).parent.parent

@pytest.fixture(scope="module")
def plugin():
    with executa.spawn(PLUGIN_DIR) as p:
        yield p

def test_describe(plugin):
    info = plugin.call("describe")
    assert info["name"].startswith("tool-")
    assert info["tools"], "plugin should declare at least one tool"

def test_invoke_get_state(plugin):
    resp = plugin.call(
        "invoke",
        {"tool": "session", "arguments": {"action": "get_state"}},
    )
    assert_jsonrpc_ok(resp)
```

## Public surface (Phase 5 MVP)

| Symbol | Purpose |
| --- | --- |
| `executa.spawn(project_dir, *, command=None, env=None)` | Context manager spawning the plugin under `uv run`. Yields an `ExecutaClient`. |
| `ExecutaClient.call(method, params=None, *, timeout=10.0)` | One JSON-RPC round-trip. |
| `ExecutaClient.invoke(tool, arguments)` | Sugar for `("invoke", {"tool", "arguments"})`. |
| `ExecutaClient.describe()` / `.health()` | Standard control methods. |
| `assert_jsonrpc_ok(resp)` | Raises with a useful diff when `success != True`. |
| `assert_jsonrpc_error(resp, code=...)` | Verifies the structured error path. |
| `wire_format.validate_response(env)` | Strict envelope shape check, matches nexus's `executa_wire`. |
| `contract.contract_for(project_dir)` | Reads `pyproject.toml` + spawns briefly to capture `MANIFEST`; exposes `.parametrize_invoke(...)` for Hypothesis fuzzing. |
| `mock_state_dir(tmp_path)` (fixture) | Overrides `XDG_STATE_HOME` so plugins don't leak state. |

## Why "same invoker as Anna Agent"

The stdio client used by `anna-executa-test` is a near-line-for-line
extraction of the path Anna Agent runs in production. If your plugin
passes here, it will pass at runtime — modulo network credentials and
real-time NATS routing, which are by design out of scope.

## Wire-format compliance

Run `pytest -k contract` after writing your tests — `contract_for(...)`
will fuzz `invoke` against your declared `MANIFEST.tools[].parameters`
JSON Schema and assert the response envelope matches the nexus contract.

## Related

- [Local Development](/developers/apps/local-dev)
- [Testing the bundle](/developers/apps/testing-bundle)
- [App Manifest](/developers/apps/app-manifest)
