---
title: "Host API vs Executa Tool — When to Use Which"
description: "Anna apps can reach for the platform's host API or for a custom Executa tool to accomplish similar-looking tasks. They are not equivalent — this guide explains the real differences and gives a decision framework."
section: apps
slug: host-api-vs-executa
order: 24
updated: 2026-05-27
estimated_minutes: 8
---

## The trap: they look like equivalent menus

At first glance the **Host API** (`anna.llm`, `anna.agent`, `anna.storage`, `anna.image`, `anna.upload`) and **Executa tools** (custom plugin processes invoked via `anna.tools.invoke`) appear to offer overlapping capabilities. Both can "call an LLM", both can "store data", both can "talk to external systems". So which one should an Anna App reach for?

**They are not actually peers.** Treating them as a free choice between two equivalent menus is the most common architectural mistake in Anna App design. They differ on identity, billing, lifecycle, trust boundary, and the platform contract — and picking the wrong one silently breaks quota accounting, cross-device sync, or maintainability.

## Side-by-side

| Dimension | Host API (`anna.llm`, `anna.storage`, …) | Executa Tool (`anna.tools.invoke`) |
|---|---|---|
| **Where the code lives** | Inside nexus / dispatcher (the platform) | A process the developer wrote (Python/Node/Go/binary) |
| **Identity** | Automatically scoped to the signed-in user via `app_session_token` / `storage_token` | The process has no user identity — it must reverse-RPC back to the host API to touch user-scoped resources |
| **Quota & billing** | Counts against the user's unified Anna quota (see *matrix pricing baseline*) | Developer-paid (your own API keys, your own infra) |
| **Audit / compliance** | Centralised in nexus logs | Black box on the developer side |
| **Cross-device** | Yes — server-backed | No — local to whichever machine / runner spawned the process |
| **Cold start** | ~0 ms (the dispatcher is already running in-process) | Tens to hundreds of milliseconds (process spawn + `describe` handshake) |
| **State** | Stateless — every call independent | Can hold long-lived state (a warm model client, a DB connection pool, an open file handle) |
| **Reach** | Whatever the platform has abstracted | Local filesystem, GPU, private SDKs, third-party systems |
| **Versioning** | Evolves with the dispatcher (schema pinned at `dispatcher_version=0.10.0`, tracking the `anna-app-schema` version) | Developer bumps it independently |
| **Permission model** | User grants per-namespace via `manifest.permissions` | Once installed, the executa is trusted wholesale |
| **Platform reach** | Web, Desktop, Mobile — all the same wire contract | Only where an Anna runtime is installed |

## The key clarification: Executa is not a substitute for the host API — it is an extension point for it

The most consequential misreading of the surface is "I can do LLM either way — let me pick one." The real design treats them as **nested**, not exclusive:

```
iframe (UI / orchestration)
   ├── anna.llm.complete(...)          ← Host API (direct)
   ├── anna.storage.set(...)            ← Host API (direct)
   └── anna.tools.invoke("rerank", ...) ← Executa
                  │
                  └── reverse-RPC from inside the executa:
                       anna.llm.complete(...)   ← still the Host API
                       anna.storage.get(...)    ← user identity inherited
```

So the right question is **not** "host API or executa?" — it's "does this piece of logic need to run in a separate process?" That is the real boundary between iframe code and an executa. Once you decide to move logic into an executa, the executa itself should still call back into the host API for any user-scoped work, rather than reimplementing those capabilities (and silently bypassing identity, quota, and audit).

## Decision framework

**Default to the Host API.** Only switch to an Executa when at least one of these hard constraints applies:

1. **Heavy CPU / memory work** — embeddings, vector search, local image processing, PDF parsing, numpy / PyTorch. The iframe main thread and per-call host RPC are both wrong places for these.
2. **Long-lived session state** — keep a model client, a database connection pool, a scraper session, or a cached index alive across many invocations. Host calls are stateless by contract.
3. **Capabilities the platform has not abstracted** — local filesystem, OS tooling (`git`, `ffmpeg`), intranet APIs, specific hardware. The host API simply does not expose these.
4. **Developer-owned secrets** — you are integrating a third-party SaaS using *your* API key (not the end user's). The key must not reach the iframe (browser context can be inspected); putting the integration in an executa keeps it server-side / process-side.
5. **Agent-orchestrable tools** — you want `anna.agent.session.run` to decide when to call this capability. That is exactly what executas are designed to be.

If none of the above applies, **use the host API**. You inherit maintenance, multi-platform reach, audit, and quota accounting for free.

## Anti-patterns (each one tempting, each one a trap)

| Anti-pattern | Why it bites |
|---|---|
| Executa `import openai` calling OpenAI directly | The end user's chosen model / quota / billing is bypassed. The bill lands on the developer. When the user switches models in their Anna settings, your app silently ignores it. |
| Executa writing "user data" to a local JSON file | Lost on device swap, reinstall, or uninstall. Will never sync between Web / Desktop / Mobile. |
| Wrapping `anna.upload.inline` in an executa that just forwards | One extra stdio hop plus a reverse-RPC for no gain. Pure overhead. |
| Making "translate this sentence" or "generate one image" into an executa | The cold-start cost exceeds the actual work. The user feels lag for no reason. |
| Running algorithms inside the iframe (when they belong in an executa) | Blocks the UI thread; the app appears frozen during work. |

## Practical guidance for Anna App authors

1. **The iframe is UI + orchestration.** It calls the host API for user-identity-bound operations (LLM, storage, image, upload), and it calls executas to trigger custom heavy logic.
2. **The host API is the default.** If a capability exists there, use it — you get platform maintenance, cross-platform behaviour, and audit / quota for free.
3. **Put only "must run locally" code in an executa.** And when an executa needs user-scoped capabilities, it should reverse-RPC back into the host API — never bring its own OpenAI key or roll its own storage layer.
4. **Always use APS for persistence** (see `local-dev` `--storage aps` to exercise the real backend in local development). Do not fake persistence by writing files inside an executa.
5. **Quick test:** identity / billing / sync / cross-device → host API; CPU / state / private keys / system access → executa.

## In one sentence

**The Host API is the default path; Executa is an escape hatch — and the escape hatch should still reverse-RPC back through the Host API, not bypass it.**
