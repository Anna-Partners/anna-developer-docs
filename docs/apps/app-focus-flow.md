---
title: "Build Beautiful: the Focus Flow Example"
description: "Clone the anna-app-focus-flow reference project and ship a polished Anna App — Tool plugin, Skill, and SPA bundle — in one sitting."
section: apps
slug: app-focus-flow
order: 3
updated: 2026-05-06
estimated_minutes: 6
---

The [`anna-app-focus-flow`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/anna-app-focus-flow) example in the public [`anna-executa-examples`](https://github.com/whtcjdtc2007/anna-executa-examples) repo is the most complete reference Anna App we ship. It bundles **all three** building blocks an app can declare — a stdio Tool plugin, a Skill, and a polished UI bundle — wired together with the production RPC dispatcher. Treat it as a working blueprint: clone it, rename, and you have a beautiful Anna App.

> [!TIP]
> If you only want the bare CLI flow, start with [Quickstart: anna-app CLI](/developers/apps/app-quickstart). This page is for when you want a finished, opinionated example to learn from or fork.

## What you get out of the box

```
anna-app-focus-flow/
├── app.json                  # Listing metadata (slug, name, category)
├── manifest.json             # AppManifest schema:1 — UI + executas + host_api ACL
├── bundle/
│   ├── index.html            # SPA entry, loads the AnnaAppRuntime SDK
│   ├── app.js                # calls anna.tools.invoke / storage / chat / window
│   ├── style.css             # the "beautiful" part
│   └── icon.svg
├── executas/
│   ├── focus-session-python/ # stdio Tool plugin — Python / uv (default flavour)
│   │   ├── executa.json       #   {tool_id, type:"python", enabled:true}
│   │   ├── focus_session_plugin.py
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── focus-session-node/   # stdio Tool plugin — Node.js 18+ (alternate flavour)
│   │   ├── executa.json       #   {tool_id, type:"node", enabled:false}
│   │   ├── package.json
│   │   └── focus_session_plugin.js
│   ├── focus-session-go/     # stdio Tool plugin — Go 1.21+ (alternate flavour)
│   │   ├── executa.json       #   {tool_id, type:"go", enabled:false}
│   │   ├── go.mod
│   │   └── main.go
│   └── focus-coach/
│       └── SKILL.md          # declarative Skill loaded into the LLM prompt
├── fixtures/                 # recorded RPC sessions for replay-based tests
├── tests/                    # vitest (bundle) + pytest (plugin) suites
└── scripts/
    └── set-tool-id.py        # rewrite the placeholder tool_id across all 4 files
```

A single repo gives you everything an app submission needs:

- **Tool** — `focus-session` exposes one dispatcher method (`session`) with an `action` discriminator (`start`, `pause`, `resume`, `complete`, `get_state`). One Executa row per app, no per-method explosion. The plugin ships in **three language flavours** (Python, Node.js, Go) all conforming to the same JSON-RPC contract; pick one via the `enabled` field in each `executa.json` (default: Python). See [Multi-language executas](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/docs/multi-language-anna-apps.md) for the full discovery rules.
- **Skill** — `focus-coach` is loaded into the assistant's system prompt whenever the app's window is focused, so the LLM knows when and how to call the tool.
- **UI bundle** — a static SPA that talks to the host through the [App UI SDK](/developers/apps/app-ui-sdk), exercising `tools.invoke`, `storage.get/set`, `chat.write_message`, and `window.set_title` against the real ACL.
- **Tests + fixtures** — vitest drives the bundle through `mountBundle`, pytest drives the plugin through `anna-executa-test`, and recorded JSONL fixtures replay through `anna-app fixture verify`.

## 1. Clone and install

```bash
git clone https://github.com/whtcjdtc2007/anna-executa-examples.git
cd anna-executa-examples
pnpm install                 # installs @anna-ai/cli for every example
uv --version                 # uv must be on PATH — used to spawn the Python bridge
anna-app doctor              # checks uv, runtime pin, signing key
```

Then jump into the example:

```bash
cd examples/anna-app-focus-flow
```

> [!NOTE]
> If `which anna-app` finds nothing on your PATH, use `pnpm --filter anna-app-focus-flow <script>` so the workspace-local CLI binary resolves correctly.

## 2. Run it locally

```bash
pnpm dev                     # → anna-app dev
# Harness UI: http://localhost:5180
```

The CLI starts the same harness you saw in the [Quickstart](/developers/apps/app-quickstart): it serves `bundle/` at `/anna-apps/focus-flow/dev/`, supervises the active `executas/focus-session-*/` flavour as a stdio process (Python via `uv run`, Node via `node`, Go via `go run`), and proxies every `anna.*` RPC to the real Python bridge — same dispatcher, same ACL gating, same SSE event shapes as production. Edits under `bundle/` hot-reload the iframe.

The first `tools.invoke` lazy-spawns the executa. If the process exits immediately, look for `tool_failed: executa process exited` in the right-hand RPC log panel; for the Python flavour, `cd executas/focus-session-python && uv sync` will surface the real dependency error.

To try a different language flavour for a single run without editing `executa.json`:

```bash
anna-app dev --executa dir=./executas/focus-session-node
anna-app dev --executa dir=./executas/focus-session-go,type=go
```

The `--executa` flag bypasses `enabled: false` on the directory you single out.

## 3. Mint your own Tool & Skill IDs

The example ships with `*-CHANGEME-*` placeholder IDs so it stays publishable as a template. Before installing on Anna for real, mint server-side IDs and rewrite all four files atomically:

```bash
# After minting at https://anna.partners/executa → My Tools → Mint:
scripts/set-tool-id.py apply --tool tool-yourhandle-focus-session-abcd1234
scripts/set-tool-id.py status   # confirm the three files agree
```

The helper updates (Python flavour only — see the per-flavour READMEs for Node / Go):

1. `executas/focus-session-python/pyproject.toml` (`[project].name` + `[project.scripts]` key)
2. `manifest.json` (`required_executas[].tool_id` + `ui.host_api.tools`)
3. `bundle/app.js` (`TOOL_ID` constant)

The runtime `MANIFEST` in `focus_session_plugin.py` no longer declares a `name` — the host identifies the Executa by its server-assigned `tool_id`, not by a self-reported manifest name.

Run `scripts/set-tool-id.py reset` to restore the placeholders before committing back to a fork.

> [!IMPORTANT]
> Tool IDs are **mint-only** — Anna assigns them server-side as `tool-{handle}-{slug}-{uniq}` and the dispatcher does literal string equality against `required_executas[].tool_id`. You cannot type a custom ID, and any client-supplied `tool_id` is dropped. See [App Manifest](/developers/apps/app-manifest) for the full ACL rules.

## 4. Validate

```bash
pnpm validate                # → anna-app validate --strict
```

This runs the same three layers Nexus applies on submission:

1. **`AppManifest`** Pydantic model (`extra="forbid"`) — shape & types
2. **`validate_ui_section_static`** — CSP, view geometry, and the rule that every `host_api.tools` entry resolves to a declared `required_executas` / `optional_executas` ID
3. **Bundle linter** — entry exists, view names unique, sizes well-formed; `--strict` greps the bundle JS for `anna.<ns>.<method>` usage and asserts each is allow-listed

## 5. Test the contract

```bash
# Bundle (TypeScript / vitest):
pnpm test

# Plugin (Python / pytest via anna-executa-test):
cd executas/focus-session
uv sync --extra dev
uv run pytest ../../tests/plugin -q
```

Both suites use the production dispatcher path. See [Testing the Bundle](/developers/apps/testing-bundle) and [Testing the Plugin](/developers/apps/testing-plugin) for the underlying APIs.

## 6. Replay recorded fixtures

```bash
pnpm fixture:verify          # replays fixtures/*.jsonl through the harness
pnpm fixture:summarize       # human-readable transcript of the happy path
```

Recorded fixtures are how the example pins regressions — see [Recording and Replay](/developers/apps/recording-replay) for the JSONL format and how to capture new ones.

## 7. Submit it

When the example is yours (renamed, re-minted, restyled), follow the standard publish flow:

1. Mint a Skill ID for `focus-coach` and paste the SKILL.md body in the Anna console.
2. Create the App listing (`app.json` → **Listing** tab on the developer console).
3. Create a version, paste your `manifest.json`, upload every file under `bundle/` through the bundle uploader.
4. Submit for review → wait for approval → **Publish** → install from the app's detail page.

Detailed walk-throughs live at [Publishing an App](/developers/apps/app-publish), and the per-tab field reference at [Listing Fields](/developers/apps/app-listing).

## Where to look next

- **Manifest internals** — [App Manifest](/developers/apps/app-manifest)
- **Bundling executas** — [Bundling Executas](/developers/apps/app-bundling)
- **App UI surface** — [Overview](/developers/apps/app-ui-overview), [SDK](/developers/apps/app-ui-sdk), [Host API](/developers/apps/app-ui-host-api)
- **CI replay** — [Recording and Replay](/developers/apps/recording-replay)

> [!NOTE]
> The example tracks the latest stable [`@anna-ai/cli`](https://www.npmjs.com/package/@anna-ai/cli) and the pinned Python runtime declared in the harness bridge. If `anna-app doctor` flags a mismatch, run `pnpm install` at the repo root before `anna-app dev`.
