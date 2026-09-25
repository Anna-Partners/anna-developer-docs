---
title: "App UI Manifest"
description: "The `ui` section of a schema ≥ 2 manifest: bundle, views, host_api, csp_overrides."
section: apps
slug: app-ui-manifest
order: 10
updated: 2026-09-11
estimated_minutes: 6
category: "App UI"
---

When `schema` ≥ 2 (current maximum: 3), an Anna App manifest gains a `ui` section that describes the static bundle, the named views the LLM can summon, the host API scopes the iframe is allowed to call, and any per-bundle CSP overrides. Everything else from [App Manifest](/developers/apps/app-manifest) still applies — including the schema-3 changes (structured [`storage`](/developers/apps/app-manifest#storage-schema-3) entry, top-level `permissions` removed).

## Example

```jsonc
{
  "schema": 3,
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
      "tools":  ["required:*"],
      "chat":   ["append_artifact"],
      "storage": ["get", "set", "delete", "list"],
      "window": ["set_title", "open_view", "close"]
    },
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
| `host_api` | object | no | RPC ACL. See [`host_api`](#host_api). Defaults to all empty (only the always-allowed `window` scope) |
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

`mobile_entry` is served instead of `entry` when the window is opened from a mobile container — see [Mobile Support](/developers/apps/app-mobile). A single responsive entry is recommended.

`single_instance: true` means: opening the same `view` again under the same `(user, conversation_session_uuid, app_id)` re-focuses the existing window and merges the new payload into `entry_payload` rather than spawning a second window.

### `host_api`

The ACL that gates host RPC calls from your iframe. Each namespace key is a list of **method names** the iframe is allowed to invoke (`agent` is the one exception — an object spec). `window.*` is always granted; everything else requires explicit listing. This ACL is the **only** manifest-level gate — the legacy top-level `permissions` list is never consulted (see below). Some namespaces are additionally gated by a per-app, user-controlled grant enforced host-side (noted per row).

| Namespace | Allowed values | What it grants |
|---|---|---|
| `tools` | `required:*` &#124; `optional:*` &#124; `required:<tool_id>` &#124; `optional:<tool_id>` &#124; `<tool_id>` | Calls to [`tools.invoke`](/developers/apps/app-ui-host-api#tools) on the listed Executas. Bare `<tool_id>`s must appear in `required_executas` or `optional_executas`. **Optional narrowing**: empty/omitted ⇒ every declared executa is callable |
| `chat` | `append_artifact`, `write_message` ⏳, `read_history` ⏳ | Attach artifact cards; post messages / read history (stubs today) |
| `artifact` | `create`, `update`, `delete` | Manipulate chat artifacts *(stub, Phase 3)* |
| `llm` | `complete`, `stream`, `embed` | Host-side LLM calls bound to the user's quota — see [LLM & Agent](/developers/apps/llm-and-agent) |
| `agent` | object, not a list: `{ "session": { "auto": true, "fixed": false }, "tools": […] }` | Multi-turn agent sessions (`agent.session.*`); at least one submode must be `true`. `tools` optionally narrows the session's tool surface |
| `fs` | `read`, `write` | Anna Agent filesystem access *(stub, Phase 3)* |
| `storage` | `get`, `set`, `delete`, `list` | Per-window `runtime_state` (≤256 KB); with a schema-3 [`storage`](/developers/apps/app-manifest#storage-schema-3) declaration the same methods are APS-backed (`anna.storage.*`) |
| `files` | `upload_init`, `upload_finalize`, `download_url`, `download`, `list`, `delete` | APS object/file storage (`anna.files.*`); per-call scope is gated by the install-time `storage_token`, not by this list |
| `prefs` | `get` | Read user preferences *(stub)* |
| `image` | `generate`, `edit` | Host-mediated image generation/editing — also gated by the per-app `image_grant` |
| `upload` | `inline`, `negotiate`, `confirm` | User-artifact uploads to host storage — also gated by the per-app `upload_grant` |
| `web` | `search`, `fetch`, `image_search`, `image_fetch` | Host-managed web search/fetch (provider keys, SSRF guard, billing stay host-side) — also gated by the per-app `web_grant` |
| `apps` | `list`, `search`, `get`, `launch`, `deck.list`, `deck.add`, `deck.remove`, `deck.reorder` | Apps launcher: browse/launch the user's installed apps, curate the "我的 Apps" deck |
| `credentials` | **provider ids** (e.g. `google`), not method names | `credentials.list_accounts` / `credentials.get_token` for the listed providers — also gated by the per-app `credentials_grant` |
| `mobile` | `share`, `haptics`, `camera_capture` | Native bridge — only executable inside the anna-mobile shell; desktop containers answer `unsupported_container` |
| `window` | (always granted) | Geometry, title, focus, open/close — listing values here is harmless |

Full method-level reference: [App UI Host API](/developers/apps/app-ui-host-api).

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

Declaring `frame-src` also unlocks the **playback permission chain**: the platform scopes `autoplay`, `encrypted-media`, `fullscreen` and `picture-in-picture` to your declared origins (both in the bundle's `Permissions-Policy` response header and in the host window's iframe `allow` attribute). All other features (camera, microphone, geolocation, …) stay denied.

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
- **Local harness parity**: `anna-app dev` serves your bundle without CSP or Permissions-Policy headers, so embeds work locally even *without* the declaration. Always verify with `anna-app validate` and an online working draft before relying on local behaviour.
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
- Available on every plan; no review flag or extra permission is required.

### Top-level `permissions` (legacy, `schema ≤ 2` only)

The root-level `permissions` list is **display-only legacy metadata with zero enforcement sites** — the dispatcher gates every host RPC on `ui.host_api` (plus the per-app grants noted above) and never reads `permissions`. At `schema: 3` the field is **rejected outright** (`permissions: removed in schema 3 — permission display is derived from ui.host_api + storage/host_capabilities`); the Store/review permission display is derived from the enforced declarations instead. On `schema ≤ 2` apps it is accepted (allow-list validated) but ignored at runtime — see the [Manifest reference](/developers/apps/app-manifest#field-reference).

## Validation

Two passes:

1. **Static** — runs on every `validate-manifest` and version-create call. Checks `format`, view counts/sizes, `host_api.tools` references, `csp_overrides` shape, `external_origins` schemes.
2. **With files** — runs at `bundle/finalize`. Confirms `bundle.entry` exists in the uploaded `file_map`.

Both raise `ManifestValidationError` with a Chinese-language reason string. Common rejections:

- `ui.bundle.format 当前仅支持 'static-spa'`
- `ui.views 数量必须在 1..16 之间`
- `ui.views 中只能有一个 default=true`
- `view '<name>' default_size 小于 min_size`
- `host_api.tools 引用未在 manifest 中声明的 tool_id: <ref>`
- `csp_overrides 含不允许的 directive: [...]`
- `csp_overrides[script-src] 仅允许 'self' / 'wasm-unsafe-eval' / 'sha256-...' / 'nonce-...'`
- `csp_overrides[style-src] 仅允许 'self' / 'sha256-...' / 'nonce-...'`
- `csp_overrides[frame-src] only allows explicit https:// origins (no '*', no path, no CSP keywords)`
- `csp_overrides[frame-src] allows at most 8 origins`
- `ui.bundle.entry '<path>' 未在上传的 file_map 中` *(at finalize)*

Next: [App UI Bundle Pipeline](/developers/apps/app-ui-bundle).
