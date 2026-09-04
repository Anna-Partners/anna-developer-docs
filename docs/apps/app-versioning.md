---
title: "Versioning & Updates"
description: "How versions are created, ordered, and rolled out to installed users."
section: apps
slug: app-versioning
order: 8
updated: 2026-04-22
estimated_minutes: 4
category: "Distribution & Lifecycle"
---

Each Anna App version is an immutable `AnnaAppVersion` row consisting of a SemVer string, a free-form `changelog`, and the manifest JSON. For `schema: 2` apps the version is also bound 1:1 to an immutable `AnnaAppUiBundle` (the uploaded static SPA) — a bundle that has been finalized cannot be edited; you must create a new version. To change anything bundled or any prompt directive, create a new version with a strictly greater SemVer and publish it.

## SemVer rules

The `version` field must match:

```
^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-.]+)?$
```

- `X.Y.Z` is required.
- An optional `-prerelease` suffix is allowed (e.g. `1.2.0-beta.1`).
- `+build` metadata is **not** supported by the validator.
- A new version must be **strictly greater** than the largest existing version of this app, comparing major/minor/patch numerically and treating any pre-release as smaller than the matching release (`1.2.0-beta.1 < 1.2.0`).

Examples:

| Existing latest | Allowed next | Rejected |
|---|---|---|
| `1.0.0` | `1.0.1`, `1.1.0`, `2.0.0` | `1.0.0`, `0.9.0` |
| `1.2.0-beta.1` | `1.2.0-beta.2`, `1.2.0`, `1.3.0` | `1.2.0-alpha.9`, `1.1.9` |

There is **no semantic distinction** between patch / minor / major bumps in the platform today. There is no separate "auto-install patch, prompt for major" tiering — see [Update behaviour](#update-behaviour-for-installed-users) below.

## Creating a version

`POST /api/v1/developer/apps/{id}/versions`:

```json
{
  "version": "1.0.1",
  "changelog": "Fix typo in system_prompt_addendum.",
  "manifest": { "schema": 1, "required_executas": [{ "tool_id": "web_search" }] }
}
```

Server-side checks:

1. SemVer format.
2. No duplicate version on this app.
3. Strictly greater than current max.
4. Full manifest validation (see [App Manifest](/developers/apps/app-manifest#validation)).

The version is created with `is_latest=False`. It does not affect anyone until you publish it.

> **CLI note** — `anna-app apps publish` no longer calls this endpoint directly: it runs `apps push` + `apps cut <version>`, so the resulting version also carries cut-time frozen executa bindings. The endpoint above remains for raw API/CI callers.

## Publishing

`POST /api/v1/developer/apps/{id}/versions/{vid}/publish` — see [Publishing an App](/developers/apps/app-publish#4-publish-a-version) for the full flow. In short:

- App must be `APPROVED` or `PUBLISHED`.
- Manifest is re-validated.
- This version becomes `is_latest`; the previous one's flag is cleared.
- The `anna_app_executas` snapshot is rebuilt for this version.

The previous "published" version row is **not** deleted — it remains in the table with `is_latest=False`. There is no public endpoint to install an arbitrary historical version.

## Update behaviour for installed users

`UserAnnaApp` carries `auto_update: bool` (defaults to `True` on first install). The platform behaviour today:

- Re-running `install_app` for an already-installed user upgrades `installed_version` to the current `is_latest` and re-runs `required_executas` auto-install for any newly added entries.
- There is **no scheduled job** that pushes updates automatically; "auto-update" is a stored preference, not an executed policy. New `is_latest` versions take effect for a user the next time install is invoked for them.
- There is **no in-product "What's new" prompt**, no per-segment (patch/minor/major) tiering, and no "user must accept major upgrade" gate.

## Rollback

There is no built-in rollback or "deprecate version" endpoint. To effectively roll back, publish a new version (with a higher SemVer) that restores the previous manifest content.

## Archiving the app

Archiving the **app** (`POST /developer/apps/{id}/archive`) sets `status=ARCHIVED`, removing it from the App Store. Existing `UserAnnaApp` rows continue to function. There is no per-version archive.

## Cadence and badges

The platform does **not** today implement:

- "Recently updated" badges based on shipping window.
- "Maintenance status: unknown" warnings for stale apps.
- Automatic delisting after N months of inactivity.

`AnnaApp.updated_at` is tracked and surfaced in the listing payload, but no policy is keyed off it.

That is the full versioning surface. Ship a new SemVer, publish it, and installed users converge on the next install call.
