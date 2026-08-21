---
title: "Concepts: Executa (Tools + Skills) and Apps"
description: "One umbrella, two flavours, and the App that bundles them. The 4-minute version."
section: overview
slug: concepts
order: 2
updated: 2026-04-23
estimated_minutes: 4
---

Anna exposes two extension surfaces:

- **Executa** — a single first-class capability the agent can call. An Executa is either a **Tool** (an executable process speaking JSON-RPC) or a **Skill** (a declarative `SKILL.md` recipe). Both share the same registry, draft/version/visibility lifecycle, and developer Console.
- **Anna App** — a curated bundle of one or more Executas (tools + skills) plus a prompt addendum, published to the App Store and `#mention`-able by the user.

> [!IMPORTANT]
> When this hub says "publish an Executa" or "Executa Hub", it means *either a Tool or a Skill*. The flavour is just an `executa_type` field on the record (`tool` or `skill`).

## At a glance

| Aspect | **Executa: Tool** | **Executa: Skill** | **Anna App** |
|---|---|---|---|
| **Form** | A standalone process speaking JSON-RPC | A folder containing `SKILL.md` | A manifest bundling Executas + prompt |
| **Language** | Any (Python, Node, Go, Rust, …) | Markdown (+ optional supporting files) | JSON manifest + linked Executa references |
| **How the agent uses it** | Called directly as a callable capability with a typed schema | Listed as a recipe the agent can consult on demand; the recipe text guides the agent, which then uses its built-in capabilities to act | Activated when the user `#mentions` it; brings its bundled Executas + prompt addendum into the turn |
| **Best for** | Side effects, network, file system, native APIs | Declarative recipes, prompts-as-code, reusable runbooks | Curated end-user experiences |
| **Distribution** | Source or signed binary in the Executa Hub | Markdown payload in the Executa Hub | The Anna App Store |

## Tools (executable Executa)

A **Tool** is the lowest-level Executa. You write a small program — in any language — that:

1. Reads JSON-RPC requests from stdin.
2. Implements at least two methods: `describe` (return your manifest) and `invoke` (run a tool).
3. Writes JSON-RPC responses to stdout. Logs go to stderr.

That's it. There is no SDK to learn and no runtime to embed. The protocol is documented in [Protocol Spec](/developers/tools/executa-protocol).

> [!TIP]
> If you can write a CLI in your favourite language, you can ship a Tool.

## Skills (declarative Executa)

A **Skill** is a folder containing a `SKILL.md` — a recipe written in Markdown. Skills are not callable capabilities of their own; instead, the agent is told *what skills exist* and *what each one is for*, and consults a skill's full body only when it decides the skill is relevant. The body then guides the agent, which carries out any actions using its built-in capabilities.

This means a Skill is essentially **prompt-as-code**: declarative knowledge the agent can pull in on demand, not a process that runs on its own.

Skills are the right choice when:

- The capability is mostly prompt + light orchestration (no compiled code of your own).
- You want to ship and version capabilities without building a binary.
- You want non-engineers to author plugins.

See [What is a Skill](/developers/skills/skill-intro) and [SKILL.md Format](/developers/skills/skill-format).

## Anna Apps

An **Anna App** is a curated bundle published to the App Store. A user installs it once; thereafter they can `#mention` the App in chat and Anna will:

- Activate **all** the App's required Executas (tools and/or skills) for that turn.
- Inject the App's `system_prompt_addendum` into the system prompt.
- Optionally wrap the user message with a prefix template.

Apps are how a domain expert ships an end-user experience — "Weekly Review Coach", "GitHub Triage Buddy" — without forcing each user to install a dozen separate Executas by hand.

## How they relate

```
+---------------------------+
|        Anna App           |  manifest + prompt addendum
|  (published in App Store) |
+-------------+-------------+
              │ bundles
              ▼
+---------------------------+        +---------------------------+
|   Executa (type: tool)    |  …or…  |   Executa (type: skill)   |
|   process + JSON-RPC      |        |   SKILL.md + metadata     |
+---------------------------+        +---------------------------+
              \\                                  /
               \\________ Executa Hub ___________/
                  (one catalogue, one wizard,
                   one draft → version flow)
```

You can ship a single Tool and stop there. You can ship a single Skill without ever touching JSON-RPC. You only need an App when you want to package an end-user experience.

## Next

- [Architecture & Lifecycle](/developers/overview/architecture)
- [Choosing What to Build](/developers/overview/choosing)
