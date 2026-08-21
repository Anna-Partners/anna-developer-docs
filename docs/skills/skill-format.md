---
title: "Skill Format"
description: "The frontmatter, metadata structure, and supporting files that make a Skill loadable."
section: skills
slug: skill-format
order: 2
updated: 2026-04-23
estimated_minutes: 6
---

A Skill is the declarative flavour of an [Executa](/developers/overview/concepts). Every Skill is a folder; its entry point is **`SKILL.md`** — markdown with YAML frontmatter, where one frontmatter key (`metadata`) carries a JSON blob describing execution mode and dependencies.

## Top-level frontmatter

```yaml
---
name: short-kebab-name
description: One-sentence description used at skill-discovery time.
metadata: {"matrix":{ ... }}
---
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Lowercase kebab-case; defaults to the parent directory name if omitted |
| `description` | string | yes | What the LLM uses to decide when to load the skill — write it as a search query the user might type |
| `metadata` | JSON | no | One-line JSON blob (see below) carrying executable metadata |

Top-level `version` / `author` are accepted but currently informational — versioning happens at publish time via the Executa version snapshot.

## The `metadata` blob

The skill loader parses `metadata` as JSON. If the JSON has a top-level `matrix`, `openclaw`, or `nexus` key (in that order), the value of that key is used as the actual structured metadata; otherwise the JSON is consumed directly. Real example from the bundled `chart-generator` skill:

```yaml
---
name: chart-generator
description: "Use matplotlib and seaborn to create publication-quality charts…"
metadata: {"matrix":{"emoji":"📈","execution_mode":"python","category_name":"data-analysis","requires":{"python_packages":["matplotlib","seaborn"]},"install":[{"id":"pip","kind":"pip","package":"matplotlib seaborn","label":"Install matplotlib & seaborn (pip)"}],"uninstall":[{"id":"pip","kind":"pip","command":"pip uninstall matplotlib seaborn","label":"Uninstall matplotlib & seaborn (pip)"}]}}
---
```

### Recognized fields under `matrix`

| Key | Type | Notes |
|---|---|---|
| `always` | boolean | Load this skill into every conversation (use sparingly — reserved for foundational tooling like `uv`) |
| `skill_key` | string | Override identifier (defaults to `name`) |
| `primary_env` | string | Required environment variable hint shown in onboarding |
| `emoji` | string | Display icon |
| `homepage` | string | Documentation link |
| `category_name` | string | Free-form group used by the Skill catalogue (`productivity`, `data-analysis`, `network`, `office`…) |
| `os` | array | Limit availability (`["macos", "linux", "windows"]`) |
| `execution_mode` | enum | `prompt` (default) / `bash` / `python` / `api` / `hybrid` |
| `parameters` | array | Optional input parameters declared like Executa tool parameters |
| `requires` | object | Dependency declarations (see below) |
| `install` | array | Install recipes (see below) |
| `uninstall` | array | Matching uninstall recipes |

### `requires`

Declare what the skill needs available at runtime. The agent surfaces missing requirements during onboarding:

```json
"requires": {
  "bins": ["jq"],                         // executables that MUST be on PATH
  "any_bins": ["uv", "curl"],             // satisfied by ANY one being present
  "env": ["GITHUB_TOKEN"],                // required environment variables
  "config": ["github.host"],              // required config keys
  "python_packages": ["matplotlib"]       // pip-installable packages
}
```

### `install` / `uninstall`

A list of recipes; the agent picks the first one matching the host OS and an available installer.

```json
"install": [
  {"id": "brew",  "kind": "brew",  "formula": "jq",  "bins": ["jq"], "os": ["macos"],  "label": "Install jq (brew)"},
  {"id": "apt",   "kind": "apt",   "package": "jq",                   "os": ["linux"],  "label": "Install jq (apt)"},
  {"id": "pip",   "kind": "pip",   "package": "matplotlib seaborn",                     "label": "Install via pip"}
]
```

| Field | Notes |
|---|---|
| `id` | Stable identifier within the recipe list |
| `kind` | One of `brew`, `pip`, `apt`, `npm`, `go`, `uv`, `download`; uninstall recipes also accept `shell` |
| `formula` / `package` / `command` | Provided depending on `kind`; `command` is a raw shell command for `shell` / `download` |
| `bins` | Executables this recipe makes available (used to verify success) |
| `os` | Restrict the recipe to specific OSes |
| `label` | UI string |

Uninstall recipes mirror the install side and may use a `command` to run a custom shell uninstall.

## Body conventions

When the LLM picks the skill, the runtime returns the body of `SKILL.md` to it (preceded by an execution-mode hint and any declared dependencies). It is not a script the runtime executes — it's instructions the LLM reads. Treat it as prompt engineering:

1. **Lead with intent.** First paragraph: what the skill does, plainly.
2. **Be explicit about output format** when in `prompt` mode.
3. **Provide one or two inline examples**; point to `examples/` for longer ones.
4. **For `bash` / `python` modes**, fence ready-to-run commands in code blocks. The LLM will copy those commands into a follow-up call to the agent's `exec` / `command` tool to run them in the workspace sandbox — the skill loader itself does not execute fenced blocks.
5. **Reference supporting files by relative path** — `templates/report.md.tpl`.

> [!TIP]
> Ambiguity in the body becomes ambiguity in the output. When in doubt, add a constraint.

## Supporting files

- `examples/` — input/output pairs the model can imitate.
- `templates/` — file scaffolds with placeholders.
- `data/` — small reference datasets (lookup tables, glossaries).
- `scripts/` — helper scripts the body references.

No manifest is needed for these — reference them by relative path from the body.

## Reference

The platform ships bundled skills you can study (chart-generator, csv-data-tools, jq, curl, pdf-tools, postgres-client, …) — open one in the Skill Hub and copy its `SKILL.md` structure.
