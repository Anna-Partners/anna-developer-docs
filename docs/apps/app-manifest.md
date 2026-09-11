---
title: "App Manifest"
description: "The manifest JSON that declares which Executas an app bundles and how the assistant should behave when it is mentioned."
section: apps
slug: app-manifest
order: 4
updated: 2026-09-11
estimated_minutes: 6
---

An Anna App is composed of two halves:

1. **Listing metadata** (name, slug, category, tagline, description, logo, screenshots, homepage, pricing model). This is edited in the **Listing** tab of the [Developer Console](/developer) and stored on the `AnnaApp` row. It is **not** part of the manifest.
2. **Manifest** — a JSON document attached to each immutable [version](/developers/apps/app-versioning). It declares the Executas the app bundles and the prompt instructions the assistant should follow when the user `#`mentions the app.

This page documents the manifest only.

## Minimal example

```json sample=app-manifest
{
  "schema": 1,
  "required_executas": [
    { "tool_id": "web_search" }
  ]
}
```

## Full example

```json sample=app-manifest
{
  "schema": 1,
  "required_executas": [
    { "tool_id": "web_search" },
    { "tool_id": "pdf_reader", "min_version": "1.0.0" }
  ],
  "optional_executas": [
    { "tool_id": "image_generation", "min_version": "1.0.0" }
  ],
  "permissions": [],
  "host_capabilities": ["aps.kv", "llm.sample"],
  "system_prompt_addendum": "You are Research Buddy, a meticulous research assistant. Always cite sources with markdown links. Prefer primary sources. When asked a question, search first, then synthesise.",
  "user_message_prefix_template": "[Research] {user_message}",
  "tags": ["research", "productivity"]
}
```

## Field reference

