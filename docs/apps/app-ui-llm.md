---
title: "App UI LLM Integration"
description: "How the assistant summons, updates, and closes your app windows via LangChain tools and SSE events."
section: apps
slug: app-ui-llm
order: 15
updated: 2026-04-28
estimated_minutes: 4
category: "App UI"
---

When the user `#`mentions a `schema: 2` app whose manifest contains `ui.views`, three LangChain tools are auto-injected into the assistant's tool list for that turn:

| Tool | Purpose |
|---|---|
| `open_app_view(app_id, view?, payload?)` | Summon (or focus) a window |
| `update_app_view(window_uuid, title?, geometry?, runtime_state_patch?)` | Push state into an existing window |
| `close_app_view(window_uuid, reason?)` | Close a window |

The tools are **only** injected when at least one mentioned app actually has UI views — schema-1 apps don't pollute the tool list.

## Prompt injection

When the user mentions an app with UI views, the system prompt grows a block:

```xml
<user_mentioned_apps>
  <app slug="research-suite" name="Research Suite" version="0.4.1">
    <tagline>Plan, capture, and summarise web research.</tagline>
    <system_prompt_addendum>
      When the user asks to research, summon the workspace via
      open_app_view('research-suite').
    </system_prompt_addendum>
    <bundled_executas>
      <executa tool_id="tool-yourhandle-browser-…" />
    </bundled_executas>
    <ui_views>
      <view name="main"          title="Research Workspace" default="true"
            summary_template="Research session: {topic}" />
      <view name="chart_preview" title="Chart Preview" />
    </ui_views>
  </app>
</user_mentioned_apps>
```

The `<ui_views>` block tells the model exactly which `view` names are valid arguments to `open_app_view`.

## Tools in detail

### `open_app_view(app_id, view?, payload?)`

```python
open_app_view(
    app_id="research-suite",
    view="main",                       # omitted → default view
    payload={"topic": "ECM-related immune evasion"}
)
```

- Resolves the user's installed version of the app.
- If the version's UI bundle is not `bundle_ready`, returns `bundle_not_ready`.
- If `single_instance: true` and a window already exists, focuses it and merges `payload` into `entry_payload`.
- Otherwise creates a new `AnnaAppWindowSession`, mints a JWT, and broadcasts SSE `open_view`.
- Returns `{ window_uuid, status: "active", entry_payload, geometry }`.

### `update_app_view(window_uuid, ...)`

```python
update_app_view(
    window_uuid="…",
    title="Research: ECM evasion",
    runtime_state_patch={"progress": 0.6}
)
```

- Patches geometry/title/runtime_state shallow-merged with current values.
- A `runtime_state_patch` triggers an SSE `runtime_state_synced` after the merge.
- Setting only `title` triggers `title_changed`.
- Use this to stream progress from a long-running tool call into the window.

### `close_app_view(window_uuid, reason?)`

```python
close_app_view(window_uuid="…", reason="task_done")
```

- Sets `status = closed`; broadcasts `close_view`.
- Idempotent.

## Recommended chat ↔ window pattern

```
User:    @research-suite please dig into ECM-related immune evasion.

LLM →    open_app_view(app_id="research-suite", payload={"topic": "ECM"})
         (Window appears.)

LLM →    chat.append_artifact (from inside the iframe, NOT a tool the LLM calls)
         {"kind": "app_event", "summary": "Started research on ECM",
          "payload_ref": "windows/<wid>/runtime_state"}

iframe → tools.invoke(tool_id=browser, args={"url": "…"})
iframe → storage.set({key: "findings", value: [...]})

LLM →    update_app_view(window_uuid="…",
                         runtime_state_patch={"progress": 1.0, "status": "ready"})

LLM:     "I summarised five papers in the workspace — open it to read."
```

The iframe should **always** post a chat artifact when it produces something the user might want to refer back to (a finding, a chart, a draft). The `chat.append_artifact` call goes through the host RPC; the artifact card appears in the chat scrollback even after the window is closed.

## Full SSE event stream

`GET /api/v1/anna-apps/runtime/events/stream` (cookie-authenticated). Events are framed as standard SSE:

```
event: data_model.AnnaAppEvent
data: {"type":"data_model/AnnaAppEvent","kind":"open_view", … }

```

Kinds and payloads are listed in [App UI Windows](/developers/apps/app-ui-windows#cross-tab-cross-device-sync). Both your iframe (via the SDK) and other dashboard tabs subscribe to the same stream — that is how multi-device coherence works without you doing anything.

## Failure modes the assistant should know about

When `open_app_view` fails, the tool returns a structured error the model can reason about:

| `error.code` | What to tell the user |
|---|---|
| `app_not_installed` | Suggest installing it from the App Store |
| `bundle_not_ready` | The developer hasn't finalised the bundle for this version — the model should not retry |
| `version_not_published` | Same as above |
| `agent_unavailable` | The user's Anna Agent is offline; the window opens but tool calls inside will fail |
| `quota_exceeded` | Too many active windows for the user (rare) |

For developer-side and iframe-side errors, see [App UI Host API → Error codes](/developers/apps/app-ui-host-api#error-codes).
