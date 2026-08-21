---
title: "Local Development"
description: "Run an Anna App locally with `anna-app dev` — in-process dispatcher, stdio executa, no nexus checkout required."
section: apps
slug: local-dev
order: 16
updated: 2026-04-29
estimated_minutes: 5
category: "Local Development & Testing"
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
