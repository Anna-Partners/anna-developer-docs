---
title: "Welcome to the Anna Developer Hub"
description: "What you can build for Anna, and how to find your way around."
section: overview
slug: welcome
order: 1
updated: 2026-04-23
estimated_minutes: 3
---

Anna is a universal AI agent — and almost everything she does at runtime is something a third-party developer can extend, replace, or compose.

This hub is the single source of truth for that work. It covers the two building blocks you can ship — **Executa** (the umbrella for both **Tools** and **Skills**) and **Anna Apps** — and walks you from "hello world" to a published listing in the App Store.

> [!IMPORTANT]
> **Executa = Tools + Skills.** They are two flavours of the same first-class object in Anna's catalogue, distribution pipeline, and developer Console. A *Tool* is an executable plugin process; a *Skill* is a declarative `SKILL.md` recipe. Both are stored as `Executa` records, both go through the same draft → version → visibility lifecycle, and both can be bundled into Anna Apps.

## Where to start

- **New to Anna?** Read [Concepts: Executa and Apps](/developers/overview/concepts) first. It's a 4-minute primer that prevents 90% of confusion.
- **Want to ship a Tool today?** Jump to a quickstart: [Python](/developers/tools/executa-python), [Node.js](/developers/tools/executa-nodejs), or [Go](/developers/tools/executa-go).
- **Prefer a declarative recipe?** Start with [What is a Skill](/developers/skills/skill-intro).
- **Building a curated experience?** Start with [What is an Anna App](/developers/apps/app-intro) and the [Manifest Reference](/developers/apps/app-manifest).

## What this hub is not

- It is **not** the Developer Console. The Console (at `/developer`) is where verified developers manage their own Executas and Apps once published; this hub is the public learning resource.
- It is **not** the API reference for end-user features. For Anna's user-facing docs see [docs.anna.partners](https://docs.anna.partners).

## Stay in the loop

- **Examples**: [`anna-executa-examples`](https://github.com/whtcjdtc2007/anna-executa-examples) — runnable Tool plugins in Python, Node.js, and Go.
- **Forum**: [forum.anna.partners](https://forum.anna.partners) — proposals, RFCs, show-and-tell.
- **Changelog**: linked from the Reference section as we ship platform updates.
