---
title: "Architecture & Lifecycle"
description: "How an Executa call flows through Anna, from chat input to response."
section: overview
slug: architecture
order: 3
updated: 2026-04-23
estimated_minutes: 5
---

This page is a map. If you've read [Concepts](/developers/overview/concepts) and you want to understand where your code runs, what it can see, and when it gets killed — start here.

## The runtime

Anna is composed of:

- A **frontend** (web/desktop/mobile) that drives chat.
- A **gateway / API** (Nexus) that stores state, routes turns, and orchestrates tool calls.
- A **runtime** that hosts the LLM session and the tool executor (`matrix`).
- A **NATS** message bus for streaming, fan-out, and event delivery.
- An **Executa Hub** registry that catalogues installable Executas (both Tools and Skills).

Executas — both Tool and Skill flavours — are activated **inside the runtime**, on the same host. Apps don't run anywhere themselves; they're metadata + references that the runtime reads when the user `#mentions` them.

## Lifecycle of a Tool Executa call

1. **User turn arrives** — the runtime builds a system prompt, including any `@`-mentioned Executas and any `#`-mentioned Apps' contributions (system_prompt_addendum, required Executas).
2. **LLM emits a tool call** — for example `weather.lookup({ city: "Tokyo" })`.
3. **Runtime spawns the plugin process** if it isn't already warm. The binary lives wherever the user installed it; the platform passes credentials via environment variables (see [Credentials & OAuth](/developers/tools/executa-credentials)).
4. **Runtime sends `invoke`** as a single JSON-RPC line to the plugin's stdin.
5. **Plugin runs** — does its work, returns a JSON-RPC response on stdout. stderr is captured for debugging only.
6. **Runtime parses the response** and returns it to the LLM as a tool result.
7. **Process disposition**: short-lived plugins exit immediately; long-lived plugins (declared in the manifest) stay warm and serve the next call.

> [!NOTE]
> The runtime treats your stdout as a strict transport. Anything that isn't a valid JSON-RPC frame will fail the call. Always direct logs to stderr.

## Lifecycle of a Skill Executa call

Skills don't spawn processes of their own. The runtime discovers `SKILL.md` files at agent start (or loads them from the Executa record in the database), parses the frontmatter, and registers each skill as a LangChain `@tool`. When the LLM picks the skill, the tool **returns the skill's markdown body to the LLM**, decorated with an execution-mode hint and any declared dependencies.

The skill itself does *not* execute bash or Python directly. If the body contains a fenced bash/python block, the LLM reads it and — in a follow-up turn — calls the agent's built-in `exec` / `command` tools to run it inside the workspace sandbox. That keeps Skills fast and safe and lets the same skill be used from any execution backend.

## Lifecycle of an Anna App `#mention`

1. The user types `#weekly-review` in chat. The frontend resolves it against the user's installed apps and includes the `app_id` in the request.
2. The runtime loads the App's manifest, expands `required_executas` into active tools for the turn, and appends `system_prompt_addendum` (XML-fenced) to the system prompt.
3. From here, the lifecycle is identical to a normal turn — the LLM sees one or more new tools and may choose to call them.

## Concurrency & isolation

- Each Executa call runs in its **own process**. There is no shared state with the runtime beyond stdin/stdout and environment variables.
- Multiple plugins can be invoked **in parallel** within a single turn if the LLM emits parallel tool calls.
- The runtime applies a per-call timeout (default 30s; long-running plugins can declare a different limit in their manifest — see [Manifest Reference](/developers/apps/app-manifest)).

## What you can rely on

- Stdin / stdout / stderr.
- A working temp directory (`$TMPDIR`).
- Environment variables for credentials, declared in your manifest.
- Outbound network (subject to user/admin policy).

## What you can't rely on

- Persistent disk between calls (use the user's data directory only when explicitly granted).
- A specific operating system. Ship a single binary per platform if you depend on native code.
- Inter-tool messaging. Tools shouldn't call each other directly — let the LLM coordinate.
