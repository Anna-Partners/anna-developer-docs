---
title: "Anna App UI Overview"
description: "How Anna Apps render an interactive sandboxed window on the dashboard, and how the LLM, the iframe, and the host coordinate."
section: apps
slug: app-ui-overview
order: 9
updated: 2026-04-28
estimated_minutes: 5
category: "App UI"
---

A `schema: 1` Anna App is just "a manifest + a set of Executas". When you bump the manifest to `schema: 2` and add a `ui` section, the app graduates to a **Talk-to-the-App, Run-in-a-Window** form factor: Anna can summon a sandboxed `<iframe>` window on the dashboard, the user can drag/resize/minimize it, and your iframe code can call back into the host through a typed RPC bridge.

This page is the framework-level orientation. Every concrete file/contract is linked to its detail page.

## What you ship

| Thing | Where it lives |
|---|---|
| `AnnaApp` row (listing, status, developer) | DB `anna_apps` |
| `AnnaAppVersion` row + manifest JSON (`schema: 2`, contains `ui`) | DB `anna_app_versions.manifest` |
| `AnnaAppUiBundle` + `AnnaAppUiFile[]` rows | DB; assets in R2 (`anna-app-bundles/<env>/<slug>/<version>/...`) |
| Static assets (your SPA: `index.html`, JS, CSS, wasm, fonts) | Uploaded by you via `bundle/init` → per-file PUT → `bundle/finalize` |
| `AnnaAppWindowSession` rows (one per opened window) | DB `anna_app_window_sessions` (created at runtime) |

## Runtime topology

```
┌──────────────────────────── Browser (/dashboard) ───────────────────────────┐
│                                                                              │
│  ┌─Chat Pane──┐  ┌─App Deck──┐  ┌──────── Window Layer ────────────┐         │
│  │ messages   │  │ installed │  │ floating <iframe sandbox> windows │         │
│  │ SSE stream │  │ apps      │  │ headers, resize, dock, z-index    │         │
│  └────────────┘  └───────────┘  └───────────────────────────────────┘         │
│       ▲              ▲                       ▲                                │
│       │              │                       │                                │
│  ┌────┴──────────────┴────────── Window Manager ───────────────────────┐      │
│  │  AnnaAppWM: open/focus/close/minimize/dock                          │      │
│  │  Hydrates from GET /runtime/windows on dashboard load               │      │
│  │  Applies SSE events (open_view, geometry_changed, …)                │      │
│  └────────────────────────────────────────────────────────────────────-┘      │
│                                  │                                            │
│                          ┌───────┴────────┐                                   │
│                          │ Host Bridge    │  postMessage  ◀── iframe SDK ──   │
│                          │ token mint +   │  /api/v1/anna-apps/runtime/rpc    │
│                          │ ACL forwarding │                                   │
│                          └───────┬────────┘                                   │
└──────────────────────────────────┼────────────────────────────────────────────┘
                                   │
        ┌──────────────────────────┴───────────────────────────┐
        │ Nexus FastAPI                                        │
        │ /anna-apps/{slug}/{version}/<path>          (assets) │
        │ /api/v1/anna-apps/runtime/windows[/{wid}]    (CRUD)  │
        │ /api/v1/anna-apps/runtime/rpc               (RPC)    │
        │ /api/v1/anna-apps/runtime/events/stream     (SSE)    │
        └──────────────────────────┬───────────────────────────┘
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        │ AnnaAppWindowSession (Postgres) + Redis pub/sub      │
        └──────────────────────────┬───────────────────────────┘
                                   │  invokes
                                   ▼
                       ┌────────────────────────┐
                       │ Executa via NATS RPC   │
                       │ (user's Anna Agent)    │
                       └────────────────────────┘
```

There are four pieces:

1. **Window Manager** — a frontend singleton (`window.AnnaAppWM`) that owns the window DOM and the dock.
2. **Host Bridge** — routes `postMessage` between every iframe and the backend RPC endpoint, mints/refreshes per-window tokens.
3. **Backend Runtime** (`/api/v1/anna-apps/runtime/*` + `/anna-apps/...` for assets) — window CRUD, RPC dispatcher with manifest-driven ACL, SSE event stream, bundle serving with per-bundle CSP.
4. **LLM Tools** (`open_app_view` / `update_app_view` / `close_app_view`) — only injected when at least one mentioned app declares `ui.views`. The LLM uses them to summon, push state into, or close a window.

