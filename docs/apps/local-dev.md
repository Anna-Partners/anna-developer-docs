---
title: "Local Development"
description: "Run an Anna App locally with `anna-app dev` — in-process dispatcher, stdio executa, no nexus checkout required."
section: apps
slug: local-dev
order: 16
updated: 2026-09-24
estimated_minutes: 5
category: "Local Development & Testing"
verified_cli: "0.1.54"
---

# Local Development with `anna-app dev`

`anna-app dev` boots a fully self-contained Anna App harness on your laptop:

- the **same** RPC dispatcher that ships in production (`anna-app-core`),
- an in-memory `WindowStore` (no Postgres, no NATS, no Executa Agent),
- a static-file server that loads your bundle in an iframe,
- an SSE relay so server-pushed events (`auth.refresh`, `app/method`,
  `entry_payload` updates) reach the iframe just like in production,
- a process supervisor for `executas/<name>/` that forwards `tools.invoke`
  RPCs over stdio to your plugin. Detection is language-agnostic
  (`executa.json` / `pyproject.toml` / `package.json` / `go.mod` /
  `bin/<name>`); see [Multi-language executas](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/docs/multi-language-anna-apps.md).

End users do **not** need a platform source checkout — the harness pulls
`anna-app-runtime-local` via `uvx` on demand (see [Runtime modes](#runtime-modes)).

## Prerequisites

- Node 22+
- `uv` (Astral) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- An app project created by `anna-app init <dir> --slug <slug>`

Run `anna-app doctor` to verify your environment before the first `dev`
session — it checks `uv`, the uvx cache, and (if you're contributing to
nexus) the in-tree runtime path.

## Quickstart

```bash
anna-app init my-focus-flow --slug focus-flow
cd my-focus-flow
anna-app dev
```

Open the URL it prints (`http://127.0.0.1:5180/dev/<wid>?t=<dev-token>` by
default). The bundle loads inside the harness iframe and can call every
host_api the manifest grants.

## CLI flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--manifest <path>` | `manifest.json` | Manifest path (relative to `--cwd`). |
| `--bundle <dir>` | `./bundle` | Static-file root served at `/anna-apps/<slug>/dev/`. |
| `--slug <slug>` | from manifest `slug` (falls back to `name`) | Slug used in URLs and SSE topics. |
| `--view <name>` | manifest default | Open a non-default view at boot. |
| `--port <n>` | `5180` | HTTP port for the dev server. |
| `--user-id <id>` | `1` | Harness user_id (also overridable via `manifest.dev.user_id`). |
| `--no-watch` | (watcher on) | Disable bundle file watcher (LiveReload). |
| `--storage <mode>` | `legacy` | APS backend: `legacy` = in-memory `runtime_state` (offline); `aps` = **real** Nexus APS via `/api/v1/storage/*` — see [Storage backends](#storage-backends). |
| `--matrix-nexus-root <path>` | (auto) | Use an in-tree nexus checkout instead of `uvx`. |
| `--executa <spec>` *(repeatable)* | (auto-discovery) | Register an executa explicitly; spec is comma-separated `key=value` (`dir=<path>[,tool_id=<id>][,type=python\|node\|go\|binary][,command="<argv>"]`). When given, replaces auto-discovery for the run and bypasses `enabled: false` on the chosen dir. |

## Runtime modes

`anna-app dev` picks one of two modes automatically:

- **uvx (default for end users)** — runs
  `uvx anna-app-runtime-local@<PIN> anna-app-bridge`. The pin lives in
  [`anna-app-cli/src/harness/bridge.ts`](https://anna.partners/developers/apps/app-quickstart)
  (constant `PINNED_RUNTIME_VERSION`). The wheel is fetched once and
  cached under your platform's uv cache dir (see `uv tool dir`).
- **nexus-source (auto for platform contributors)** — runs
  `python -m anna_app_runtime_local.bridge` against the in-tree
  `packages/anna-app-runtime-local/` so contributor edits take effect
  without a publish round-trip. Triggered when:
  - `--matrix-nexus-root <path>` is passed, **or**
  - `$ANNA_NEXUS_ROOT` is set, **or**
  - the CLI auto-detects you're inside a nexus checkout.

The two modes are byte-equivalent at runtime — the dispatcher code is
the same wheel either way.

## Storage backends

By default `anna-app dev` keeps all APS storage **in memory** for offline
parity (`legacy` mode, seeded from `manifest.dev.seed_storage`). To exercise
real APS — the same wire path as production — run:

```bash
anna-app dev --storage aps
```

while logged in (`anna-app login`). The boot banner confirms the mode:

```text
storage backend   aps (real nexus APS via /api/v1/storage/*) · caps gate strict (production parity)
```

`--storage aps` requires the real LLM bridge — it cannot be combined with
`--no-llm` or `--mock-llm`.

### Storage capability gate (production parity)

In `aps` mode the harness enforces the same capability gate as the platform
minter: if your manifest declares **no** `aps.*` entry in
`host_capabilities` (and no schema-3 `storage` entry), any `storage/*` /
`files/*` call for a non-self scope fails locally with the exact production
error plus a fix hint:

```text
-32021: storage_token missing — host did not authorize storage for this invoke
hint: declare "aps.kv" (KV) / "aps.files" (Files) in host_capabilities; the
platform will not mint a plugin storage_token without them (docs: executa-storage)
```

Pass `--no-strict-caps` to downgrade the gate to a one-shot warning while you
iterate on the manifest — but note the warning is honest: the same call **will**
fail in production until the declaration lands.

> [!TIP]
> Exercising real APS locally is the difference between finding a scope or
> capability bug in an afternoon and finding it in Marketplace review — the
> in-memory backend does not enforce `storage_token` scopes the way
> production does (missing `host_capabilities` declarations are now caught
> by the strict caps gate above even in local runs).

## Size limits (production parity)

Requires CLI ≥ **0.1.54** (`anna-app-runtime-local` ≥ 0.2.0a24). The harness
enforces the platform's transport contracts locally so size bugs surface on
your laptop instead of in production:

| Boundary | Limit | Local behavior |
| --- | --- | --- |
| Sync `tools.invoke` result (payload + envelopes) | **~4 MiB** — same as production's NATS `max_payload` | Rejects with `result_too_large`, `details: {size, max, retriable: false}` — identical wire error to production |
| `tools.invokeAsync` result / args | **256 KB** / **64 KB** | Job fails with `result_too_large` / call rejects with `invalid_arg` |
| Any single stdio JSON-RPC frame (either direction) | **16 MiB** — same as the production Agent's readline ceiling; sized for inline `host/uploadFile` reverse-RPC frames | Structured `frame_too_large` error (`data: {frame_bytes, max_frame_bytes}`); the bridge and the plugin process keep serving subsequent calls |

Everything under these caps passes through **verbatim** — no per-string-field
truncation (see [Result size and integrity](/developers/apps/app-ui-host-api#result-size-and-integrity)).
Content above them must travel by reference: `host/uploadFile` or APS
`files/*`.

> [!WARNING]
> Harness versions before 0.1.54 crashed on frames over **64 KiB**: an
> oversized request killed the Python bridge (`python bridge exited (code=1)`,
> then `python bridge not running` for every later call), and an oversized
> plugin response was misreported as `tool_failed / executa process exited`
> while leaking the still-running plugin process (forum #338). If you see
> those errors, upgrade the CLI.

## `executas/` discovery requirements

- An explicit `executa.json` **requires both** `tool_id` and `type`
  (`python | node | go | binary`). Missing either one skips the executa with
  only a startup warning
  (`⚠ skipping executa <name>: executa.json missing required \`tool_id\``)
  — the plugin is silently not spawned, and every `tools.invoke` then fails
  with `not_implemented: tools.invoke is not available in this runtime`.
- `app.json`'s `bundled_executas` is an **object keyed by handle**, not an
  array:

  ```json
  {
    "bundled_executas": {
      "error-journal": { "path": "executas/error-journal" }
    }
  }
  ```

  Passing an array instead produces
  `⚠ bundled handle "0" → executas/error-journal: no executa discovered at that path`
  — the `"0"` is the array index being read as a handle name.

## `manifest.dev` block

The optional `dev` block lets you customise the harness without polluting
the production manifest. The production dispatcher ignores it; `anna-app
publish` strips it before upload.

```jsonc
{
  "dev": {
    "fixtures": ["fixtures/*.jsonl"],   // recordings to replay
    "seed_storage": { "theme": "dark" }, // initial runtime_state
    "user_id": 1,                       // override --user-id default
    "mocks": {                          // static responses, keyed "ns.method"
      "tools.invoke": { "success": true, "data": {} }
    }
  }
}
```

Field reference lives in
`anna_app_core.manifest.AppDevConfig` in the published [`anna-app-core`](https://pypi.org/project/anna-app-core/) package.

## Live-reload

The watcher reloads the iframe whenever a file under `--bundle` changes.
Disable with `--no-watch` if your editor's autosave is too chatty.

## What's not in `dev`

- No `chat.read_history` / `chat.write_message` persistence — Phase 3 will
  proxy these through real conversation storage.
- `anna.llm.*` / `anna.agent.*` bridge to a real nexus by default (you must
  be logged in via `anna-app login`). Develop offline with `--no-llm` (calls
  return `llm_disabled`) or `--mock-llm <fixture>` (canned responses from a
  JSONL fixture).
- No real Executa NATS — `tools.invoke` calls go to the local stdio
  process spawned from `executas/<name>/`. To exercise the production
  NATS path, deploy to a staging nexus and use `anna-app dev --remote`
  (Phase 9).

## Related

- [Testing the bundle](/developers/apps/testing-bundle)
- [Testing the plugin](/developers/apps/testing-plugin)
- [Recording & replaying sessions](/developers/apps/recording-replay)
