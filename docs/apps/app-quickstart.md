---
title: "Quickstart: anna-app CLI"
description: "From an empty directory to a running Anna App harness in under a minute — scaffold, dev, validate."
section: apps
slug: app-quickstart
order: 2
updated: 2026-04-29
estimated_minutes: 4
---

This is the fastest path from "nothing" to a working Anna App on your laptop. Concepts come right after — see [App Manifest](/developers/apps/app-manifest), [Bundling](/developers/apps/app-bundling), and the rest of this section once you have something running.

> [!TIP]
> No platform source checkout is required. The CLI fetches the pinned Python runtime through `uvx` on first run and caches it.

## Prerequisites

- **Node 22+** — `node --version`
- **uv** (Astral) — one-time install:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **`anna-app` CLI** — global install:
  ```bash
  npm i -g @anna-ai/cli
  anna-app --help
  ```

Run `anna-app doctor` once to confirm `uv`, the `uvx` cache, and your dev signing key are in shape.

## 1. Scaffold

```bash
anna-app init my-focus-flow --slug focus-flow
cd my-focus-flow
```

The `minimal` template lays down a complete, valid project:

```
my-focus-flow/
├── manifest.json                      # schema 2 — UI + executa + dev block
├── app.json                           # store-listing metadata (name, tagline, category)
├── bundle/
│   ├── index.html                     # iframe entry; pulls the AnnaAppRuntime SDK
│   └── app.js                         # connects to the host, calls tools.invoke / storage
├── executas/
│   └── focus-flow/                    # local stdio executa (Python; auto-detected)
│       ├── focus_flow_plugin.py       # describe / health / invoke loop
│       └── pyproject.toml
└── README.md
```

The scaffold's `tool_id` is `tool-dev-focus-flow` — a synthetic dev id that lets you reference your local executa from the manifest before anything is published to the catalogue.

## 2. Run the harness

```bash
anna-app dev
```

The CLI prints `✓ dashboard http://localhost:5180/`. Open it. A mock-dashboard shell loads, and your bundle is mounted inside an iframe at `/anna-apps/<slug>/dev/index.html?wid=<window-uuid>&t=<dev-token>`. The harness runs the **same** dispatcher that ships in production, with an in-memory `WindowStore` (no Postgres, no NATS, no Executa Agent in the loop).

What's happening underneath:

- The CLI auto-discovers each `executas/<name>/` subdirectory and supervises it as a stdio process. Detection is language-agnostic: `executa.json` (explicit) > `pyproject.toml` (Python via `uv run`) > `package.json` (Node) > `go.mod` + `executa.json` (Go) > `bin/<name>` (pre-built binary). See [Multi-language executas](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/docs/multi-language-anna-apps.md).
- A static-file server serves your `bundle/` at `/anna-apps/<slug>/dev/`.
- An SSE relay forwards server-pushed events (`auth.refresh`, `app/method`, `entry_payload`) into the iframe.
- The bundle's `tools.invoke`, `storage.set`, `storage.get`, `window.set_title`, `window.ready` calls land in the production RPC dispatcher and are ACL-checked against `manifest.ui.host_api`.

Hot reload is on by default — edit `bundle/app.js`, save, watch the iframe refresh.

## 3. Validate before publish

```bash
anna-app validate           # JSON Schema + ui static + tool_id linter
anna-app validate --strict  # also greps the bundle for host_api ACL coverage
```

The validator is fail-fast and layered:

1. JSON Schema (`@anna-ai/app-schema`) — same definition the server uses on `POST /api/v1/developer/apps/{id}/versions`.
2. UI static checks — bundle entry exists, view names unique, sizes well-formed.
3. Cross-file `tool_id` linter — every `host_api.tools[]` entry resolves to a `required_executas[]` entry, with Levenshtein-1 typo suggestions.
4. `--strict` — greps your bundle JS/TS for `anna.<ns>.<method>` usage and verifies each is allowlisted in `manifest.ui.host_api`.

If everything is green, you have a publishable artifact.

## 4. Drive it from a test

For CI, mount the bundle programmatically (no browser, no SSE):

```ts
import { mountBundle } from "@anna-ai/cli/test";

const h = await mountBundle({
  manifest: "./manifest.json",
  bundle:   "./bundle",
});

await h.call("storage", "set", { key: "ping", value: 1 });
const events = h.drainEvents();
await h.close();
```

For executa-side coverage, use the `anna-executa-test` pytest plugin (`executa_session` / `executa_invoke` fixtures). Both paths share the same dispatcher as `anna-app dev` and production.

## 5. Where to next

- **Manifest reference** — [App Manifest](/developers/apps/app-manifest) (every field, every validator)
- **Bundling components** — [Bundling](/developers/apps/app-bundling)
- **Listing assets** — [Listing](/developers/apps/app-listing)
- **App UI runtime** — [Overview](/developers/apps/app-ui-overview), [SDK](/developers/apps/app-ui-sdk), [Host API](/developers/apps/app-ui-host-api)
- **Local dev deep-dive** — [Local Development](/developers/apps/local-dev)
- **Recording & replay for CI** — [Recording / Replay](/developers/apps/recording-replay)
- **Submit for review** — [Publishing](/developers/apps/app-publish)

> [!NOTE]
> The CLI ships as [`@anna-ai/cli`](https://www.npmjs.com/package/@anna-ai/cli) on npm. Source, docs, and the rest of the developer hub live at [anna.partners](https://anna.partners). The pinned Python runtime version is exposed as `PINNED_RUNTIME_VERSION` in the harness bridge.
