---
title: "App Manifest"
description: "The manifest JSON that declares which Executas an app bundles, how the assistant should behave when it is mentioned, and the three capability declarations."
section: apps
slug: app-manifest
order: 4
updated: 2026-11-02
estimated_minutes: 6
---

An Anna App is composed of two halves:

1. **Listing metadata** (name, slug, category, tagline, description, logo, screenshots, homepage, pricing model). This is edited in the **Listing** tab of the [Developer Console](/developer) and stored on the `AnnaApp` row. It is **not** part of the manifest.
2. **Manifest** — a JSON document attached to each immutable [version](/developers/apps/app-versioning). It declares the Executas the app bundles, the prompt instructions the assistant should follow when the user `#`mentions the app, and the few [capability declarations](#capability-declarations) that involve something other than the user's own account.

This page documents the manifest only.

## Minimal example

```json sample=app-manifest
{
  "schema": 4,
  "required_executas": [
    { "tool_id": "web_search" }
  ]
}
```

## Full example

```json sample=app-manifest
{
  "schema": 4,
  "required_executas": [
    { "tool_id": "web_search" },
    { "tool_id": "pdf_reader", "min_version": "1.0.0" }
  ],
  "optional_executas": [
    { "tool_id": "image_generation", "min_version": "1.0.0" }
  ],
  "storage": { "scopes": { "user": "rw" } },
  "system_prompt_addendum": "You are Research Buddy, a meticulous research assistant. Always cite sources with markdown links. Prefer primary sources. When asked a question, search first, then synthesise.",
  "user_message_prefix_template": "[Research] {user_message}",
  "tags": ["research", "productivity"]
}
```

## Field reference

The manifest is parsed by the `AppManifest` Pydantic model with `extra="forbid"`. **Any field not listed below will be rejected** — including the retired `permissions` / `host_capabilities` fields when they appear on a `schema: 4` manifest (older schemas are [normalized](#legacy-manifests-schema-13) instead).

| Field | Type | Required | Constraints |
|---|---|---|---|
| `schema` | integer | yes | `1`–`4`. `1` = no UI; `≥ 2` enables the [`ui`](/developers/apps/app-ui-manifest) section; `4` is the current schema. Lower values are accepted and rewritten to `4` on ingest |
| `required_executas` | array | `schema: 1` only | Items: `{ "tool_id": string, "min_version"?: string, "version"?: string }` |
| `optional_executas` | array | no | Same item shape as `required_executas`. Defaults to `[]` |
| `storage` | object | no | Cross-app data declaration — `{ "scopes": { "user" \| "app" \| "tool": "r" \| "w" \| "rw" } }`. See [Capability declarations](#capability-declarations) |
| `system_prompt_addendum` | string | no | Max 4000 characters. Appended to the assistant's system prompt when the user `#`mentions the app |
| `user_message_prefix_template` | string | no | Max 500 characters. Must contain **exactly one** `{user_message}` placeholder. See [Runtime behaviour](#runtime-behaviour) for current limitations |
| `tags` | array of string | no | Free-form tags. Stored but not surfaced in the App Store today |
| `ui` | object | no (required in practice when `schema ≥ 2` — mandatory for bundle-only apps with no `required_executas`) | UI bundle + views + the `credentials` / `agent.tools` declarations + browser features. Full reference: [App UI Manifest](/developers/apps/app-ui-manifest) |
| `dev` | object | no | **Local-harness-only.** Consumed by `anna-app dev`; production dispatcher ignores it at runtime, and `anna-app publish` strips it before upload. See [`dev` block](#dev-block-local-harness-only) |

## Capability declarations

**Installing an App is the consent.** Every Host API namespace — `llm.*`, `image.*`, `video.*`, `music.*`, `audio.*`, `web.*`, `upload.*`, `files.*`, `storage.*` (own app scope), `chat.*`, `artifact.*`, `window.*`, `apps.*`, `tools.*` for your declared Executas, `mobile.*`, `agent.session.*` — is available to an installed, enabled App **without any manifest declaration and without a user toggle**. The App only ever spends the installing user's own CU quota, so that quota is the only usage gate; the user's controls are *disable* and *uninstall*.

The manifest declares exactly the three things that touch a second principal — a third-party account, data shared with the user's other apps, or the user's own machine:

| Declaration | Where | Protects | Enforcement |
|---|---|---|---|
| `ui.host_api.credentials: [provider id, …]` | `ui` section | The user's **third-party accounts** (`google`, …). `credentials.list_accounts` / `credentials.get_token` only work for listed providers — and the user must also have connected that provider on the platform | Undeclared provider → iframe `permission_denied`; the Executa `credentials_token` only carries declared providers |
| `ui.host_api.agent.tools: [tool id, …] \| ["*"]` | `ui` section | The user's **local device**: host-kit tools (`fs_*`, `exec_*`, `browser_*`) a sandbox agent session created by the App may use. `"*"` = every host-kit tool. Server-side tools (`doc_read`, `sheet_read`, `web_search`, …) never need declaring | Effective session tool set = `requested ∩ (server_side ∪ (host_kit ∩ declared))` — see [LLM & Agent](/developers/apps/llm-and-agent) |
| `storage.scopes: { scope: mode }` | top level | **Data shared with the user's other apps**: `user` (user-wide), `app` (another app's bucket via `owner`), `tool` (an Executa's cache); mode `r` / `w` / `rw`. Your own `scope=app` bucket needs no declaration | Undeclared scope → iframe `permission_denied`; a bundled Executa's `storage_token.allowed_scopes` = `["tool"]` + `"user"` iff the Executa declares it |

Plus the browser-mandated [`ui.browser_permissions`](/developers/apps/app-ui-browser-permissions) (`microphone`, `camera`, …), which is a Permissions-Policy delegation, not a platform capability — a realtime voice App declares `microphone` explicitly.

Schema-4 shape with all three declarations:

```jsonc
{
  "schema": 4,
  "required_executas": [{ "tool_id": "inbox-executa" }],
  "storage": { "scopes": { "user": "rw" } },                 // optional: cross-app data
  "ui": {
    "bundle": { "format": "static-spa", "entry": "index.html", "external_origins": [] },
    "views": [ /* … */ ],
    "host_api": {
      "credentials": ["google"],                             // optional: third-party accounts
      "agent": { "tools": ["fs_read_file", "exec_run"] }     // optional: local-device tools (host-kit only)
    },
    "browser_permissions": ["microphone"],                   // optional: browser features
    "csp_overrides": {}
  }
}
```

Most Apps declare none of these and have no `host_api` block at all. The Store page summarises whatever you do declare as at most three plain-language items (*Connects to: Gmail* / *Reads/writes data shared with your other apps* / *Local device access*) — that summary (`AnnaAppDetail.capabilities`) is derived server-side from the manifest and is also the reviewer's checklist.

### Legacy manifests (schema 1–3)

Older manifests are accepted at every ingest point (publish, working draft, `anna-app validate`, Executa `describe` caches) and folded into schema 4 by a single idempotent normalization. **No republish is needed**; `anna-app validate` warns about retired fields so you can delete them on your next release.

| Legacy field | Normalization |
|---|---|
| `permissions` | Dropped |
| `host_capabilities` entries `aps.scope.<scope>.read` / `.write`, `aps.scope.admin` | Folded into `storage.scopes` (`admin` ⇒ every scope `rw`) |
| Every other `host_capabilities` string (`aps.kv`, `aps.files`, `llm.*`, `web.*`, `host.upload`, …) | Dropped |
| `storage.kv` / `storage.files` (schema 3) | Dropped — only `storage.scopes` survives |
| `ui.host_api.audio` containing `"session"` | `ui.browser_permissions` gains `microphone` (deduplicated) |
| `ui.host_api.tools` refs whose `tool_id` is not in `required_executas` ∪ `optional_executas` | Appended to `optional_executas` |
| `ui.host_api.{tools, chat, artifact, llm, fs, prefs, storage, window, files, image, video, music, audio, upload, apps, web, mobile, embed}` and `ui.host_api.agent.session` | Dropped |
| `ui.host_api.agent.tools`, `ui.host_api.credentials` | Kept verbatim |
| `schema` ≤ 3 | Rewritten to `4` |

Pydantic validation (`extra="forbid"`) runs **after** normalization, so any other unknown key is still rejected.

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
- **`optional_executas`** — **not** auto-installed. Tool documentation is still injected when the app is `#`mentioned, but the user must have the Executa installed for it to actually run.

A given `tool_id` may appear at most once across both arrays combined. Together the two arrays are also the set of Executas your iframe may call through [`tools.invoke`](/developers/apps/app-ui-host-api#tools) — there is no separate allow-list.

### `dev` block (local-harness-only)

The `dev` block is consumed by `anna-app dev` (the local harness shipped with the [`anna-app` CLI](/developers/apps/app-quickstart)). It is declared on the Pydantic model so `extra="forbid"` does not reject it, but the production dispatcher **ignores it at runtime**, and `anna-app publish` strips it before upload.

```json
{
  "schema": 4,
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

Checks performed (`anna_app_validator.validate_manifest`, after [legacy normalization](#legacy-manifests-schema-13)):

1. **Structure** — Pydantic `AppManifest` parsing (`extra="forbid"`, types, length limits).
2. **`schema`** must be `1`–`4`.
3. **`required_executas` non-empty** — **required for `schema: 1`** (chat-augmentation apps need at least one tool, otherwise the app is a runtime no-op). **Optional for `schema ≥ 2`**: Bundle-only UI apps that rely solely on the Host API (e.g. `image.*`, `storage.*`, `llm.*`) may leave both `required_executas` and `optional_executas` empty.
4. **Placeholder rule** — if `user_message_prefix_template` is set, it must contain exactly one `{user_message}` substring. Zero or two+ occurrences fail.
5. **Executa existence + visibility** — every `tool_id` must resolve to a non-archived `executas` row whose `visibility` is `app_bundled` or `public`.
6. **Uniqueness** — no `tool_id` may appear twice across `required_executas + optional_executas`.
7. **Storage scopes** — `storage.scopes` keys must be `user` / `app` / `tool` and values `r` / `w` / `rw`.
8. **UI section** — when `schema ≥ 2`, the `ui` section is statically validated (`validate_ui_section_static`). Bundle entry path existence is re-checked at `bundle/finalize`. See [App UI Manifest](/developers/apps/app-ui-manifest) for the full rules.

Common rejection reasons:

- Missing or wrong-typed required field.
- An unknown field (manifest uses `extra="forbid"`) — on `schema: 4` this includes `permissions`, `host_capabilities` and the retired `ui.host_api` namespaces.
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
| `storage` | Consulted by the iframe `storage.*` / `files.*` scope gate and by the `storage_token` minter for bundled Executas |
| `tags` | Stored only |
| `schema` | `1` = no UI; `≥ 2` = UI runtime enabled. When `≥ 2`, the `<ui_views>` block is appended to the per-app prompt and the LLM gets the `open_app_view` / `update_app_view` / `close_app_view` tools |
| `ui` | See [App UI Overview](/developers/apps/app-ui-overview) and [App UI Manifest](/developers/apps/app-ui-manifest) |

If multiple apps are mentioned in the same turn, all `system_prompt_addendum` blocks are concatenated in mention order; `user_message_prefix_template` is taken from the first non-empty mentioned app (mention order).

> [!TIP]
> Validate locally before submission. The reviewer will tell you about a failed validation, but it adds days to the review cycle. Click **Validate** in the Developer Console version editor — it runs the exact same checks the version-create endpoint runs.
