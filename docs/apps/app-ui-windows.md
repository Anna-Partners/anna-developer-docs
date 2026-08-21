---
title: "App UI Windows"
description: "Window lifecycle, geometry persistence, multi-tab/device sync, dock, single-instance dedup."
section: apps
slug: app-ui-windows
order: 12
updated: 2026-04-28
estimated_minutes: 5
category: "App UI"
---

Each Anna App UI window is a row in `anna_app_window_sessions`. The frontend treats every window as ephemeral DOM; **all** durable state lives server-side.

## Lifecycle

```
                          ┌──── REST: POST /runtime/windows ────┐
LLM (open_app_view) ─────►│                                     │
User (deck click)  ─────► │  status = active                    │
SSE: open_view             │  geometry = view.default_size      │
                          │  entry_payload = caller-supplied    │
                          │  runtime_state = {} or persisted    │
                          └──────────────┬──────────────────────┘
                                         │  Window Manager mounts <iframe>
                                         ▼
                                    ┌──────────┐
                              ┌────►│ active   │── user click "—" ──► minimized
                              │     └────┬─────┘                          │
                              │          │ user closes ×                  │
                              │          ▼                                │
                              │     ┌──────────┐                          │
                              │     │ closed   │◄─── close_app_view ──────┘
                              │     └──────────┘
                              │ iframe crash / report_error
                              │          │
                              │          ▼
                              │     ┌──────────┐
                              └─────│ crashed  │
                                    └──────────┘
```

Status values (`AnnaAppWindowStatus`):

- `active` — currently mounted (or eligible to mount on hydrate).
- `minimized` — collapsed to dock; iframe unmounted, state preserved.
- `closed` — terminal; will not rehydrate.
- `crashed` — terminal; LLM is informed and may re-open.

## Endpoints

All under `/api/v1/anna-apps/runtime/`:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/windows` | Open a window (LLM and deck both go through this) |
| `GET` | `/windows?conversation_session_uuid=…` | List active+minimized windows for the current conversation (used at hydrate) |
| `GET` | `/windows/{wid}` | Window detail incl. fresh JWT, sdk_url, bundle_url, runtime_state |
| `PATCH` | `/windows/{wid}` | Patch geometry / status / title / runtime_state (debounced 250 ms by frontend) |
| `DELETE` | `/windows/{wid}` | Close the window |
| `POST` | `/windows/{wid}/flush` | `navigator.sendBeacon`-friendly flush of `runtime_state` |
| `POST` | `/rpc` | Iframe → host RPC (see [Host API](/developers/apps/app-ui-host-api)) |
| `GET` | `/events/stream` | Server-Sent Events on the per-user channel |

Every PATCH and DELETE re-broadcasts a `data_model/AnnaAppEvent` over SSE so other tabs/devices stay in sync.

## Geometry & resize

```jsonc
"geometry": {
  "x": 240, "y": 120,
  "w": 960, "h": 640,
  "monitor_w": 1920, "monitor_h": 1080,
  "dock_pinned": false,
  "dock_side": null,    // "left" | "right" | "bottom" | null
  "snapped":   null     // "left" | "right" | "max" | null
}
```

- Drag/resize uses an in-memory transform for 60 fps; on `pointerup` the Window Manager `_schedulePatch`-es a `PATCH /windows/{wid} { geometry }` after a 250 ms debounce.
- The backend clamps `w`/`h` to the view's `min_size` and `max_size` (from the manifest).
- `monitor_w` / `monitor_h` are stored so a second device with a different screen can re-flow proportionally.

## Single-instance views

If a view declares `single_instance: true`, opening it again under the same `(user_id, conversation_session_uuid, app_id, view)` re-focuses the existing window and merges the new payload into `entry_payload`. Otherwise a fresh window is spawned.

## `runtime_state`

A 256 KB JSON blob, set via `storage.set` from inside the iframe. Use it for tiny UI state (current tab, open accordions, scroll position). For anything larger, store the blob in your own backend / artifact and put only a handle here.

```jsonc
"runtime_state": {
  "draft": { "title": "…", "body": "…" },
  "selectedTab": "preview"
}
```

`PATCH /windows/{wid} { runtime_state_patch }` is shallow-merged with the current `runtime_state` (last-writer-wins). To do a full replacement use `replace_runtime_state` (admin only) or `storage.delete` + re-set.

## Cross-tab / cross-device sync

Server-Sent Events on `GET /runtime/events/stream` carry envelopes of type `data_model/AnnaAppEvent`:

```jsonc
{
  "type": "data_model/AnnaAppEvent",
  "kind": "geometry_changed",     // see table below
  "window_uuid": "…",
  "app_id": "…",
  "version_id": "…",
  "conversation_session_uuid": "…",
  "by_client_id": "…",            // the client that originated the change; suppress local echo
  "ts": 1714291200,
  "payload": { … }                // kind-specific
}
```

Event kinds:

| `kind` | Payload |
|---|---|
| `artifact_appended` | `{ artifact_id, kind, summary?, payload?, payload_ref? }` *(app appended a chat artifact)* |
| `chat_message_from_app` | `{ role, content }` *(app posted into the conversation)* |
| `close_view` | `{ window_uuid, reason? }` |
| `geometry_changed` | `{ geometry }` |
| `open_view` | `{ window_uuid, app_id, version_id, view, entry_payload, geometry, runtime_state, source }` |
| `ping` | `{}` *(keepalive)* |
| `rpc.stream` | `{ … }` *(streaming RPC chunk — e.g. agent run frames)* |
| `runtime_state_synced` | `{ runtime_state }` *(only on full sync; patches are not broadcast to keep traffic small)* |
| `status_changed` | `{ status }` |
| `title_changed` | `{ title }` |
| `window_focus_changed` | `{ window_uuid, z_index }` |

These are the canonical wire `kind`s (see `AnnaAppEvent.json` in the published [`@anna-ai/app-schema`](https://www.npmjs.com/package/@anna-ai/app-schema) package); treat any unknown `kind` as a forward-compatible addition and ignore it. `entry_payload` is **not** a wire `kind` — the SDK re-surfaces entry-payload updates (carried by `open_view`) and `runtime_state_synced` to your `anna.on(...)` callbacks.

The Window Manager applies these via `applyEvent(event)`.

## Hydration on dashboard load

On page load `AnnaAppWM.init().hydrate(conversation_session_uuid)`:

1. `GET /runtime/windows?conversation_session_uuid=…` returns every `active` and `minimized` window for the current conversation.
2. For each, the Window Manager **reuses** the existing `window_uuid`, mints no new session, and mounts an iframe at `/anna-apps/{slug}/{version}/{entry}?wid=…&t=<freshly-issued-jwt>`.
3. Minimized windows render a dock chip but no iframe until restored.

Refreshing the page does **not** create new windows. Closing a tab without the user pressing × does **not** mark the window `closed` — only an explicit user action or `close_app_view` does.

## Idle reaper

Active windows with no heartbeat or RPC for **24 h** (default) are auto-marked `closed` and broadcast `close_view`. Tune via env `ANNA_APP_WINDOW_IDLE_HOURS`.

## sendBeacon flush

On `pagehide` the Host Bridge fires `navigator.sendBeacon('/runtime/windows/{wid}/flush', JSON.stringify({ runtime_state }))` so the latest state is durable even when the user just closes the tab. The endpoint is idempotent and requires no JWT (it's auth-checked by session cookie).

Next: [App UI LLM Integration](/developers/apps/app-ui-llm).
