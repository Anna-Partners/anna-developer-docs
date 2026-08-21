---
title: "Local Development"
description: "Build and iterate on a skill on your own machine before publishing."
section: skills
slug: skill-local
order: 3
updated: 2026-04-23
estimated_minutes: 5
---

The fastest iteration loop is: **drop the folder into a discoverable skills directory → reload the agent → trigger the skill → revise.**

## 1. Where the loader looks

The Nexus skill loader resolves the **bundled skills directory** by trying these locations in order and using the first one that exists:

| Order | Source | Path | Purpose |
|---|---|---|---|
| 1 | Env override | `$MATRIX_SKILLS_DIR` | Point at any folder of skills (recommended for development) |
| 2 | In-tree bundled | `<repo>/skills/` | Built-in skills shipped with Nexus (e.g. `chart-generator`, `jq`, `curl`) |
| 3 | Package bundled | ships inside the platform package | Internal fallback |

In addition, **workspace skills** under `<workspace>/skills/` are loaded separately by `load_workspace_skills(workspace_path)` and merged on top of the bundled set (workspace entries win on name collision via `merge_skills`).

Each immediate subdirectory containing a `SKILL.md` is a skill (the loader recursively walks the tree looking for `SKILL.md` files). On first access the registry builds an index of skill name → file path; the body is parsed lazily the first time a given skill is requested.

```bash
export MATRIX_SKILLS_DIR=~/dev/anna-skills
mkdir -p "$MATRIX_SKILLS_DIR/my-skill"
$EDITOR "$MATRIX_SKILLS_DIR/my-skill/SKILL.md"
```

Restart the agent (or hit the reload endpoint) and trigger the skill by asking Anna something matching its frontmatter `description`.

## 2. Pick the execution mode

The `metadata.matrix.execution_mode` field is a **hint** the runtime injects above the skill body so the LLM knows how the skill is intended to be run. The skill loader itself does not execute anything — the LLM uses the hint to decide which built-in agent tool (typically `exec` / `command`) to call next.

| Mode | Hint shown to the LLM |
|---|---|
| `prompt` (default) | "Follow the instructions in the body" — no execution implied |
| `bash` | "Run the example commands via `exec` (bash/shell)" |
| `python` | "Run the Python via `exec`, preferring `uv run --with <pkg> python script.py`" |
| `api` | "This skill describes an HTTP call — use `exec` to run `curl` or similar" |
| `hybrid` | "Mix bash and Python as the body suggests" |

For `bash` / `python` skills, declare any required `bins` / `python_packages` in `requires` plus matching `install` recipes so onboarding can ensure dependencies are present before the agent tries to run them. When any loaded skill is `python` mode, the runtime additionally injects a section into the system prompt instructing the agent to prefer `uv` over the system `pip` (see `src/skills/converter.py`).

## 3. Smoke-test checklist

- [ ] The frontmatter `description` is the kind of question a user would actually type. (If your skill never loads, this is almost always the cause.)
- [ ] Output matches your spec on three different inputs.
- [ ] Edge cases (empty input, malformed input) degrade gracefully.
- [ ] All `requires` items resolve on a clean machine, or the install recipes succeed.
- [ ] Supporting files referenced from the body actually exist at those paths.

## chart-generator walkthrough

A real bundled skill looks like this:

```
skills/chart-generator/
├── SKILL.md
└── examples/
```

Frontmatter (truncated):

```yaml
---
name: chart-generator
description: "Use matplotlib and seaborn to create publication-quality charts…"
metadata: {"matrix":{"emoji":"📈","execution_mode":"python","category_name":"data-analysis","requires":{"python_packages":["matplotlib","seaborn"]},"install":[{"id":"pip","kind":"pip","package":"matplotlib seaborn"}]}}
---
```

The body teaches Anna to:

1. Inspect the user's data.
2. Suggest the most appropriate chart type.
3. Emit a Python snippet that calls `matplotlib` / `seaborn` to render the chart.
4. Save the output as `chart.png` (or SVG/PDF) in the workspace.

When the LLM calls the skill, the runtime returns the body to it. The LLM then issues an `exec` call running `uv run --with matplotlib --with seaborn python script.py` (or installs the packages via the declared `install` recipe first). Browse the bundled `chart-generator` skill in the Skill Hub for the live source.

## Next

- **Publish your skill** — [Publishing](/developers/skills/skill-publish).
