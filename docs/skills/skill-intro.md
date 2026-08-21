---
title: "What is a Skill"
description: "Skills are the declarative flavour of Executa: a folder of markdown that Anna loads on demand and turns into a LangChain tool."
section: skills
slug: skill-intro
order: 1
updated: 2026-04-23
estimated_minutes: 4
---

A **Skill** is the *declarative* flavour of [Executa](/developers/overview/concepts). It's a folder containing a `SKILL.md` plus optional supporting files (examples, templates, scripts, datasets) that teaches Anna *how* to do something. At runtime the loader registers each skill as a LangChain `@tool`; when the LLM picks it, the tool returns the skill's markdown body — along with an execution-mode hint and any declared dependencies — and the agent then uses its built-in `exec` / `command` tools to run any bash or Python the body recommends.

> [!NOTE]
> Skills do **not** execute code by themselves. The skill body is delivered to the LLM as instructions; running anything is the agent's job, via its existing execution tools. That is why `execution_mode` is a *hint* ("this skill is best run via bash") and not an interpreter selection.

## When to ship a Skill (vs. a Tool Executa)

Both are Executas — same Hub, same draft → version → visibility lifecycle. The difference is the *shape* of the artifact.

| Ship a **Skill** when… | Ship a **Tool** when… |
|---|---|
| You want to teach Anna a process, style, or workflow | You need to maintain a long-running process with credentials |
| The work is mostly markdown + commands the agent can run via `exec` | You need bidirectional JSON-RPC, streaming, or complex SDK integrations |
| You want users to read / fork / customise the body | You want a black-box contract behind a stable manifest |

The two compose well: a `chart-generator` Skill teaches Anna *when and how* to render a chart, and may itself recommend calling a `pandas-tools` Tool Executa for heavier data wrangling.

## Anatomy

```
my-skill/
├── SKILL.md            # required — frontmatter + body
├── examples/
│   ├── input-1.md
│   └── output-1.md
├── templates/
│   └── report.md.tpl
└── README.md           # optional — for humans browsing the source
```

## A minimal SKILL.md

```markdown
---
name: meeting-summary
description: Turn raw meeting notes into a structured summary with decisions, action items, and open questions.
metadata: {"matrix":{"emoji":"📝","execution_mode":"prompt","category_name":"productivity"}}
---

# Meeting Summary Skill

When the user provides raw meeting notes, produce a summary with three sections:

## Decisions
- Bullet list of every decision the group made.

## Action Items
- `[ ] Owner — task — due date`

## Open Questions
- Bullet list of unresolved items.

If owner or due date is missing, write `?` and surface it as an open question.
```

The body is markdown that the LLM receives when it calls the skill. Frontmatter has two required keys (`name`, `description`) and one structured `metadata` blob — see [Skill format](/developers/skills/skill-format).

## Where to next

- **Format spec** — [Skill format](/developers/skills/skill-format).
- **Run locally** — [Local development](/developers/skills/skill-local).
- **Publish** — [Publishing](/developers/skills/skill-publish).
