---
title: "App UI SDK"
description: "Embed the Anna App SDK in your bundle and call host APIs from inside the iframe."
section: apps
slug: app-ui-sdk
order: 13
updated: 2026-04-28
estimated_minutes: 5
category: "App UI"
---

The Anna App SDK is a single ESM file the host serves at:

```
/static/anna-apps/_sdk/latest/index.js
```

It runs **inside your iframe**, talks to the parent window over `postMessage`, and exposes a typed runtime object you use to call the host. It is a native ES module (it `export`s `AnnaAppRuntime`; there is no `window` global), so you load it with a single `<script type="module">` + `import` — the SDK origin is automatically allow-listed in your bundle's `script-src`.

## Minimum bundle

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>My App</title>
  <link rel="stylesheet" href="./assets/app.css" />
</head>
<body>
  <main id="root">Loading…</main>
  <script type="module">
    import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

    const anna = await AnnaAppRuntime.connect();
    document.getElementById("root").textContent =
      anna.runtimeState?.notes ?? `Hello, ${anna.viewMeta.title}!`;

    // Persist on user input (debounce yourself)
    document.addEventListener("input", e => {
      anna.storage.set({ key: "notes", value: e.target.value });
    });
  </script>
</body>
</html>
```

That's it. No bundler is required; ESM imports work because the host serves the SDK with `Content-Type: application/javascript` and the bundle CSP already allows `script-src 'self' <sdk-origin>`.

## `AnnaAppRuntime.connect()`

```ts
const anna = await AnnaAppRuntime.connect();
```

Behind the scenes:

1. Reads `wid` and `t` from the iframe URL `?wid=…&t=…`.
2. Sends a `window.hello` RPC over `postMessage` to the parent.
3. Receives `capabilities`, `view_meta`, `entry_payload`, `runtime_state`, `geometry` and resolves.
4. Starts a 10s heartbeat (`window.ready` after first hello, then `window.heartbeat`).
5. Subscribes to host events (`auth.refresh`, `entry_payload`, `runtime_state_synced`, `geometry_changed`, `close`, …) — `auth.refresh` is handled internally by replacing the bound token.

The returned object:

```ts
interface AnnaAppRuntime {
  windowUuid: string;
  appId:      string;
  versionId:  string;
  viewMeta:   { name: string; title: string; default_size: {w,h}; … };
  capabilities: { tools: string[]; chat: string[]; storage: string[]; … };

  /** Initial payload supplied by `open_app_view(payload=…)` */
  entryPayload: any;
  /** Server-persisted runtime_state from `storage.set` calls */
  runtimeState: Record<string, any>;
  /** Last known window geometry */
  geometry: { x: number; y: number; w: number; h: number; … };

  // Namespaced proxies — every method returns a Promise<RpcResponse>
  tools:    { list(): Promise<…>; invoke(args): Promise<…> };
  chat:     { append_artifact(args): Promise<…> /* …stubs… */ };
  storage:  { get(args): Promise<…>; set(args): Promise<…>; delete(args): Promise<…> };
  artifact: { /* stubs, see Host API */ };
  llm:      { /* stubs, see Host API */ };
  fs:       { /* stubs, see Host API */ };
  prefs:    { /* stubs, see Host API */ };
  window: {
    set_title({ title }):    Promise<…>;
    resize({ w, h }):        Promise<…>;
    focus():                 Promise<…>;
    close({ reason? }):      Promise<…>;
    open_view({ view, payload? }): Promise<…>;
    report_error({ message, stack? }): Promise<…>;
  };

