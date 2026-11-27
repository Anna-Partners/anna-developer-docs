---
title: "Durable Conversations"
description: "Give your App the user's long-lived conversations — memory, persisted history and the full agent — with the conversation.* Host API."
section: apps
slug: app-ui-conversation
order: 15
updated: 2026-11-27
estimated_minutes: 8
category: "App UI"
---

The `conversation.*` Host API gives an App **durable conversations**: long-lived threads that carry the user's memory and persona, keep their history on the platform, and run the same agent the user talks to everywhere else in Anna — with every tool that agent has, including the ones on the user's own machine.

It is the API Anna's own Chat App is built on, and it has no first-party privilege: any App that declares it gets the same surface.

## Conversations vs. agent sessions

| | `conversation.*` | [`agent.session.*`](/developers/apps/llm-and-agent) |
|---|---|---|
| Lifetime | Durable — until the user deletes it | A working session: idle 30 min, at most 24 h |
| History | Persisted by the platform, paged with `conversation.messages` | Session-scoped |
| Memory & persona | The user's own (except Zen conversations) | None |
| Tools | The user's full agent tool set | The set you request, limited by `ui.host_api.agent.tools` |
| Use it for | A chat surface the user comes back to | A bounded task your App drives |

If your App needs an agent to do a job and hand back a result, use `agent.session.*`. Use `conversation.*` only when the conversation itself is the product.

## Declare the capability

A conversation reaches the user's memory and their local tools, so `conversation.*` is one of the five [capability declarations](/developers/apps/app-manifest#capability-declarations):

```jsonc
{
  "schema": 4,
  "ui": {
    "bundle": { "format": "static-spa", "entry": "index.html", "external_origins": [] },
    "host_api": { "conversation": true }
  }
}
```

Calls without the declaration fail with `conversation_not_declared`. The declaration needs `@anna-ai/app-schema` ≥ 0.36.0 and `@anna-ai/cli` ≥ 0.1.68 to validate, and `@anna-ai/app-runtime` ≥ 0.29.0 in your bundle. A host older than dispatcher 0.36.0 answers `unknown_method`.

## Isolation

Conversations belong to **(user, app)**. Your App lists, reads and writes only the conversations it created; a `conversation_uuid` that belongs to another App answers `not_found`, exactly like one that does not exist.

One App per deployment is the **default conversation App** (an administrator setting — a role, not a privilege). It shares its conversations with the platform's REST clients, so messages a user sends from the mobile app or through an API key appear in it. Every other App gets its own isolated set.

## Methods

A `Conversation` carries at least:

```ts
{
  uuid: string;
  name: string;
  is_default: boolean;      // the one conversation that always exists
  is_zen: boolean;          // minimal system prompt, no memory / persona
  is_pinned: boolean;
  is_auto_named: boolean;
  override_model: string | null;
  thinking: boolean | { enabled: boolean; effort?: string } | null;
  pinned_agent_id: string | null;
  pinned_mentions: object;  // sticky @ Executa / # App pins
  last_active_at: string | null;
  created_at: string;
  updated_at: string;
}
```