## Lifecycle of one user request

```
1.  User #mentions an app with `ui.views`.
2.  Backend builds <user_mentioned_apps>… <ui_views>…</ui_views> into the system prompt
    and injects open_app_view/update_app_view/close_app_view into the LLM tool list.
3.  LLM decides to call open_app_view(app_id, view, payload).
4.  Backend creates (or dedups) AnnaAppWindowSession, mints a 120s JWT, emits SSE
    `data_model/AnnaAppEvent { kind: "open_view", … }` on the user channel.
5.  Window Manager receives the SSE event, mounts an <iframe sandbox>
    pointing at /anna-apps/{slug}/{version}/{entry}?wid=…&t=…
6.  iframe imports /static/anna-apps/_sdk/latest/index.js as an ES module, calls
    AnnaAppRuntime.connect(); the SDK sends `window.hello` over postMessage.
7.  Host Bridge forwards hello to /runtime/rpc; backend returns capabilities,
    view_meta, entry_payload, runtime_state, geometry.
8.  iframe renders. It can now invoke whitelisted tools, push artifacts to chat,
    persist state via storage.set, etc.
9.  User drags/resizes the window → Window Manager debounces a PATCH /windows/{wid}
    {geometry: …} → backend persists + broadcasts SSE `geometry_changed` to other
    tabs/devices.
10. LLM may push updates by calling update_app_view (sends `entry_payload` patch
    over SSE → SDK exposes as `entry_payload` event).
11. User closes the window → Window Manager DELETEs /windows/{wid}; backend marks
    status=closed and emits SSE `close_view`. Other tabs cleanly tear down too.
```

## Persistence model (no `localStorage`)

All window state is server-authoritative so opening the same conversation in another tab or device shows the exact same windows in the exact same positions:

| Layer | Storage | Examples |
|---|---|---|
| Geometry, dock, monitor size | `anna_app_window_sessions.geometry` (JSON) | `{x, y, w, h, monitor_w, monitor_h, dock_pinned, dock_side, snapped}` |
| Window meta | `anna_app_window_sessions` columns | `window_uuid`, `status`, `view`, `entry_payload`, `conversation_session_uuid`, `last_focus_at` |
| App-internal state (≤256 KB) | `anna_app_window_sessions.runtime_state` (JSON) | written by your SDK call `storage.set(...)`; flushed via `navigator.sendBeacon` on tab close |
| Large objects | R2 / artifact; runtime_state holds only a handle | uploaded blobs |

Closing **≠** refreshing. Only an explicit user `×` or `close_app_view` flips `status` to `closed`. A page reload simply re-hydrates from `GET /runtime/windows` and re-attaches to the same `window_uuid`.

## Security baseline

- iframe runs in a `<iframe sandbox>` (no `allow-same-origin` in the spec; the SDK itself talks only via `postMessage`).
- Every request from iframe → backend carries a short-TTL (120s) JWT bound to `(window_uuid, user_id, app_id, version_id, scopes)`. The Host Bridge auto-refreshes it.
- Asset responses include a per-bundle `Content-Security-Policy` (default `default-src 'none'`, `frame-ancestors 'self'`, `script-src 'self'`, …) plus `X-Content-Type-Options: nosniff`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy` locking off camera/mic/geolocation.
- Every host RPC re-validates the `(ns, method)` against `manifest.ui.host_api`. Unauthorised calls return `permission_denied` without ever reaching the handler.

## Where to next

Build it in this order:

1. [App UI Manifest](/developers/apps/app-ui-manifest) — declare `ui.bundle`, `ui.views`, `ui.host_api`.
2. [App UI Bundle Pipeline](/developers/apps/app-ui-bundle) — upload your static SPA via `bundle/init` → file PUT → `bundle/finalize`.
3. [App UI SDK](/developers/apps/app-ui-sdk) — wire `AnnaAppRuntime.connect()` inside your `index.html`.
4. [App UI Host API](/developers/apps/app-ui-host-api) — full RPC namespace reference + permissions matrix.
5. [App UI Windows](/developers/apps/app-ui-windows) — window lifecycle, persistence, multi-device sync, dock, sizing.
6. [App UI LLM Integration](/developers/apps/app-ui-llm) — `open_app_view` / `update_app_view` / `close_app_view`, SSE events, chat ↔ window patterns.