  // Event subscription
  on(event:
       | "entry_payload"
       | "runtime_state_synced"
       | "geometry_changed"
       | "title_changed"
       | "close",
     handler: (payload: any) => void
    ): () => void;  // returns unsubscribe
}
```

Every namespace proxy is generated dynamically from `capabilities` returned by `window.hello`. If your manifest does not list `chat.append_artifact`, calling `anna.chat.append_artifact(...)` from inside the iframe will throw `permission_denied` — you cannot escalate from the client.

## Resume vs first open

The host calls your iframe with two bundles of state:

| Field | Source | Purpose |
|---|---|---|
| `entry_payload` | `open_app_view(payload=…)` and `update_app_view(runtime_state_patch=…)` | Per-call instructions from the LLM (or the user via the deck) |
| `runtime_state` | `storage.set` calls from prior sessions | Your own persisted UI state (≤256 KB total) |

Recommended pattern:

```js
const anna = await AnnaAppRuntime.connect();

if (anna.runtimeState?.bootedOnce) {
  // Resume: rebuild UI from runtime_state, then merge any new entry_payload
  hydrateFrom(anna.runtimeState);
  if (anna.entryPayload) applyAdditionalInstruction(anna.entryPayload);
} else {
  // First open: drive UI from entry_payload alone
  bootstrapFrom(anna.entryPayload);
  await anna.storage.set({ key: "bootedOnce", value: true });
}

anna.on("entry_payload", payload => {
  // LLM pushed new instructions via update_app_view
  applyAdditionalInstruction(payload);
});

anna.on("runtime_state_synced", state => {
  // Another tab/device updated runtime_state
  hydrateFrom(state);
});
```

## Storing state

`storage.set` writes into `anna_app_window_sessions.runtime_state` (JSON, max 256 KB). Use it as a tiny key-value store. For larger objects, persist them to your own backend or to an artifact and store only a handle in `runtime_state`.

```js
await anna.storage.set({ key: "draft", value: { title, body } });
const { value } = await anna.storage.get({ key: "draft" });
await anna.storage.delete({ key: "draft" });

// Enumerate keys (paginated, returns the APS list shape):
const { items, next_cursor } = await anna.storage.list({
  prefix: "draft/",
  limit: 100,
});
```

The host debounces the underlying disk write; concurrent calls are coalesced. On tab close the host page emits a `navigator.sendBeacon` flush to `POST /runtime/windows/{wid}/flush` so the latest state is durable even when the user just closes the tab.

## Calling Executas

```js
const { result } = await anna.tools.invoke({
  tool_id: "tool-yourhandle-browser-abcd1234",
  method:  "page.fetch",   // required when tool_id is mint-only (no fixed plugin namespace)
  args:    { url: "https://example.com" }
});
```

The host resolves the `tool_id` against `(plugin_name, tool_name)` from the Executa registry, then invokes the Executa over NATS on the user's currently-online Anna Agent. If no agent is online you get `agent_unavailable`.

If you supplied a per-Executa allow-list in `host_api.tools` (e.g. `["required:tool-yourhandle-browser-abcd1234"]`), only those `tool_id`s can be invoked.

## Title, resize, close

```js
await anna.window.set_title({ title: "Editing report.md" });
await anna.window.resize({ w: 1024, h: 768 });
await anna.window.close({ reason: "user_done" });
```

`window.*` is always allowed — no permission required.

## Errors

Every RPC returns a Promise that resolves with a structured response:

```ts
{ ok: true,  result: any }
{ ok: false, error: { code: string; message: string; details?: any } }
```

Common codes:

| Code | Meaning |
|---|---|
| `invalid_token` | JWT expired or wrong window — the SDK auto-refreshes most cases |
| `permission_denied` | `(ns, method)` not in `host_api`, or referenced `tool_id` not in allow-list |
| `invalid_arg` | Schema mismatch on RPC args |
| `not_found` | Window already closed; storage key missing; etc. |
| `agent_unavailable` | `tools.invoke` could not reach the user's Anna Agent |
| `bundle_not_ready` | (At `open_app_view` time) the version's bundle is still `draft` |
| `rate_limited` | Too many RPCs in flight |

Full namespace × method matrix and current implementation status: [App UI Host API](/developers/apps/app-ui-host-api).
