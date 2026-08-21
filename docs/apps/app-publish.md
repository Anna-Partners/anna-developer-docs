---
title: "Publishing an App"
description: "Walk an app through review and into the Anna App Store."
section: apps
slug: app-publish
order: 7
updated: 2026-04-22
estimated_minutes: 5
category: "Distribution & Lifecycle"
---

Apps move through the review pipeline from the [Developer Console](/developer) **or** the `anna-app` CLI (`anna-app apps push` / `cut` / `release` / `publish` / `submit-review`, plus `archive` / `unpublish` / `status` / `versions` / `grants`). There is no raw zip upload — the CLI bundles and uploads for you, and admin review is the only step that happens exclusively server-side.

## Status machine

```
DRAFT ──submit──▶ PENDING_REVIEW ──admin approve──▶ APPROVED ──publish version──▶ PUBLISHED
  ▲                      │                              │                              │
  └──── REJECTED ◀───────┘                              └────── publish version ───────┘
                                                                                        │
                                                                                  ARCHIVED
```

Defined in `AnnaAppStatus`:

| Status | Meaning |
|---|---|
| `DRAFT` | Newly created. Not visible to anyone but you |
| `PENDING_REVIEW` | Submitted for admin review. You can no longer submit again until the admin acts |
| `APPROVED` | Admin approved but no version is `is_latest` yet — invisible in the App Store, but **installable** by direct lookup |
| `PUBLISHED` | Visible in the App Store and installable. Set automatically when you publish a version while in `APPROVED`/`PENDING_REVIEW`, or when an admin approves with `publish=True` |
| `REJECTED` | Admin rejected. You can edit and re-submit |
| `ARCHIVED` | Hidden from the App Store. Existing installations keep working |

## 1. Pre-flight (developer)

- [ ] Listing fields filled in ([Listing Fields](/developers/apps/app-listing)).
- [ ] At least one version exists ([App Manifest](/developers/apps/app-manifest)).
- [ ] **Validate** in the Versions tab returns `valid: true`.
- [ ] *(UI apps, `schema: 2`)* The version's UI bundle has been uploaded and `bundle/finalize` returned `status: bundle_ready`. The platform refuses to open windows for any version whose bundle is still `draft`. See [App UI Bundle Pipeline](/developers/apps/app-ui-bundle).
- [ ] You have installed and used the app yourself end-to-end.

## 2. Submit for review

In the Console: **Settings tab → Submit for review** (`POST /developer/apps/{id}/submit-review`).

Backend rules:

- The app must currently be `DRAFT` or `REJECTED`.
- The app must have at least one version (otherwise: `"提交审核前需至少创建一个版本"`).
- On success the status flips to `PENDING_REVIEW`.

There is no email notification today.

## 3. Admin review

An admin (or super-admin with the `APPS_MGMT` section) acts on the app via:

- `POST /api/v1/super-admin/apps/{id}/approve` with body `{ "publish": bool, "notes": string? }`
  - Status must be `PENDING_REVIEW`.
  - With `publish: false` → status becomes `APPROVED`.
  - With `publish: true` → the most-recently created version is published (becomes `is_latest`) and status becomes `PUBLISHED`.
  - `review_notes`, `reviewed_at`, `reviewed_by_id` are recorded.
- `POST /api/v1/super-admin/apps/{id}/reject` — status becomes `REJECTED`. You can revise and submit again.

Reviewers verify, at minimum:

- Manifest re-validates against the schema and against the live Executa catalogue.
- Listing copy and screenshots match observed behaviour.

There is no enforced SLA today; check **My Apps** in the Console for the current status.

## 4. Publish a version

Once the app reaches `APPROVED` (or `PUBLISHED`), the developer can publish individual versions via the **Versions** tab → **Publish** (`POST /developer/apps/{id}/versions/{vid}/publish`):

- Allowed only when `app.status ∈ {APPROVED, PUBLISHED}` (otherwise: `"App 必须先通过审核（APPROVED）后才能发布版本"`).
- The manifest is re-validated against the live Executa catalogue.
- Other versions of the same app have `is_latest` cleared; this one is set to `is_latest=True` with `published_at = now()`.
- The `anna_app_executas` snapshot is rebuilt.
- `app.latest_version` is updated; `status` auto-promotes from `APPROVED`/`PENDING_REVIEW` to `PUBLISHED`.

## 5. After publish

- The app appears in the public App Store list (`status == PUBLISHED`).
- New installs auto-install the app's `required_executas`.
- `install_count`, `rating_avg`, `rating_count`, and `is_featured` are tracked on `AnnaApp` (rating/featured are admin-driven).

## 6. Rejection

If the admin rejects, the app moves to `REJECTED`. Edit the listing or create a new version, then submit for review again. There is no penalty for multiple rounds.

## 7. Archive

Settings tab → **Archive** (`POST /developer/apps/{id}/archive`):

- Sets `status = ARCHIVED` from any state.
- Existing `UserAnnaApp` rows are untouched — installed users continue to use the app.
- New users cannot discover or install the app.

Next: [Versioning & updates](/developers/apps/app-versioning).