The manifest is parsed by the `AppManifest` Pydantic model with `extra="forbid"`. **Any field not listed below will be rejected.**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `schema` | integer | yes | `1` (no UI), `2` (UI runtime, enables the [`ui`](/developers/apps/app-ui-manifest) section) or `3` (adds the structured [`storage`](#storage-schema-3) entry and **removes** `permissions`) |
| `required_executas` | array | yes | Length ≥ 1. Items: `{ "tool_id": string, "min_version"?: string, "version"?: string }` |
| `optional_executas` | array | no | Same item shape as `required_executas`. Defaults to `[]` |
| `permissions` | array of string | no | **Deprecated — display-only, `schema ≤ 2` only.** Never enforced anywhere: iframe method gating is `ui.host_api`, storage scope gating is `host_capabilities`. Store/review permission displays are **derived** from those enforced declarations, not from this list. `schema: 3` rejects the field: `permissions: removed in schema 3 — permission display is derived from ui.host_api + storage/host_capabilities` |
| `host_capabilities` | array of string | no | **Strict allow-list** (see below). Declares the host-mediated capabilities the app's bundled Executas rely on (APS storage scopes, LLM sampling, web search, …). Note: each Executa must **also** declare its own `host_capabilities` in its plugin manifest — per-invoke tokens (e.g. `storage_token`) are gated on the Executa's declaration plus the user's grant, not on this field alone. At `schema: 3`, when an Executa's manifest declares storage the publish validator requires both declarations to normalize to the **same** storage surface |
| `storage` | object | no | **`schema: 3` only.** Structured APS declaration replacing the `aps.*` capability strings — see [`storage` (schema 3)](#storage-schema-3). Mutually exclusive with `aps.*` entries in `host_capabilities` |
| `system_prompt_addendum` | string | no | Max 4000 characters. Appended to the assistant's system prompt when the user `#`mentions the app |
| `user_message_prefix_template` | string | no | Max 500 characters. Must contain **exactly one** `{user_message}` placeholder. See [Runtime behaviour](#runtime-behaviour) for current limitations |
| `tags` | array of string | no | Free-form tags. Stored but not surfaced in the App Store today |
| `ui` | object | no (required in practice when `schema ≥ 2` — mandatory for bundle-only apps with no `required_executas`) | UI bundle + views + host API ACL. Full reference: [App UI Manifest](/developers/apps/app-ui-manifest) |
| `dev` | object | no | **Local-harness-only.** Consumed by `anna-app dev`; production dispatcher ignores it at runtime, and `anna-app publish` strips it before upload. See [`dev` block](#dev-block-local-harness-only) |

Allowed `permissions` values (`_ALLOWED_PERMISSIONS`, `schema ≤ 2` only — the whole field is display-only and removed at `schema: 3`):

```
ui.svg
fs.read, fs.write
tools.invoke
chat.read, chat.write_message, chat.append_artifact
artifact.create, artifact.update, artifact.delete
llm.complete
storage.read, storage.write
prefs.read
```

Allowed `host_capabilities` values (`_ALLOWED_HOST_CAPABILITIES` — shared with the Executa plugin manifest):

```
llm.sample, llm.complete, llm.embed
llm.agent.auto, llm.agent.fixed
llm.image, llm.image.edit
web.search, web.fetch, web.image_search, web.image_fetch
host.upload
aps.kv, aps.files
aps.scope.user.read, aps.scope.user.write
aps.scope.app.read, aps.scope.app.write
aps.scope.tool.read, aps.scope.tool.write
aps.scope.admin   (platform pre-installed apps only)
```

Every `aps.*` string — including the `aps.scope.*` family — also triggers plugin-side `storage_token` minting when it appears in an **Executa's** manifest (“wide convergence”; see [Persistent Storage](/developers/tools/executa-storage#three-pre-conditions)).

### `storage` (schema 3)

From `schema: 3` the ten `aps.*` capability strings collapse into one structured entry (the legacy strings remain permanent aliases for `schema ≤ 2` manifests — both forms normalize to the same declaration):

```json
{
  "schema": 3,
  "storage": {
    "kv": true,
    "files": false,
    "scopes": { "user": "rw", "tool": "rw" }
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `kv` | boolean | KV surface: plugin `storage/*` reverse RPCs + iframe `anna.storage.*`. Implies self-owned `scope=app` access (legacy `aps.kv` parity) |
| `files` | boolean | Object/file surface: plugin `files/*` reverse RPCs + iframe `anna.files.*`. Also implies self app-scope |
| `scopes` | object | Explicit cross-scope grants: key ∈ `user` \| `app` \| `tool`, value ∈ `"r"` \| `"w"` \| `"rw"`. `app` here means **cross-owner** app-scope (self app-scope comes from `kv`/`files`); consumed by the iframe scope gate. Plugin tokens stay pinned to `user`/`tool` regardless |

Rules enforced by the publish validator:

- `storage` requires `schema ≥ 3` (`manifest.storage requires schema >= 3 (declare legacy aps.* host_capabilities instead)`);
- `storage` and `aps.*` strings in `host_capabilities` are **mutually exclusive** (`storage declaration: use either manifest.storage (schema 3) or legacy aps.* host_capabilities, not both`);
- when a bundled Executa's own manifest declares storage, its normalized declaration must **equal** the app's (single-source rule — kills the “declared in both places, drifted silently” failure class).

### `required_executas[]` and `optional_executas[]`

```json
{ "tool_id": "web_search", "min_version": "1.0.0" }
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `tool_id` | string | yes | 1–200 chars. Must match the `tool_id` of an Executa already published in the platform's Executa catalogue (visibility must be `app_bundled` or `public`; `private` and `archived` Executas are rejected) |
| `min_version` | string | no | Up to 40 chars. Stored on the manifest; **not enforced** by the validator today (only `tool_id` existence is checked) |
| `version` | string | no | Pin a specific `ExecutaVersion` snapshot. Omit or use `"latest"` to auto-freeze the current Executa state at publish time |

Behavioural difference between the two arrays:

- **`required_executas`** — automatically installed for the user when the app is installed (a `UserExecuta` row is created if missing). Tool documentation is injected into the system prompt whenever the app is `#`mentioned.
- **`optional_executas`** — **not** auto-installed. Tool documentation is still injected when the app is `#`mentioned, but the user must have the Executa otherwise authorised for it to actually run.

A given `tool_id` may appear at most once across both arrays combined.

### `dev` block (local-harness-only)

The `dev` block is consumed by `anna-app dev` (the local harness shipped with the [`anna-app` CLI](/developers/apps/app-quickstart)). It is declared on the Pydantic model so `extra="forbid"` does not reject it, but the production dispatcher **ignores it at runtime**, and `anna-app publish` strips it before upload.

```json
{
  "schema": 2,
  "required_executas": [{ "tool_id": "tool-dev-focus-flow" }],
  "ui": { "...": "..." },
  "dev": {
    "fixtures": ["fixtures/*.jsonl"],
    "seed_storage": { "focus-flow:last": 0 },
    "user_id": 7,
    "mocks": {
      "tools.invoke": { "result": { "pong": true } }
    }
  }
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `fixtures` | array of string | no | Glob patterns, relative to the manifest dir, pointing at JSONL fixture files for replay |
| `mocks` | object | no | Per-`(ns, method)` static response mocks, keyed by `"ns.method"` (e.g. `"tools.invoke"`) |
| `seed_storage` | object | no | Initial `runtime_state` planted into the in-memory `WindowStore` for `anna-app dev` sessions |
| `user_id` | integer | no | Override the harness's default `user_id` (default: `1`) |

The `dev` block also accepts unknown extra keys (`extra="allow"`) so the harness can evolve independently from the on-the-wire schema.

## Validation

Validation runs in two places:

- `POST /api/v1/developer/apps/validate-manifest` — the **Validate** button in the Developer Console (read-only dry run).
- `POST /api/v1/developer/apps/{id}/versions` — when you create a new version. The same checks run again on `publish` to guard against an Executa being deleted in the meantime.

Checks performed (`anna_app_validator.validate_manifest`):

1. **Structure** — Pydantic `AppManifest` parsing (`extra="forbid"`, types, length limits).
2. **`schema`** must be `1`, `2` or `3`.
3. **`required_executas` non-empty** — **required for `schema: 1`** (chat-augmentation apps need at least one tool, otherwise the app is a runtime no-op). **Optional for `schema ≥ 2`**: Bundle-only UI apps that rely solely on `ui.host_api` (e.g. `image.*`, `storage.*`, `llm.*`) may leave both `required_executas` and `optional_executas` empty.
4. **Placeholder rule** — if `user_message_prefix_template` is set, it must contain exactly one `{user_message}` substring. Zero or two+ occurrences fail.
5. **Executa existence + visibility** — every `tool_id` must resolve to a non-archived `executas` row whose `visibility` is `app_bundled` or `public`.
6. **Uniqueness** — no `tool_id` may appear twice across `required_executas + optional_executas`.
7. **Permissions allow-list** — on `schema ≤ 2`, unknown `permissions` entries are rejected. On `schema: 3` any non-empty `permissions` is rejected (the field is removed — display is derived from `ui.host_api` + the storage declaration).
8. **UI section** — when `schema ≥ 2`, the `ui` section is statically validated (`validate_ui_section_static`). Bundle entry path existence is re-checked at `bundle/finalize`. See [App UI Manifest](/developers/apps/app-ui-manifest) for the full rules.
9. **Storage declaration** (`schema: 3`) — `manifest.storage` is mutually exclusive with `aps.*` strings in `host_capabilities`, and a bundled Executa's own storage declaration must normalize to exactly the app's (single-source rule). See [storage (schema 3)](#storage-schema-3).

Common rejection reasons:

- Missing or wrong-typed required field.
- An unknown field (manifest uses `extra="forbid"`).
- `required_executas` empty **on a `schema: 1` app** (allowed on `schema ≥ 2` Bundle-only apps).
- `tool_id` not found in the Executa catalogue.
- `user_message_prefix_template` missing `{user_message}` or containing it more than once.

Version-level checks (run alongside the manifest checks when creating a version):

- `version` must be valid SemVer (`X.Y.Z` with optional `-prerelease`).
- `version` must be **strictly greater** than the largest existing version of this app (pre-release sorts below the matching release).

## Runtime behaviour

The manifest only takes effect when the user explicitly `#`mentions the app in a chat **and** has it installed and enabled.

| Manifest field | What the runtime does with it |
|---|---|
| `required_executas` | On install, missing `UserExecuta` rows are auto-created. On `#`mention, all bundled Executas' tool documentation is injected into the system prompt |
| `optional_executas` | On `#`mention, tool documentation is injected. **Not** auto-installed |
| `system_prompt_addendum` | Wrapped in `<app><system_prompt_addendum>...</system_prompt_addendum></app>` and appended to the system prompt. Treated as authoritative for that turn |
| `user_message_prefix_template` | **Partial.** The template is surfaced to the model as a `<user_message_prefix_template>` block in the system prompt, so the assistant is aware of it. The placeholder is **not** yet substituted into the user's actual message — treat it as a hint, not a hard rewrite |
| `permissions` | **Never enforced at runtime** — display-only legacy metadata on `schema ≤ 2` (iframe gating is `ui.host_api`; see [Host API](/developers/apps/app-ui-host-api)). Rejected at `schema: 3` |
| `tags` | Stored only |
| `schema` | `1` = no UI; `≥ 2` = UI runtime enabled; `3` additionally enables `storage` and removes `permissions`. When `≥ 2`, the `<ui_views>` block is appended to the per-app prompt and the LLM gets the `open_app_view` / `update_app_view` / `close_app_view` tools |
| `ui` | See [App UI Overview](/developers/apps/app-ui-overview) and [App UI Manifest](/developers/apps/app-ui-manifest) |

If multiple apps are mentioned in the same turn, all `system_prompt_addendum` blocks are concatenated in mention order; `user_message_prefix_template` is taken from the first non-empty mentioned app (mention order).

> [!TIP]
> Validate locally before submission. The reviewer will tell you about a failed validation, but it adds days to the review cycle. Click **Validate** in the Developer Console version editor — it runs the exact same checks the version-create endpoint runs.
