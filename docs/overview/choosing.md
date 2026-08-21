---
title: "Choosing What to Build"
description: "Tool, Skill, or App? A short decision guide."
section: overview
slug: choosing
order: 4
updated: 2026-04-23
estimated_minutes: 3
---

You usually know what you want Anna to do. The question is which surface to ship.

> [!NOTE]
> Tools and Skills are the two flavours of **Executa**. Picking between them is choosing the *shape* of an Executa, not picking a different system. See [Concepts](/developers/overview/concepts).

## Decision shortcut

> [!TIP]
> **Need to call a network API, run a binary, hold credentials, or stream results?** → Build a **Tool** Executa.
>
> **Want to encode a recipe, runbook, or prompts-as-code that the agent reads and acts on?** → Build a **Skill** Executa.
>
> **Want to package an end-user experience and have it appear in the App Store?** → Build an **Anna App** that bundles one or more Executas.

## Worked examples

| You want to… | Ship a… | Why |
|---|---|---|
| Query the GitHub API for issues | **Tool** Executa | Auth + network = process-level concern |
| Convert a CSV to a tidy chart | **Skill** Executa (e.g. `chart-generator`) | Mostly matplotlib glue the agent runs via `exec` |
| Bundle five Executas into a "Marketing Researcher" experience | **App** that bundles those Executas | Discovery + installability is the whole product |
| Add a `pdf.summarize` capability for everyone in the org | **Tool** Executa (or wrap in an App for a listing) | New capability, may need binary deps |
| Teach Anna a new "code review" workflow with prompts only | **Skill** Executa | Pure declarative; no native code |

## Cost / friction tradeoff

| | Tool Executa | Skill Executa | Anna App |
|---|---|---|---|
| Time to first run | medium (write + spawn a process) | low (one markdown file) | adds a few minutes on top of underlying Executas |
| Distribution effort | medium (binary builds, registry submission) | low (markdown payload) | high (review, listing assets) |
| Audience | technical | technical & non-engineer | end users |

Note that Tools *and* Skills go through the same Executa Hub publish flow (drafts, versions, visibility) — the cost difference above is in *authoring*, not in distribution mechanics.

## When in doubt

Build the smallest unit that solves your problem first, then promote upward:

1. Start with a **Skill** Executa to validate the workflow.
2. If you need real I/O, credentials, or streaming, extract that part into a **Tool** Executa.
3. When you're ready to publish to end users, wrap everything in an **App**.
