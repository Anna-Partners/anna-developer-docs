---
title: "Bundling Executas"
description: "How an app declares the Executas it bundles, and what install/runtime semantics each kind has."
section: apps
slug: app-bundling
order: 5
updated: 2026-04-22
estimated_minutes: 4
category: "Distribution & Lifecycle"
---

An Anna App's *Executa* bundling is **not a file package**. "Bundling" Executas means listing their `tool_id`s inside the version's manifest JSON — there is no zip or tarball for that part.

> [!NOTE]
> *UI* assets are different. Schema-2 apps additionally upload a static SPA (HTML/JS/CSS/wasm) via the bundle pipeline. That is a real file bundle and is documented in [App UI Bundle Pipeline](/developers/apps/app-ui-bundle).

If you haven't already, read [App Manifest](/developers/apps/app-manifest) first — this page only covers the `required_executas` / `optional_executas` arrays.

## The two arrays

```json
{
  "schema": 1,
  "required_executas": [
    { "tool_id": "web_search" },
    { "tool_id": "pdf_reader", "min_version": "1.0.0" }
  ],
  "optional_executas": [
    { "tool_id": "image_generation" }
  ]
}
```

| Array | Auto-installed for the user? | Tool docs injected on `#`mention? |
|---|---|---|
| `required_executas` | ✅ Yes — `install_app` creates a `UserExecuta` row for every entry the user does not yet have | ✅ |
| `optional_executas` | ❌ No — user must already have it (or install it separately) for it to actually run | ✅ |

A given `tool_id` may appear at most once across both arrays combined.

## Item shape

```json
{ "tool_id": "web_search", "min_version": "1.0.0" }
```

| Field | Required | Constraints |
|---|---|---|
| `tool_id` | yes | 1–200 chars. Must already exist as a row in the platform's `executas` table at submission time and again at publish time |
| `min_version` | no | ≤40 chars. Stored on the manifest but **not enforced** by the validator today; only `tool_id` existence is checked |

There is no syntax for `path://`, `catalogue://`, `hub://`, or any other reference scheme. Bundling Executa source code or binaries inside an app is not supported — Executas are platform-published units; the app simply declares which of them it depends on.

## Lifecycle of a bundle

1. **Create version** — `anna-app apps publish` is a composite of `apps push` (stage the working draft) + `apps cut <version>` (snapshot + **freeze** every executa ref to an immutable `ExecutaVersion`), so the version carries its `anna_app_executas` bindings from the moment it exists. The raw `POST /api/v1/developer/apps/{id}/versions` endpoint is the legacy path: manifest `tool_id`s are checked for existence, but bindings are only frozen later, at release. Either way the version is stored with `is_latest=False`.
2. **Publish version** (`POST /api/v1/developer/apps/{id}/versions/{vid}/publish`) — the manifest is **re-validated** (in case an Executa was removed in the meantime). On success:
   - Cut-time `anna_app_executas` bindings are reused as-is; versions without them (legacy path) get the snapshot rebuilt here: `required` first, then `optional`, in declared order, with `display_order` and `is_required` recorded.
   - The app's `latest_version` cache is updated.
   - If the app's `status` is `APPROVED` or `PENDING_REVIEW`, it is auto-promoted to `PUBLISHED`.
3. **User install** (`install_app`) — only allowed when `status ∈ {PUBLISHED, APPROVED}`. The latest published version is fetched; missing `UserExecuta` rows for `required_executas` are created. `optional_executas` are not auto-installed.
4. **User `#`mention** (`build_app_mention_prompt`) — only effective when the user has the app installed and `is_enabled=True`. All bundled Executas (required + optional) have their tool documentation injected into the system prompt for that turn.

## Validation checklist

Before clicking **Validate** in the Versions tab, make sure:

- [ ] `schema` is `1`.
- [ ] `required_executas` has at least one entry.
- [ ] Every `tool_id` exists in the Executa catalogue (the **Validate** button confirms this with a single round trip).
- [ ] No `tool_id` appears in both arrays.
- [ ] `system_prompt_addendum` is ≤4000 chars.
- [ ] `user_message_prefix_template`, if set, contains exactly one `{user_message}` and is ≤500 chars.

Next: [Listing assets](/developers/apps/app-listing).