| method | args | result |
|---|---|---|
| `conversation.list` | `{}` | `{ conversations: Conversation[] }` — creates the default conversation (`is_default`) first if it does not exist |
| `conversation.create` | `{ name?, zen?, override_model? }` | `Conversation` |
| `conversation.update` | `{ conversation_uuid, name?, is_pinned?, override_model?, thinking?, pinned_agent_id?, pinned_mentions? }` | `Conversation`. An empty string clears `override_model` / `pinned_agent_id`; an empty object clears `thinking` |
| `conversation.delete` | `{ conversation_uuid }` | `{ deleted: true }`. The default conversation cannot be deleted (`invalid_arg`) |
| `conversation.messages` | `{ conversation_uuid, limit?, after_id? }` | `{ messages, … }` — the persisted history. `limit` 1–500 (default 200); `after_id` returns only messages with a greater id. Attachment URLs are re-signed on every call |
| `conversation.send` | `{ conversation_uuid, message, attachments?, executa_ids?, app_ids?, mention_modes?, thinking? }` | `{ task_id, stream_id }` — see [Sending a message](#sending-a-message) |
| `conversation.status` | `{ conversation_uuid }` | `{ task, stream_id }` — `task` is `null` when idle |
| `conversation.cancel` | `{ conversation_uuid, task_id, reason? }` | Stops the running task |
| `conversation.modify` | `{ conversation_uuid, task_id, instruction }` | Sends a correction to the running task; the agent applies it at its next checkpoint |
| `conversation.options` | `{}` | `{ models, executas, agents, settings }` — what a composer needs: chat models, the user's installed Executas (for `@`), their Agents, and `preferred_model` / `thinking_default` / `sandbox_enabled` / `sandbox_path` |

Notes:

- The model is a property of the conversation. Set it with `conversation.update { override_model }`; `conversation.send` takes no model.
- When a conversation has a `pinned_agent_id`, `conversation.send` dispatches to that Agent. It must be one of the user's own Agents, otherwise `invalid_arg`.
- A new conversation is named automatically after its first message. Poll `conversation.list` to pick the name up.
- `message` may be empty when `attachments` is not. Upload files with [`upload.*`](/developers/apps/app-ui-host-api) and pass each one as `{ type: "<MIME type>", url }`.

## Sending a message

`conversation.send` starts a run and returns as soon as it is queued. The reply arrives as stream frames, which the SDK exposes as an async iterator:

```js
import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const anna = await AnnaAppRuntime.connect();

const { conversations } = await anna.conversation.list();
const main = conversations.find((c) => c.is_default);

const stream = anna.conversation.send({
  conversation_uuid: main.uuid,
  message: "Summarise my notes from yesterday",
});

const run = await stream.ready;   // { task_id, stream_id }, or null if the send was rejected

let text = "";
for await (const frame of stream) {
  if (frame.event === "error") {
    console.error(frame.code, frame.message);      // stream-level failure
  } else if (frame.error) {
    console.error(frame.error_type, frame.error);  // failure inside the run
  } else if (frame.choices) {
    text += frame.choices[0]?.delta?.content ?? "";
  }
}
```

What to know about the stream:

- **One run per conversation at a time.** While a run is active, offer *stop* (`conversation.cancel`) and *correct* (`conversation.modify`) instead of a second send.
- **Two error shapes.** `{ event: "error", code, message }` comes from the stream itself (the send was rejected, the run timed out in the queue). `{ event: "sse", error, error_type }` comes from inside the run. Handle both.
- **Status frames are optional.** `queued`, `started` and `keepalive` may not arrive; never wait for one before showing progress.
- **A rejected send has one error path.** If the request is refused before it is queued — no quota, unknown conversation — `stream.ready` resolves to `null` and the stream yields a single `error` frame, then ends.
- **Treat persisted history as the truth.** After a run that errored, was cancelled or was recovered, reload `conversation.messages`.

## Recovering a run

A run continues on the platform when your window reloads or the network drops. When you open a conversation, ask where it stands:

```js
const { task, stream_id } = await anna.conversation.status({ conversation_uuid });

if (task && stream_id) {
  // Replays the stream from the first frame and follows it live.
  const stream = anna.conversation.attach({ stream_id, task_id: task.task_id });
  for await (const frame of stream) { /* render as above */ }
} else if (task) {
  // Running, but not attachable: poll, then reload the history.
}
```

| `task` | `stream_id` | Meaning | What to do |
|---|---|---|---|
| `null` | — | Idle | Show the history |
| running | set | A run your App can follow | `anna.conversation.attach(...)` — frames are de-duplicated by sequence number |
| running | `null` | Started outside the Host API (REST, a voice call), or older than one hour | Show "running", poll `conversation.status` every few seconds, reload `conversation.messages` when it ends |

## Voice

A realtime [audio session](/developers/apps/app-ui-audio-session) can speak with a conversation: open it with `anna.audio.session({ llm: "conversation", conversation_uuid })`. Each spoken turn is persisted in that conversation. Voice turns are not attachable — while a call is active `conversation.status` reports a running task without a `stream_id`. Details: [Talking to a durable conversation](/developers/apps/app-ui-audio-session#talking-to-a-durable-conversation).

## Local development

`anna-app dev` forwards `conversation.*` to the real platform when you are logged in, so you develop against the real agent and the frames your App receives are the ones production sends. The conversations you see follow the same isolation rule as production: your App's own set, or the user's main conversations if your App is the deployment's default conversation App.

For offline work, `--mock-llm <fixture>` replays canned responses; a `conversation.send` fixture row may carry an `events` array that is played back as stream frames. See [Local Development](/developers/apps/local-dev).

## Errors

| code | when |
|---|---|
| `conversation_not_declared` | The manifest does not set `ui.host_api.conversation: true` |
| `not_found` | Unknown `conversation_uuid` or `task_id`, or one that belongs to another App or user |
| `invalid_arg` | Missing or malformed argument; a `pinned_agent_id` that is not the user's Agent; a send with neither text nor attachments |
| `quota_exhausted` | The user has no quota left for the run |
| `rate_limited` | Too many requests |
| `unavailable` | The platform cannot queue the run right now — retry |

Usage is billed to the installing user at the same rate as their other conversations.
