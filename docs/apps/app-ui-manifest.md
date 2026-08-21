---
title: "App UI Manifest"
description: "The `ui` section of a schema-2 manifest: bundle, views, host_api, csp_overrides."
section: apps
slug: app-ui-manifest
order: 10
updated: 2026-04-28
estimated_minutes: 6
category: "App UI"
---

When `schema: 2`, an Anna App manifest gains a `ui` section that describes the static bundle, the named views the LLM can summon, the host API scopes the iframe is allowed to call, and any per-bundle CSP overrides. Everything else from [App Manifest](/developers/apps/app-manifest) still applies.

## Example

```jsonc
{
  "schema": 2,
  "permissions": [
    "tools.invoke",
    "chat.append_artifact",
    "storage.read", "storage.write"
  ],
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
| `host_api` | object | no | RPC ACL. See [`host_api`](#host_api). Defaults to all empty (only the always-allowed `window` scope) |
| `csp_overrides` | object | no | Map of CSP directive → list of values. Only the directives below are accepted; `script-src` / `style-src` accept only `'self'`, `'sha256-...'`, `'nonce-...'` |
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

`single_instance: true` means: opening the same `view` again under the same `(user, conversation_session_uuid, app_id)` re-focuses the existing window and merges the new payload into `entry_payload` rather than spawning a second window.

### `host_api`

The ACL that gates host RPC calls from your iframe. Each namespace key is a list of methods the iframe is allowed to invoke. `window.*` is always granted; everything else requires explicit listing.

| Namespace | Allowed values | What it grants |
|---|---|---|
| `tools` | `required:*` &#124; `optional:*` &#124; `required:<tool_id>` &#124; `optional:<tool_id>` &#124; `<tool_id>` | Calls to [`tools.invoke`](/developers/apps/app-ui-host-api#tools) on the listed Executas. Bare `<tool_id>`s must appear in `required_executas` or `optional_executas` |
| `chat` | `read`, `write_message`, `append_artifact` | Read history, post messages, attach artifact cards |
| `artifact` | `create`, `update`, `delete` | Manipulate chat artifacts |
| `llm` | `complete` | Trigger a host-side LLM completion |
| `fs` | `read`, `write` | R2 / Anna Agent filesystem access |
| `storage` | `read`, `write` | Per-window `runtime_state` (≤256 KB) |
| `prefs` | `read` | Read user preferences |
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
script-src    ('self' | 'sha256-...' | 'nonce-...' only)
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

### Top-level `permissions`

Although the field lives at the manifest root (not under `ui`), the Anna App UI Runtime enforces it on every host RPC call: a method whose namespace is gated by a permission (e.g. `chat.write_message` requires the `chat.write_message` permission) will return `permission_denied` when not declared. Allowed values are listed in the [Manifest reference](/developers/apps/app-manifest#field-reference).

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
- `csp_overrides[script-src] 仅允许 'self' / 'sha256-...' / 'nonce-...'`
- `ui.bundle.entry '<path>' 未在上传的 file_map 中` *(at finalize)*

Next: [App UI Bundle Pipeline](/developers/apps/app-ui-bundle).
