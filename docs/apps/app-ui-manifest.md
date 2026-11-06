---
title: "App UI Manifest"
description: "The `ui` section of a schema ≥ 2 manifest: bundle, views, the credentials / agent.tools declarations, browser_permissions, csp_overrides."
section: apps
slug: app-ui-manifest
order: 10
updated: 2026-11-02
estimated_minutes: 6
category: "App UI"
---

When `schema` ≥ 2 (current: 4), an Anna App manifest gains a `ui` section that describes the static bundle, the named views the LLM can summon, the two `host_api` [capability declarations](/developers/apps/app-manifest#capability-declarations) that involve a second principal (`credentials`, `agent.tools`), the browser features (Permissions Policy) the iframe needs, and any per-bundle CSP overrides. Everything else from [App Manifest](/developers/apps/app-manifest) still applies. The Host API itself needs no declaration — every method is available to an installed App.

## Example

```jsonc
{
  "schema": 4,
  "required_executas": [
    { "tool_id": "tool-yourhandle-browser-abcd1234" }
  ],
  "system_prompt_addendum":
    "When the user asks to research, summon the workspace via open_app_view('research-suite'). Stream updates with update_app_view as findings arrive.",
  "ui": {
    "bundle": {
      "format": "static-spa",
      "entry": "index.html",
      "external_origins": ["https://api.example.com"]
    },
    "views": [
      {
        "name": "main",
        "title": "Research Workspace",
        "default": true,
        "min_size":  { "w": 480, "h": 360 },
        "default_size": { "w": 960, "h": 640 },
        "max_size":  { "w": 1920, "h": 1200 },
        "single_instance": true,
        "summary_template": "Research session: {topic}"
      },
      {
        "name": "chart_preview",
        "title": "Chart Preview",
        "entry": "index.html#/chart",
        "default_size": { "w": 640, "h": 480 }
      }
    ],
    "host_api": {
      "credentials": ["google"],
      "agent": { "tools": ["fs_read_file"] }
    },
    "browser_permissions": ["microphone"],
    "csp_overrides": {
      "connect-src": ["https://api.example.com"],
      "img-src":     ["https://images.example.com"]
    }
  }
}
```

## Field reference

`ui` is parsed by `UiManifestSection` (Pydantic, `extra="forbid"`).

| Field | Type | Required | Constraints |
|---|---|---|---|
| `bundle` | object | yes | See [`bundle`](#bundle) |
| `views` | array | yes | 1–16 entries; at most one `default: true`. See [`views[]`](#views) |
| `form_factors` | array of string | no | Containers the app supports: `"desktop"` / `"mobile"`. Defaults to `["desktop"]` — declare `"mobile"` to appear in the Anna mobile launcher. See [Mobile Support](/developers/apps/app-mobile) |
| `host_api` | object | no | Capability declarations: `credentials` (third-party account providers) and `agent.tools` (local-device tools). See [`host_api`](#host_api). Defaults to empty — most Apps omit it |
| `browser_permissions` | array of string | no | Browser features (Permissions Policy) delegated to the iframe: `microphone`, `camera`, `geolocation`, `display-capture`, `clipboard-read`, `fullscreen`, `autoplay`, `picture-in-picture`, `screen-wake-lock`, `web-share`. Unique entries; anything else is rejected. Defaults to `[]`. See [App UI Browser Permissions](/developers/apps/app-ui-browser-permissions) |
| `csp_overrides` | object | no | Map of CSP directive → list of values. Only the directives below are accepted; `style-src` accepts only `'self'`, `'sha256-...'`, `'nonce-...'`; `script-src` additionally accepts `'wasm-unsafe-eval'` (see [WebAssembly](#webassembly)); `frame-src` accepts only explicit `https://` origins (see [Embedding third-party content](#embedding-third-party-content-frame-src)) |
| `state_merge` | string | no | Reserved. Default `"last_writer_wins"` |

### `bundle`

```jsonc
{
  "format": "static-spa",
  "entry": "index.html",
  "external_origins": ["https://api.example.com"]
}
```

| Field | Type | Constraints |
|---|---|---|
| `format` | string | Currently only `"static-spa"` is accepted (validated server-side) |
| `entry` | string | Path to the entry HTML, relative to the bundle root. Must be present in the uploaded `file_map` at `bundle/finalize`. The path part (before `?`/`#`) must match `^[A-Za-z0-9_./\-]+$` and contain no `..`, `\`, or `//` |
| `external_origins` | array of string | Each must start with `https://` and must not contain `*`. Origins listed here are auto-added to `connect-src` and `img-src` of the bundle's CSP |

### `views[]`

A view is a named UI surface inside your bundle. The LLM passes `view: "<name>"` to `open_app_view`; if `view` is omitted the `default: true` view is used.

```jsonc
{
  "name": "main",                 // [a-z0-9_-]{1,40}
  "title": "Research Workspace",  // 1..120 chars
  "default": true,
  "entry": "index.html#/route",   // optional; otherwise bundle.entry
  "mobile_entry": "mobile.html",  // optional mobile-specific entry; defaults to entry
  "min_size":     { "w": 480, "h": 360 },
  "default_size": { "w": 960, "h": 640 },
  "max_size":     { "w": 1920, "h": 1200 },
  "resizable":       true,
  "movable":         true,
  "single_instance": true,        // dedup per (user, conversation, app, view)
  "summary_template": "Research session: {topic}",
  "icon": "icons/research.svg"
}
```

Sizes are integers in CSS pixels, `120 ≤ w,h ≤ 4096`. The validator rejects `default_size` outside `[min_size, max_size]`.

#### Size baseline (small screens)

The dashboard Window Manager adapts windows to the current viewport, so your declared sizes are **requests, not guarantees**. The most common low-resolution effective viewport is about **1092×614** CSS px (1366×768 at 125 % display scaling). Rules to follow:

- **`min_size.h` must be ≤ 600.** Window height is rigidly clamped to the viewport height; a `min_size.h` above it is force-shrunk by the host (your window gets *less* than its declared minimum on low-resolution displays). Make the view scroll vertically instead of demanding a tall minimum.
- **`min_size.w` should be ≤ 1024.** Width is honoured even when it exceeds the viewport, but the user then has to drag/edge-resize to see the full window — it cannot be shown whole on a single small screen.
- **`default_size` is a preference, not a guarantee.** Anything above **1440×900** is constrained to the viewport (and centred) on smaller displays.
- **Your UI must be responsive across the whole `min_size` ~ `max_size` range** — the user, the host, and agent window tools can all resize it anywhere in that interval.

The publish validator emits non-blocking lint warnings when these baselines are exceeded.

`mobile_entry` is served instead of `entry` when the window is opened from a mobile container — see [Mobile Support](/developers/apps/app-mobile). A single responsive entry is recommended.

`single_instance: true` means: opening the same `view` again under the same `(user, conversation_session_uuid, app_id)` re-focuses the existing window and merges the new payload into `entry_payload` rather than spawning a second window.

### `host_api`

`host_api` is **not** an allow-list of methods. Every Host API namespace — `window.*`, `storage.*`, `files.*`, `llm.*`, `agent.session.*`, `image.*`, `video.*`, `music.*`, `audio.*`, `web.*`, `upload.*`, `chat.*`, `artifact.*`, `apps.*`, `mobile.*`, and `tools.*` for the Executas in `required_executas` / `optional_executas` — is callable by an installed, enabled App; the user's CU quota is the only usage gate. The block holds the two declarations that involve something other than the user's own account:

| Key | Type | Declares |
|---|---|---|
| `credentials` | array of **provider ids** (e.g. `"google"`) | Third-party accounts your iframe may read via `credentials.list_accounts` / `credentials.get_token`. The user must also have connected the provider on the platform. An undeclared provider → `permission_denied` |
| `agent` | `{ "tools": [tool id, …] }` or `{ "tools": ["*"] }` | Host-kit tools that run on the user's machine (`fs_*`, `exec_*`, `browser_*`) which sandbox agent sessions created by this App may use; `"*"` = all of them. Server-side tools (`doc_read`, `web_search`, …) never need declaring. Effective set per session = `requested ∩ (server_side ∪ (host_kit ∩ declared))` — see [LLM & Agent](/developers/apps/llm-and-agent#1-what-you-declare) |

Anything else inside `host_api` is rejected on a `schema: 4` manifest. Older manifests that still carry the pre-schema-4 method tables (`"storage": ["get", "set"]`, `"tools": ["required:*"]`, `"agent": { "session": … }`, …) are accepted and [normalized](/developers/apps/app-manifest#legacy-manifests-schema-13): the method tables are dropped, `tools` refs become `optional_executas`, and `"audio": ["session"]` becomes `browser_permissions: ["microphone"]`.

Cross-app storage scopes are declared at the manifest top level ([`storage.scopes`](/developers/apps/app-manifest#capability-declarations)), not here. Full method-level reference: [App UI Host API](/developers/apps/app-ui-host-api).

### `csp_overrides`

Only these CSP directives may be added to / extended on the bundle response:

```
connect-src
img-src
media-src
font-src
style-src     ('self' | 'sha256-...' | 'nonce-...' only)
script-src    ('self' | 'wasm-unsafe-eval' | 'sha256-...' | 'nonce-...' only)
frame-src     (explicit https://host[:port] origins only — no '*', no path, no CSP keywords; max 8)
```

Anything else is rejected. The base CSP is always:

```
default-src 'none'
base-uri 'self'
script-src 'self' <sdk-origin>
style-src 'self' 'unsafe-inline'
img-src 'self' data: blob:
font-src 'self' data:
media-src 'self' blob:
connect-src 'self'
worker-src 'self' blob:
frame-ancestors 'self'
form-action 'self'
```

`external_origins` from `ui.bundle` are automatically added to `connect-src` and `img-src` — you do **not** need to repeat them in `csp_overrides`.

### Embedding third-party content (frame-src)

By default the bundle CSP has no `frame-src`, so nested iframes fall back to `default-src 'none'` and **every embed is blocked**. To embed third-party content (a YouTube player, a map, a docs viewer…), declare the exact origins:

```jsonc
"csp_overrides": {
  "frame-src": ["https://www.youtube-nocookie.com"]
}
```

Rules: explicit `https://host[:port]` origins only — no `*` or wildcard subdomains, no paths, no CSP keywords (`'self'`, `'none'`, …), at most 8 origins. The declared origins are disclosed on the App's install/review surface, like `external_origins`.

Declaring `frame-src` also unlocks the **playback permission chain**: the platform scopes `autoplay`, `encrypted-media`, `fullscreen` and `picture-in-picture` to your declared origins (both in the bundle's `Permissions-Policy` response header and in the host window's iframe `allow` attribute). Every other browser feature stays denied unless you list it in [`ui.browser_permissions`](/developers/apps/app-ui-browser-permissions) — a realtime voice session, for example, needs `"microphone"` there so `getUserMedia` works (see [App UI Audio Session](/developers/apps/app-ui-audio-session)).

Your own `<iframe>` inside the bundle **must still forward those features** — the delegation chain is per-frame:

```html
<iframe
  src="https://www.youtube-nocookie.com/embed/VIDEO_ID?start=90"
  allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
></iframe>
```

Without the `allow` attribute the player renders but fullscreen / autoplay-on-seek silently fail.

Tips:

- Prefer `https://www.youtube-nocookie.com` over `https://www.youtube.com` — same player, fewer ambient cookies sent to Google.
- **Don't strip the referrer on your embed iframe.** Declaring `frame-src` also relaxes the bundle's `Referrer-Policy` from `no-referrer` to `strict-origin-when-cross-origin` (cross-origin requests carry the origin only, never the path) — YouTube requires a Referer on embed requests and shows **error 153** ("video player configuration error") without one. Adding `referrerpolicy="no-referrer"` to your `<iframe>` re-breaks it.
- **Local harness parity**: `anna-app dev` serves your bundle without CSP headers, so embeds work locally even *without* the declaration (the `Permissions-Policy` header, by contrast, is production-aligned since CLI 0.1.63). Always verify with `anna-app validate` and an online working draft before relying on local behaviour.
- The embedded page is a normal cross-origin iframe: it inherits the app sandbox, cannot reach the Anna host bridge, and cannot call Host APIs.

### WebAssembly

`WebAssembly.compile` / `WebAssembly.instantiate` are gated by `script-src`, and the base CSP does not allow them. Opt in per app:

```jsonc
"csp_overrides": {
  "script-src": ["'wasm-unsafe-eval'"]
}
```

`'wasm-unsafe-eval'` enables **only** WebAssembly compilation — it does not enable JS `eval()` / `new Function()`.

- Ship `.wasm` files inside your bundle (`application/wasm` is on the [upload whitelist](/developers/apps/app-ui-bundle)) and fetch them same-origin. `connect-src` stays `'self'` unless you extend it, so runtime loading of WASM from third-party origins is blocked by default — keep it that way.
- **Single-threaded builds only.** App iframes are not cross-origin isolated (no COOP/COEP), so `SharedArrayBuffer` is unavailable and pthread/multi-threaded WASM builds will not run. Use single-threaded variants (e.g. the single-thread ffmpeg.wasm core).
- CSP has no per-module hash pinning for WASM — the directive applies to all WASM compiled in the iframe.
- Available on every plan; no review flag is required.

## Validation

Two passes:

1. **Static** — runs on every `validate-manifest` and version-create call. Checks `format`, view counts/sizes, `host_api` shape (`credentials` / `agent.tools` only), `browser_permissions` allow-list, `csp_overrides` shape, `external_origins` schemes.
2. **With files** — runs at `bundle/finalize`. Confirms `bundle.entry` exists in the uploaded `file_map`.

Both raise `ManifestValidationError` with a Chinese-language reason string. Common rejections:

- `ui.bundle.format 当前仅支持 'static-spa'`
- `ui.views 数量必须在 1..16 之间`
- `ui.views 中只能有一个 default=true`
- `view '<name>' default_size 小于 min_size`
- `browser_permissions contains an unsupported feature: ['payment']`
- `browser_permissions has duplicate entries: ['microphone']`
- `csp_overrides 含不允许的 directive: [...]`
- `csp_overrides[script-src] 仅允许 'self' / 'wasm-unsafe-eval' / 'sha256-...' / 'nonce-...'`
- `csp_overrides[style-src] 仅允许 'self' / 'sha256-...' / 'nonce-...'`
- `csp_overrides[frame-src] only allows explicit https:// origins (no '*', no path, no CSP keywords)`
- `csp_overrides[frame-src] allows at most 8 origins`
- `ui.bundle.entry '<path>' 未在上传的 file_map 中` *(at finalize)*

Next: [App UI Bundle Pipeline](/developers/apps/app-ui-bundle).
