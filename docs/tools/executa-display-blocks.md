---
title: "Display Blocks (verbatim output)"
description: "Declare presentation-critical text in a tool result and the Anna chat UI renders it byte-for-byte — the model never gets a chance to paraphrase it."
section: tools
slug: executa-display-blocks
order: 12
updated: 2026-09-24
estimated_minutes: 6
---

When your Executa tool runs inside the main Anna chat, its result becomes a
tool message that the model **re-synthesizes into prose**. Wording, ordering,
and even whole fields are probabilistic — no prompt instruction ("print this
field verbatim") can make them a guarantee. If your tool's value depends on a
specific sentence reaching the user exactly — a legal disclaimer, a billing
amount, a *"this is the 6th time you hit this error"* headline computed from
persistent state — you need a channel that does not pass through the model.

**Display blocks** are that channel. Declare them under the reserved
top-level `_display` key of your tool result and the Anna host UI renders
them **byte-for-byte**, in order, anchored at the tool call — with a **100%
presentation rate** that is completely decoupled from model behavior.

## Quick example

```json
{
  "fingerprint": "sha256:71bf...",
  "category": "python.module_not_found_error",
  "occurrence_count": 6,
  "fix_steps": ["step 1", "step 2"],

  "_display": {
    "blocks": [
      { "type": "markdown", "text": "📒 **This is the 6th time you have hit this** — first seen 20 August." },
      { "type": "markdown", "text": "_Tell me if this fixes it and it goes in your logbook for next time._" }
    ]
  }
}
```

What each consumer sees:

| Consumer | Sees |
|---|---|
| **User (chat UI)** | Each block rendered as an attributed card right after the tool-call trace — verbatim, in array order, every time. Cards stay visible even when the user hides tool traces: they are reply content, not debug info. |
| **Model** | `_display` replaced (before every model call) with a note — *"[2 display block(s) were already rendered VERBATIM to the user … Do NOT restate or paraphrase…]"* — plus a ≤120-char preview of each block so its surrounding prose stays coherent. |
| **Everything else in the result** | Delivered to the model unchanged. The model still reasons about and narrates your structured fields as usual. |

## Contract

| Rule | Value |
|---|---|
| `blocks` | array, **1–8** entries |
| `block.type` | `"markdown"` only (v1) |
| `block.text` | non-empty string, ≤ **4 000** chars |
| total across blocks | ≤ **16 000** chars |
| placement | top level of **your tool result** (`result.data` of the invoke response — the host resolves the transport envelopes for you) |
| conditional blocks | just don't emit them — omit-if-null is plain code in your plugin, no prompt logic |

**Over the limits or an unknown `type` ⇒ the whole `_display` is dropped**,
never silently truncated (truncation would break the verbatim guarantee).
Your business fields are untouched, and the host injects a machine-readable
`_display_rejected: "<reason>"` into the result so you can see why in the
tool trace.

> [!NOTE]
> Top-level keys starting with `_` are a host-reserved namespace (like
> `_display`). Unrecognized `_`-keys are passed through today, but carry no
> semantic guarantee — don't build on them.

## Rendering details

- Blocks render as **attributed cards** (small badge naming your tool) with
  styling distinct from the assistant's own bubbles. This is deliberate:
  users can always tell platform prose from plugin-supplied text.
- Markdown is rendered with a **strict sanitizer**: text formatting, lists,
  headings, code, tables, links and images only. No raw HTML, no event
  attributes, no forms/buttons, no `data:` URIs. Links open in a new tab
  with `rel="noopener noreferrer"`.
- Order within `blocks` is preserved; blocks are anchored to the tool call
  that produced them. There is no layout control beyond that (v1).
- History replay renders identically — blocks survive page refresh and
  device switches.

## Where it applies

| Surface | Behavior |
|---|---|
| Main chat (your tool invoked by the Anna agent) | Full `_display` pipeline as described here |
| [App `tools.invoke`](/developers/apps/app-ui-host-api) from your own iframe UI | Not needed — your app receives the raw result (already verbatim); `_display` is passed through untouched for you to reuse |
| [`agent.session`](/developers/tools/executa-agent) runs | The model-side note replacement applies; presentation is up to the app consuming the run |

## Division of labor

| You need | Use |
|---|---|
| An exact sentence must reach the user | `_display` blocks |
| Data the model should reason about / summarize | normal result fields |
| Behavioral guidance ("call X before Y") | `system_prompt_addendum` / SKILL.md |
| Rich interactive UI | App UI bundle (`ui.views`) |

If you previously wrote *"print the `headline` field verbatim"* into your
`system_prompt_addendum` or SKILL.md, move that content into `_display`
and delete the instruction — the prompt route was never reliable (it is
injected only on `#`-mention, per turn, and is advisory to the model even
then).

## Runnable example

[`display-blocks-demo`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/python/display-blocks-demo)
is a miniature error journal: `diagnose_error` returns a structured
diagnosis for the model **plus** a verbatim headline, and emits a follow-up
block only from the third occurrence of the same error — omit-if-null as
plain code. Paste the same traceback three times to watch the counting
headline render byte-identically each round.
