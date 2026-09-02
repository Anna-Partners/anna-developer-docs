---
title: "Common Pitfalls"
description: "The bugs that show up most often when authors build Executa plugins, and how to spot them fast."
section: tools
slug: executa-pitfalls
order: 14
updated: 2026-08-31
estimated_minutes: 8
---

If your plugin "installs" but the Anna UI shows it as **Stopped** (or it doesn't appear at all), this is the first page to read. Each pitfall lists the symptom you'll observe, the root cause, and the fix.

---

## 1 · Plugin process exits after one request

**Symptom**

- Manual test works: `echo '{"jsonrpc":"2.0","method":"describe","id":1}' | ./my-plugin` returns a manifest.
- The Agent UI shows the plugin card as **Stopped** immediately after install.
- Each tool call pays a noticeable cold-start delay.

**Cause**

Executa is a **long-running** protocol. The Agent spawns one process per plugin and reuses it for every `describe` / `invoke` / `health`. A plugin that returns from `main()` (or calls `sys.exit()` / `process.exit()` / `os.Exit()`) after handling a single request is broken — every subsequent request triggers a restart, and the UI never observes a live process.

**Fix**

Loop on stdin until EOF. The Agent closes stdin to request shutdown.

```python
# Python
import json, sys
for line in sys.stdin:                     # ← loop until EOF
    line = line.strip()
    if not line: continue
    req = json.loads(line)
    resp = handle(req)
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()                     # ← required
```

```javascript
// Node.js
const readline = require("readline");
const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const req = JSON.parse(line);
  process.stdout.write(JSON.stringify(handle(req)) + "\n");
});
// Don't call process.exit(); let the runtime exit naturally on stdin close.
```

```go
// Go
scanner := bufio.NewScanner(os.Stdin)
scanner.Buffer(make([]byte, 0, 1024*1024), 1024*1024)
for scanner.Scan() {                       // ← loop until EOF
    line := strings.TrimSpace(scanner.Text())
    if line == "" { continue }
    // ... handle and Fprintln(os.Stdout, ...) ...
}
```

**Quick local check**

```bash
./my-plugin <<< '{"jsonrpc":"2.0","method":"describe","id":1}' &
PID=$!
sleep 2
if kill -0 $PID 2>/dev/null; then
  echo "OK — still running"
  kill $PID
else
  echo "BUG — plugin exited after one request"
fi
```

---

## 2 · Three names don't match (`tool_id` vs `describe.name` vs archive `manifest.json` `name`)

**Symptom**

- The plugin appears under **Extra Agent Plugins** in the UI instead of next to the tool you installed.
- Or: the user-installed card shows **Stopped** while a duplicate appears as **Running** elsewhere.
- Or: `~/.anna/executa/bin/` contains a file with a generic name like `tool` instead of your tool ID.

**Cause**

Three identifiers must be **exactly** equal:

| Where | What |
|---|---|
| Anna `/executa` form (Tool ID field) | The `tool_id` minted with the 🪪 button, e.g. `tool-acme-my-tool-abcd1234` |
| Your binary | The `name` field in the manifest your plugin returns from `describe` |
| Archive root `manifest.json` | The `name` field in the JSON file you ship inside the `.tar.gz` / `.zip` |

The Agent UI joins user-installed tools to running plugins by string-matching these three; the archive `manifest.json` `name` also becomes the launcher symlink at `~/.anna/executa/bin/{name}`.

**Fix**

Pick the value once when you mint the `tool_id` and paste it everywhere. `display_name` is for the human-readable label — `display_name: "My Tool"` is fine; only `name` has to match.

---

## 3 · Banner / debug text on stdout

**Symptom**

- Agent log shows `Failed to parse JSON-RPC frame`.
- `describe` times out from the Agent's side even though `echo … | ./my-plugin` works.

**Cause**

You printed something to stdout before — or between — JSON-RPC responses. The Agent only treats lines that parse as JSON objects as protocol frames; banners and stray prints corrupt the stream.

**Fix**

All human-readable output goes to **stderr**:

```python
print("🔌 plugin started", file=sys.stderr)            # ✅
sys.stdout.write(json.dumps(response) + "\n")          # ✅ JSON-RPC only
```

```javascript
console.error("🔌 plugin started");                    // ✅
process.stdout.write(JSON.stringify(response) + "\n"); // ✅
```

---

## 4 · Manifest uses MCP-style `input_schema` instead of `parameters`

**Symptom**

- The plugin loads and the LLM calls the tool, but with **fabricated argument names** like `content`, `input`, or `query` that you never declared.
- Your tool's parameter dict shows up empty or partially filled — yet the tool returns success, so the failure is silent.

**Cause**

Matrix's `ToolDefinition.from_dict` reads the protocol-native `parameters` array. If you ship MCP-flavoured `input_schema` (a JSON Schema object), Matrix sees zero declared parameters; the LLM gets an undocumented tool and hallucinates argument names.

**Fix**

Use the canonical Executa shape:

```json
{
  "tools": [{
    "name": "send",
    "description": "Send a tweet",
    "parameters": [
      { "name": "text", "type": "string", "required": true,
        "description": "Tweet body, ≤ 280 chars" }
    ]
  }]
}
```

Not:

```jsonc
// ❌ Silently ignored by Matrix — produces empty parameter list
"input_schema": {
  "type": "object",
  "properties": { "text": { "type": "string" } },
  "required": ["text"]
}
```

See [Protocol Specification — Parameter schema](/developers/tools/executa-protocol#parameter-schema) for supported types.

---

## 5 · Wrong `result` shape for `describe` vs `invoke`

The two methods are asymmetric — easy to mix up.

**`describe`** returns the manifest **directly** as the `result`:

```json
{ "jsonrpc": "2.0", "id": 1, "result": { "name": "…", "tools": [...] } }    ✅

{ "jsonrpc": "2.0", "id": 1, "result": { "manifest": { … } } }              ❌
```

The wrong shape causes the Agent to log `❌ 无法获取 describe: …: 'name'` and drop the plugin at load time.

**`invoke`** returns a wrapped object inside `result`:

```json
{ "jsonrpc": "2.0", "id": 2,
  "result": { "success": true, "data": { … }, "duration_ms": 12 } }         ✅

{ "jsonrpc": "2.0", "id": 2, "result": { "etag": "…", "count": 5 } }        ❌
```

Without `success: true`, Matrix's `InvokeResult.from_dict` defaults `success = false` and the LLM thinks the call failed — even though your tool ran fine.

---

## 6 · Missing `manifest.json` in multi-file archives

**Symptom**

- After install, the Agent picks the wrong executable (e.g. a helper binary instead of the main one).
- Auxiliary scripts (`bin/post-install.sh`, sub-CLIs) get `Permission denied` at runtime.
- `~/.anna/executa/bin/` ends up with a generic name derived from the URL.

**Cause**

Without `manifest.json`, the Agent walks a five-level fallback (asset `entrypoint` → `bin/{name}` → only-or-first executable) and ZIP archives lose Unix permission bits. Both produce silent footguns when the archive contains more than one executable.

**Fix**

Always ship `manifest.json` at the archive root, even for single-file binaries:

```json
{
  "name": "tool-acme-my-tool-abcd1234",
  "version": "1.0.0",
  "runtime": {
    "binary": {
      "entrypoint": {
        "default":        "bin/my-tool",
        "windows-x86_64": "bin/my-tool.exe"
      },
      "permissions": {
        "bin/my-tool":         "0o755",
        "bin/post-install.sh": "0o755"
      }
    }
  }
}
```

See [Binary Distribution](/developers/tools/executa-binary).

---

## 7 · PyInstaller cold start exceeds the 5 s `describe` timeout

**Symptom**

- The first invocation after a fresh install fails with `describe timeout`. Subsequent calls work.

**Cause**

PyInstaller `--onefile` extracts the bundle to a temp directory on first launch; on a 200 MB+ binary this can take 10–30 s, especially on Apple Silicon under Rosetta or on slow filesystems.

**Fix**

The Agent already grants binary distributions a **60 s** describe timeout for the post-install scan, but the steady-state cap is back to 5 s. Three options, in order of preference:

1. Switch to `--onedir` and ship as a multi-file archive.
2. Reduce bundle size — `--exclude-module`, audit `--collect-all` flags.
3. Move heavy initialization into `invoke` rather than module-import / `describe` time.

---

## 8 · Sampling — `host_capabilities` not declared

**Symptom**

Your plugin issues `sampling/createMessage`, the host returns `error: { code: -32008, message: "not_negotiated" }`, and the Agent log says *"executa X did not declare host_capabilities['llm.sample']"*.

**Cause**

Even after v2 negotiation, Nexus refuses sampling unless the plugin's published manifest **also** declares the capability.

**Fix**

```json
{
  "name": "my-tool",
  "host_capabilities": ["llm.sample"],
  "tools": [ /* ... */ ]
}
```

Re-publish the Executa version and ask users to update. See [Sampling](/developers/tools/executa-sampling#three-pre-conditions).

---

## 9 · Sampling / Storage — plugin exits before reverse RPC completes

**Symptom**

First reverse RPC call works in dev, but in production the result never arrives — Agent logs *"unmatched response id=…"* and the host times out.

**Cause**

The plugin returned the `invoke` result and immediately did `process.exit()` / `sys.exit()`, killing the stdin reader before the reverse-RPC response could be dispatched.

**Fix**

Same as Pitfall #1 — the plugin process must be long-running. The official SDKs (`sdk/{python,nodejs,go}` in [anna-executa-examples](https://github.com/whtcjdtc2007/anna-executa-examples)) ship a single-reader-with-dispatch pattern that handles both Agent requests **and** host responses to your reverse RPCs. Use it.

---

## 9a · Published executa shows no **Permission** button — `UPLOAD_NOT_GRANTED` / `-32201`

**Symptom**

You publish an App with a bundled executa via `anna-app apps publish` (or a standalone `executa publish`). The CLI reports success, the executa installs and runs — but its card on `/executa` has no **Permission** entry, so users cannot grant `host.upload` / `aps.*` / `llm.*`, and the first reverse-RPC call fails, e.g.:

```json
{ "code": -32201, "message": "Upload token missing — host did not authorize host/uploadFile",
  "data": { "errorCode": "UPLOAD_NOT_GRANTED" } }
```

**Cause**

The permission UI and every reverse-RPC token gate read the capability declaration from the executa's **protocol manifest registered on the server** (`manifest_cache`), not from the binary itself. CLI versions before `0.1.50` never uploaded that manifest, so the server had no idea which capabilities your plugin declares.

**Fix**

Upgrade to `anna-app` ≥ `0.1.50` and keep the plugin's `describe` manifest next to `executa.json` as `manifest.json` (or point at it with the `executa.json` `manifest_file` field). `executa publish` / `apps publish` / `apps push` then sync it to the server on every publish — the CLI prints `protocol manifest synced (host capabilities: …)` and warns when the file is missing.

For executas already published without a manifest, any of these heals the row:

- re-publish with CLI ≥ `0.1.50`;
- a successful install / reinstall / upgrade on any Agent (the platform now caches the manifest the Agent gets from `describe`);
- manually pasting the `describe` JSON in **/executa → My Tools → Edit → Manifest**.

Note the capability strings are validated against the platform allow-list at write time — a typo like `host.uploadFile` is now rejected with HTTP 400 instead of silently hiding the Permission entry.

---

## 10 · Sampling — `MAX_TOKENS_EXCEEDED` on a single small call

**Symptom**

A reasonable sampling request fails with `-32007 MAX_TOKENS_EXCEEDED` even though `maxTokens` is well under 8 192.

**Cause**

The cap is **cumulative across the same `invoke_id`**, not per call. Default total is 32 000 tokens.

**Fix**

Send fewer / smaller sampling calls per tool invocation, or ask the user to raise `sampling_grant.maxTokensTotal` in their Anna Admin panel (host caps it at 32 000 in v1).

---

## 11 · Storage — `cur["value"]` looks empty even on a successful read

**Symptom**

Your read-modify-write pattern silently overwrites previous data:

```python
cur = await rpc("storage/get", {"scope": "tool", "key": "log"})
log = cur["value"] if cur["value"] else []   # ← always [] even after writes!
```

**Cause**

Legitimate values include `0`, `""`, `false`, `[]`, `{}` — all falsy. Truthiness is the wrong check. The Agent guarantees an `exists` field on **both** hit and miss responses, exactly to avoid this trap.

**Fix**

Always branch on `exists`:

```python
log = cur["value"] if cur.get("exists") else []
```

See [Persistent Storage — Result shapes](/developers/tools/executa-storage#result-shapes).

---

## 12 · Storage — using the wrong scope or omitting it

**Symptom**

Data written by version 1 of your plugin is invisible to version 2; or two unrelated plugins clobber each other under the same key.

**Cause**

`scope` defaults to `"app"` when omitted. If you actually wanted plugin-private state, it ended up in the broader app namespace; if you wanted user-shared state, it ended up siloed by app.

**Fix**

Always pass `scope` explicitly:

| Want | Pass |
|---|---|
| Plugin-private state | `scope: "tool"` |
| Shared between views of the same Anna App | `scope: "app"` |
| Visible across the user's whole drive | `scope: "user"` on any `files/*` or `storage/*` call |

---

## 13 · Long jobs — `emit_progress` events never show up

**Symptom**

Your tool runs fine under `anna.tools.invokeAsync`, but the app's progress
bar never moves — no `tool_update` events arrive, no error anywhere.

**Cause**

Progress notifications are **silently dropped** whenever the host cannot
(or will not) route them. The three usual reasons:

1. **Missing `invoke_id` correlation.** `executa/progress` is a JSON-RPC
   *notification* — the host matches it to its parent invoke solely via
   `params.context.invoke_id`. If you call the SDK's `emit_progress`
   outside a `bind_invoke(params)` block (Python) or forget to pass
   `invokeId` (Node) / `invokeID` (Go), the event has no owner and is
   dropped. Unknown or already-finished invoke ids are dropped too.
2. **Sync invoke.** Only `tools.invokeAsync` jobs have a progress channel.
   During a plain synchronous `tools.invoke` the notifications are dropped
   — the tool still works, there is just nowhere for progress to go.
3. **Rate limit.** 50 events/second per invoke; excess is dropped without
   feedback. Batch your updates (e.g. one per step, not one per row).

**Fix**

```python
# Python — bind once at the top of the handler:
from executa_sdk import bind_invoke, emit_progress

def handle_invoke(req_id, params):
    with bind_invoke(params):                       # ① correlation
        for i in range(1, total + 1):
            do_step(i)
            emit_progress("tool_update",            # ② whitelisted type
                          {"step": i, "total": total})
```

Also remember:

- Allowed `type` values are `progress` and `tool_update` only — anything
  else (including `completed` / `failed`) is coerced to `progress`;
  terminal states cannot be faked from the plugin.
- Keep `data` small: the host stores at most **8 KB per event** and keeps
  the **latest 500** events per job (older ones fall out of the ring).
- Progress is best-effort by contract. The authoritative job state is
  always `tools.getJob` — never gate your plugin's correctness on an
  event being delivered.

See the official demo `anna-executa-examples/examples/anna-app-long-task-demo`.

---

## See also

- [Lifecycle & Capability Negotiation](/developers/tools/executa-lifecycle)
- [Protocol Specification](/developers/tools/executa-protocol)
- [Sampling](/developers/tools/executa-sampling)
- [Persistent Storage](/developers/tools/executa-storage)
- [Binary Distribution](/developers/tools/executa-binary)
