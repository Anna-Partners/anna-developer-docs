---
title: "Common Pitfalls"
description: "The bugs that show up most often when authors build Executa plugins, and how to spot them fast."
section: tools
slug: executa-pitfalls
order: 14
updated: 2026-11-02
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

## 8 · Sampling — v2 not negotiated

**Symptom**

Your plugin issues `sampling/createMessage` and the host returns `error: { code: -32008, message: "not_negotiated" }`.

**Cause**

The plugin did not complete the v2 handshake: it answered `initialize` with `Method not found`, timed out (5 s), or omitted `capabilities.sampling` from its reply, so the Agent silently downgraded the session to v1 and never forwards reverse RPCs. There is no manifest declaration to add — every installed, enabled Executa receives a `sampling_token` on each invoke.

**Fix**

Reply to `initialize` with `protocolVersion: "2.0"` and the capabilities you use (`sampling`, `storage`, `media`, …). The official SDKs do this for you. See [Lifecycle](/developers/tools/executa-lifecycle#v2-capability-handshake).

---

## 9 · Sampling / Storage — plugin exits before reverse RPC completes

**Symptom**

First reverse RPC call works in dev, but in production the result never arrives — Agent logs *"unmatched response id=…"* and the host times out.

**Cause**

The plugin returned the `invoke` result and immediately did `process.exit()` / `sys.exit()`, killing the stdin reader before the reverse-RPC response could be dispatched.

**Fix**

Same as Pitfall #1 — the plugin process must be long-running. The official SDKs (`sdk/{python,nodejs,go}` in [anna-executa-examples](https://github.com/whtcjdtc2007/anna-executa-examples)) ship a single-reader-with-dispatch pattern that handles both Agent requests **and** host responses to your reverse RPCs. Use it.

---

## 10 · Sampling — `MAX_TOKENS_EXCEEDED` on a single small call

**Symptom**

A reasonable sampling request fails with `-32007 MAX_TOKENS_EXCEEDED` even though `maxTokens` is well under 8 192.

**Cause**

The cap is **cumulative across the same `invoke_id`**, not per call. The total is a platform constant: 32 000 tokens per invoke.

**Fix**

Send fewer / smaller sampling calls per tool invocation. The cap is fixed platform-side (no longer adjustable in the user's Anna Admin panel) — shrink the workload or split it across invokes.

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
| Shared between views of the same Anna App | `scope: "app"` (plugin side: only authorized for invokes dispatched from that App's context — see [Scopes](/developers/tools/executa-storage#scopes)) |
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

## 14 · Media — `audio/transcribe` recording format & inline cap

**Symptom**

`media.transcribe(...)` fails with `VIDEO_INVALID_REQUEST (-32122)` ("format is
required for inline audio"), `AUDIO_TOO_LONG (-32143)`, or — after a few calls
in the same invoke — `AUDIO_INVOKE_BUDGET_EXCEEDED (-32148)`. Or it simply
returns `AUDIO_NOT_GRANTED (-32140)`.

**Cause**

1. **Inline audio needs an explicit `format`** (`wav|mp3|webm|ogg|flac|m4a`).
   The host cannot sniff a base64 blob; the SDKs default to `wav` but will
   send whatever you pass — a stray `"aac"` or `None` is rejected.
2. **Inline is capped at 10 MB decoded** (and `audioUrl` at 25 MB / 600 s).
   16 kHz mono PCM16 wav is 32 KB per second, so ~5 min already hits the
   inline cap.
3. **Per-invoke seconds budget.** Each call reserves its estimated duration
   against `max_audio_seconds` (default 600 per `tool_invoke_id`). Compressed
   formats are estimated conservatively (25 s/MB) before the provider runs,
   then settled to the real duration — a 4 MB mp3 pre-reserves 100 s even if
   it is only 60 s long.
4. **`-32140` means disabled or an old host.** `AUDIO_NOT_GRANTED` is
   returned only when the user disabled the Executa (re-enable it under
   Installed Apps). An old host (pre 2026-10-12) answers
   `method_not_found`, which the SDKs map to `-32140` as well.

**Fix**

```python
# Push-to-talk: record 16 kHz mono PCM16, keep clips short, always pass format.
stt = await media.transcribe(audio_bytes=wav_bytes, format="wav", language="zh")

# Long recordings: upload once (host/uploadFile or your own bucket) and pass the URL
stt = await media.transcribe(audio_url=public_https_url)
```

- Prefer `wav` for short clips: duration is measured exactly from the header,
  so both the 600 s cap and the invoke budget are precise.
- Chunk by sentence/pause instead of sending one long buffer — it also gives
  the user earlier feedback.

See [Media](/developers/tools/executa-media#audiotranscribe).

---

## 15 · Sampling — empty text, `stopReason: "maxTokens"` and 40–50 s latency on a thinking model

**Symptom**

- `sampling/createMessage` with a modest `maxTokens` (say 700) returns
  `content.text: ""` (or a few characters) and `stopReason: "maxTokens"`, even
  though the prompt asked for a two-line summary.
- `usage.outputTokens` is right at the cap and `usage.reasoningTokens` (when
  present) is almost the same number.
- The call took 40–50 s. The second call is just as slow, so it's not a cold
  start.

**Cause**

The user's preferred model is a **thinking model** (Qwen3 / DeepSeek-R1 /
GPT-5.x / Claude extended thinking …) running with reasoning enabled. On
DashScope / Qwen reasoning tokens count **inside `maxTokens`**, so the model
spends the whole budget thinking and the provider truncates before a single
visible token is emitted. You are billed for the reasoning tokens you never
see, and the latency is the model filling its thinking budget — not process
start-up (forum #454).

Since `@anna-ai/app-schema` 0.32.0 the platform runs sampling (and
`llm.complete` / `llm.stream`) with thinking **off by default** whenever the
model can disable it; you only hit this when you opt in with `thinking: true`
/ `{effort}` on a small budget, when the model's reasoning is **mandatory**
(`_meta.thinking.reason: "mandatory"`), or on an older host.

**Fix**

Detect it programmatically and retry without thinking or with a larger cap:

```python
res = await sampling.create_message(messages=msgs, max_tokens=700, thinking=False)
usage = res.get("usage", {})
if res.get("stopReason") == "maxTokens" and usage.get("outputTokens", 0) - usage.get("reasoningTokens", 0) <= 0:
    # reasoning consumed the whole budget — mandatory-reasoning model or old host
    res = await sampling.create_message(messages=msgs, max_tokens=4096, thinking=False)
```

- Leave `thinking` unset (or `False`) for extraction / summarisation / JSON
  tools; opt in with `{"effort": "low"}` only where reasoning helps.
- Check `_meta.thinking.warning` — the host warns when `maxTokens` is below
  the thinking floor. On mandatory-reasoning models raise `maxTokens` or steer
  to another model via `modelPreferences`.
- `usage.reasoningTokens` is omitted (not `0`) when the provider doesn't report
  it — treat "absent" as unknown, not as "no reasoning".

See [Sampling → Thinking models](/developers/tools/executa-sampling#thinking-models-thinking).

---

## 16 · Platform Chrome / Node — bundling what the Agent already has

**Symptom**

- Your Executa package is 300+ MiB because it ships a full Chrome and/or an
  embedded Node runtime.
- `puppeteer` re-downloads Chrome during `npm install` even though you meant
  to use the platform browser.
- Headless rendering works on your machine but crashes on Cloud Agents.
- Your code pins an exact Chrome build (`146.0.7680.153`) and breaks on the
  next platform upgrade.

**Cause**

Every Agent already provides Chrome for Testing and a shared Node 22 LTS via
the discovery contract (`ANNA_CHROME_EXECUTABLE` / `ANNA_NODE_EXECUTABLE`).
Common mistakes:

- using the full `puppeteer` package — its postinstall silently downloads its
  own Chrome (hundreds of MiB into your build);
- forgetting `--no-sandbox --disable-dev-shm-usage` — Cloud Agents run as a
  non-root user without user namespaces and with a tiny `/dev/shm`;
- pinning to an exact Chrome build — the platform follows the Playwright pin
  and only promises major-version stability windows.

**Fix**

- Use `puppeteer-core` + `executablePath: process.env.ANNA_CHROME_EXECUTABLE`,
  and set `"puppeteer": {"skipDownload": true}` in `package.json`.
- Always launch with `args: ["--no-sandbox", "--disable-dev-shm-usage"]` for
  cloud compatibility (harmless on desktop).
- Compare Chrome versions by **major** only, and declare
  `runtime.requires` (e.g. `{"chrome": ">=140 <147"}`) so installs fail
  loudly rather than render wrongly after an upgrade.
- For Node tools, ship a shell-shim entrypoint that `exec`s
  `$ANNA_NODE_EXECUTABLE` instead of embedding Node.

See [Platform runtimes](/developers/tools/executa-platform-runtimes).

---

## See also

- [Lifecycle & Capability Negotiation](/developers/tools/executa-lifecycle)
- [Protocol Specification](/developers/tools/executa-protocol)
- [Sampling](/developers/tools/executa-sampling)
- [Persistent Storage](/developers/tools/executa-storage)
- [Binary Distribution](/developers/tools/executa-binary)
- [Platform runtimes](/developers/tools/executa-platform-runtimes)
