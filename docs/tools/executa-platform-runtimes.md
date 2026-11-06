---
title: "Platform runtimes — shared Node.js & Chrome"
description: "Use the Agent's preinstalled Chrome for Testing and the shared Node.js runtime instead of bundling your own: the discovery contract, version policy, runtime.requires prechecks and lightweight entrypoints."
section: tools
slug: executa-platform-runtimes
order: 13
updated: 2026-11-03
estimated_minutes: 8
---

Shipping a full Chrome (~370 MiB unpacked) and a Node-embedding binary
(~120 MiB) inside every Executa is wasteful — every Anna Agent already has
both. This page is the **contract** for using them (forum #490):

- **Chrome for Testing** — preinstalled on every Agent (cloud Linux,
  desktop macOS, desktop Windows) as part of the platform's Playwright
  runtime. Zero extra download.
- **Shared Node.js** — a pinned Node 22 LTS provided by the platform:
  baked into the Cloud Agent image, lazily installed on desktop Agents the
  first time an Executa that requires it is installed.

A real-world PPT engine dropped from **316 MiB → ~116 MiB** compressed
(850 MiB → ~361 MiB unpacked) by switching to the platform runtimes. Try the
official demo app
[`anna-app-platform-runtime-demo`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/anna-app-platform-runtime-demo)
to probe what your Agent provides.

## Discovery contract (environment variables)

The Agent injects these into every Executa subprocess. The contract is
**presence-based**: a variable is only set when the runtime is actually
ready to run — a missing variable means "not available here", never an
empty string.

| Variable | Meaning | Example (cloud) | Example (macOS) |
|---|---|---|---|
| `ANNA_RUNTIME_PROFILE` | runtime flavour | `cloud-linux` | `desktop-macos` |
| `ANNA_AGENT_VERSION` | Matrix Agent version | `2.31.0` | same |
| `ANNA_CHROME_EXECUTABLE` | absolute Chrome path (resolved by the Agent — never guess directory names) | `/ms-playwright/chromium-1200/chrome-linux/chrome` | `~/Library/Caches/ms-playwright/chromium-1200/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing` |
| `ANNA_CHROME_VERSION` | four-part version | `145.0.7632.12` | same |
| `ANNA_CHROME_PROVIDER` | always `playwright-cft` | | |
| `ANNA_NODE_EXECUTABLE` | absolute Node path | `/opt/anna/node/bin/node` | `~/.anna/runtimes/node-22/bin/node` |
| `ANNA_NODE_VERSION` | full Node version | `22.14.0` | same |
| `ANNA_RUNTIMES_JSON` | compact JSON of all of the above | `{"profile":…,"chrome":{…},"node":{…}}` | |

Semantics:

- Paths are readable + executable by your process. **Never write into those
  directories** — they are shared platform state.
- `PLAYWRIGHT_BROWSERS_PATH` may also be visible; it is an internal
  implementation detail, **not** part of the contract, and may change.
- The contract is identical across all three channels. An Executa written
  against it runs on cloud **and** desktop Agents.

## Declaring requirements — `runtime.requires`

Add a `runtime` block to your `executa.json` so a missing runtime fails at
**install time** with a structured error, instead of crashing at invoke time:

```jsonc
{
  "slug": "ppt-engine",
  "executa_type": "tool",
  "runtime": {
    "requires": {
      "node":   ">=22 <23",   // semver range; omit = no requirement
      "chrome": ">=140"       // chrome compares the MAJOR version only
    },
    "fallback": "fail"        // "fail" (default) | "bundled"
  }
}
```

- Supported range syntax: `>` `>=` `<` `<=` `=` `^` `~`, space for AND,
  `||` for OR. Anything else is rejected at publish time.
- `fallback: "bundled"` means your package ships its own runtime and can
  still run when the platform one is missing — the precheck then only warns.
- On an unmet requirement the install fails with
  `reason_code: "runtime_missing"` and a `missing_runtimes` map such as
  `{"node": "required >=22 <23, found none"}`.
- The precheck is a **pure check** — a declaration never installs anything.
  Runtime provisioning is agent-level: Cloud Agents have the shared Node
  baked into the image; on desktop Agents the user installs it once from the
  agent console ("Platform" row → install, a ~30 MiB download) and then
  retries the app install.
- Older Agents that predate the contract simply ignore the block
  (no precheck, no crash) — fully backwards compatible.

## Lightweight entrypoints

Your `binary` artifact no longer needs to embed Node. Ship your built JS
plus a tiny shell shim:

**`bin/ppt-engine` (Linux / macOS):**

```sh
#!/bin/sh
set -eu
: "${ANNA_NODE_EXECUTABLE:?This Executa requires the Anna platform Node.js runtime. Declare runtime.requires.node in executa.json and install on an up-to-date Agent.}"
exec "$ANNA_NODE_EXECUTABLE" --enable-source-maps "$EXECUTA_HOME/dist/main.js" "$@"
```

**`bin/ppt-engine.cmd` (Windows):**

```bat
@echo off
if "%ANNA_NODE_EXECUTABLE%"=="" (echo ANNA_NODE_EXECUTABLE missing 1>&2 & exit /b 2)
"%ANNA_NODE_EXECUTABLE%" "%EXECUTA_HOME%\dist\main.js" %*
```

Entrypoints may be any executable file — shell / `.cmd` shims are fully
supported by the [multi-file binary pipeline](/developers/tools/executa-binary).

## Using the platform Chrome (Puppeteer)

```js
const puppeteer = require("puppeteer-core");   // NOT "puppeteer" — it downloads its own Chrome
const browser = await puppeteer.launch({
  executablePath: process.env.ANNA_CHROME_EXECUTABLE,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"], // required on Cloud Agents
});
```

- Set `"puppeteer": { "skipDownload": true }` in `package.json` (or
  `PUPPETEER_SKIP_DOWNLOAD=1` in CI) so your build never pulls a Chrome.
- Log `ANNA_CHROME_VERSION` to **stderr** at startup for debuggability —
  stdout is the protocol channel.
- Keep concurrent Chrome instances ≤ 3–4 on Cloud Agents (limited microVM
  memory).

## Version policy

- **Chrome** follows the platform's Playwright pin and upgrades with Matrix
  releases. Major bumps are announced **≥ 2 weeks** ahead (release notes,
  forum Announcements, and the *Upcoming* section below). A given Chrome
  major stays available across **≥ 2 Matrix minor releases** so you have a
  regression window. Write your code against `puppeteer-core` +
  `executablePath` and compare **majors only** — never pin to an exact
  build like `146.0.7680.153`.
- **Node.js** is pinned to the 22 LTS line on every channel. A major switch
  goes through a separate design review and is announced in advance.
- No rollbacks: if your app hard-depends on a specific version, bundle your
  own runtime (the contract is opt-in; `fallback: "bundled"` keeps the
  precheck advisory).

## Version matrix

Planning-time truth — what each Agent release channel currently provides.
Run-time truth is always your own process env
(`ANNA_CHROME_VERSION` / `ANNA_NODE_VERSION`): desktop users may lag
several Matrix versions behind.

<!-- generated:version-matrix:start -->
> Generated from `GET /api/v1/platform/runtimes` by
> `matrix-nexus/scripts/export_platform_runtimes.py` on 2026-11-06.
> Do not edit this block by hand — re-run the exporter.

| Channel | Agent version | Chrome (CfT) | Node.js |
|---|---|---|---|
| Cloud (linux-x86_64) | — | — | — |
| Desktop macOS | — | — | — |
| Desktop Windows | — | — | — |
<!-- generated:version-matrix:end -->

Programmatic access: `GET /api/v1/platform/runtimes` (public, no auth,
cacheable) returns the same matrix plus the policy strings.
`anna-app doctor` prints it too.

## Upcoming changes

<!-- generated:upcoming:start -->
_No runtime changes are currently announced._
<!-- generated:upcoming:end -->

## FAQ

**Why can't the platform match my Puppeteer pin exactly (e.g. `146.0.7680.153`)?**
The platform Chrome follows the Playwright release cadence, not any
individual app's Puppeteer pin. Chrome for Testing builds of the same major
are render-compatible for practical purposes; regression-test against the
announced major and use `runtime.requires.chrome` (e.g. `>=140 <147`) to
make the install fail loudly instead of regressing silently.

**Where do I check which versions the platform provides?**
Four places, one truth source: ① the Version matrix above (generated from
the public API), ② `GET /api/v1/platform/runtimes`, ③ `anna-app doctor`,
④ at run time, `ANNA_CHROME_VERSION` / `ANNA_NODE_VERSION` in your process
env.

**What if my user's Agent is too old for the contract?**
The env variables are simply absent. Degrade gracefully (the demo app shows
a `legacy-scan` fallback that scans `PLAYWRIGHT_BROWSERS_PATH`) or declare
`runtime.requires` so the install is rejected with a clear message instead.

**Can I rely on `PLAYWRIGHT_BROWSERS_PATH`?**
No — it is an implementation detail and its directory layout belongs to
Playwright. Use `ANNA_CHROME_EXECUTABLE`, which the Agent resolves for you.

## See also

- [Binary distribution](/developers/tools/executa-binary) — multi-file
  archives, entrypoints, the env table
- [Node.js quickstart](/developers/tools/executa-nodejs) — §3 covers the
  platform-Node lightweight packaging path
- [Common pitfalls](/developers/tools/executa-pitfalls) — Puppeteer
  full-package download, `--no-sandbox`, build-number pinning
- Demo app: `anna-executa-examples/examples/anna-app-platform-runtime-demo`
