---
title: "Local Development"
description: "Run an Anna App locally with `anna-app dev` — in-process dispatcher, stdio executa, no nexus checkout required."
section: apps
slug: local-dev
order: 16
updated: 2026-11-27
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
Host API method — exactly as an installed App can in production.

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
storage backend   aps (real nexus APS via /api/v1/storage/*)
```

`--storage aps` requires the real LLM bridge — it cannot be combined with
`--no-llm` or `--mock-llm`.

### Same decisions as production

The harness makes the **same access decisions** as the platform — there is
no grant simulation and nothing to toggle. Every Host API method and every
Executa reverse-RPC token (`sampling_token`, `storage_token`, `image_token`,
`media_token`, `upload_token`) is available locally just as it is for an
installed App in production. The only manifest-driven checks, enforced
identically in both places, are the five
[capability declarations](/developers/apps/app-manifest#capability-declarations):

- `credentials.get_token(provider)` for a provider missing from
  `ui.host_api.credentials` → `permission_denied`;
- `storage.*` / `files.*` on a cross-app scope missing from `storage.scopes`
  → `permission_denied` (plugin side: `storage_token.allowed_scopes` only
  carries `tool` plus the scopes the Executa declares);
- `share.*` without `ui.host_api.share: true` → `share_not_declared`, and
  `conversation.*` without `ui.host_api.conversation: true` →
  `conversation_not_declared` (CLI ≥ 0.1.68);
- a sandbox agent session only sees the host-kit tools listed in
  `ui.host_api.agent.tools`.

> [!TIP]
> Exercising real APS locally (`--storage aps`) is still worth it: the
> in-memory backend does not enforce scope `owner` semantics the way
> production APS does.

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

## Executa reverse RPC under `anna-app dev`

A bundled Executa can issue **every reverse RPC the production Agent
accepts** (CLI ≥ 0.1.68 / `anna-app-runtime-local` ≥ 0.2.0a39 — earlier
versions answered `-32601 Method not found` for the methods below,
[forum #598](https://forum.anna.partners/t/anna-app-dev-executas-web-image-search-call-returns-32601-method-not-found/598)).
Sampling, embeddings, agent sessions, storage KV, `files/*`, `web/search`,
`web/fetch`, `image/generate`, `image/edit` and `host/uploadFile` were
already supported. What answers the rest depends on how the harness was
started:

| Reverse RPC | Signed out or `--no-llm` | `--mock-llm` | Signed in |
| --- | --- | --- | --- |
| `web/image_search`, `web/image_fetch` | Local implementation (ddgs / native download, unbilled) | Same | Same by default; `--web real` uses the platform provider chain and APS artifacts |
| `image/generate_async`, `image/edit_async`, `image/get_job`, `image/cancel_job`, `image/resign`, `video/*`, `music/*`, `audio/speak`, `audio/transcribe` | `llm_disabled` | The matching fixture line, else `not_implemented` | The real platform service |
| `storage/quota_status` | `not_implemented` | `not_implemented` | The user's real quota with `--storage aps`; otherwise `not_implemented` |
| `credentials/listAccounts`, `credentials/getToken` | `llm_disabled` | The matching fixture line, else `not_implemented` | Real accounts and a short-lived token; `APP_NOT_GRANTED` when the provider is not declared or not authorized |

`--mock-llm` never fabricates a success for these methods: without a
`{"ns": "<ns>", "method": "<method>", "result": {…}}` fixture line the
plugin receives `not_implemented`.

**Credentials.** The harness asks the plugin for its manifest (`describe`)
and sends the declared `credentials[].name` list to the platform, which maps
it to OAuth providers exactly as it does for an installed Executa. A
provider your plugin does not declare answers `APP_NOT_GRANTED`, so a
missing declaration fails locally instead of after publishing. Restart
`anna-app dev` after changing the declaration. The page-side
`anna.credentials.*` Host API is not served by the local harness.

**Fake-IP DNS proxies.** `web.fetch` / `web.image_fetch` refuse a hostname
that does not resolve to a public address. If a proxy on your machine runs in
fake-IP mode (Clash / Surge / sing-box TUN — every name resolves to
`198.18.x.x`), the harness detects it, says so in the boot banner, and
verifies fetch targets over DNS-over-HTTPS instead; a name that really points
at a private address is still refused. `ANNA_APP_RUNTIME_WEB_DOH_URL` selects
another DoH JSON endpoint (default `https://dns.alidns.com/resolve`); the
hostname being fetched is sent to that resolver. CLI versions before 0.1.68
answer `SSRF_BLOCKED … resolves to private IP 198.18.x.x` for every URL.

### Differences from production that remain

| | Production | `anna-app dev` | What to do |
| --- | --- | --- | --- |
| JSON-RPC error codes | Per-family codes (web `-3252x`, credentials `-3206x`, …) | Three codes: `-32004` (not implemented), `-32602` (invalid params), `-32603` (everything else) | Branch on `error.data.errorCode` when debugging locally |
| `web/image_fetch` → `get_url` | Short-lived https reference the platform can read | Under the default `--web local`: `http://localhost:<port>/_dev/web-images/…` — the harness keeps the image for the run and serves it back. Reachable from your machine only; no expiry, gone when the harness stops (CLI < 0.1.68 returned an inline `data:` URL) | Render it or read it from the page / plugin as usual. To hand it to a platform call (LLM vision, `image.edit`) use `--web real`, or read the bytes and pass them inline |
| `web/image_fetch` → `path` | A real APS files object, usable with `files.*` | A placeholder under `--web local` — nothing is stored in APS | Use `--web real` for flows that depend on `path` |
| `web/image_fetch` artifact owner | The Executa's `tool` scope | The dev App's `app` scope under `--web real` | Use `get_url`; do not assume `path` across environments |
| Billing and ownership | Recorded against the Executa | Recorded against the dev App | Nothing |
| Token expiry and renewal | Enforced | Not simulated | Verify long-running tools on the real platform before release |
| `anna-app executa dev` | — | Web, media, embeddings and credentials reverse RPCs are not supported | Test them with `anna-app dev` and a bundled Executa |

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

- `chat.append_artifact` / `chat.write_message` are deprecated no-ops (see
  [App UI Host API](/developers/apps/app-ui-host-api)). For conversations,
  `conversation.*` is forwarded to the real platform when you are logged in
  (and replayed from fixtures with `--mock-llm`) — see
  [Durable conversations](/developers/apps/app-ui-conversation#local-development).
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
