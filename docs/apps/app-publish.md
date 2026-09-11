---
title: "Publishing an App"
description: "Walk an app through review and into the Anna App Store."
section: apps
slug: app-publish
order: 7
updated: 2026-08-26
estimated_minutes: 5
category: "Distribution & Lifecycle"
---

Apps move through the review pipeline from the [Developer Console](/developer) **or** the `anna-app` CLI (`anna-app apps push` / `cut` / `release` / `publish` / `submit-review`, plus `archive` / `unpublish` / `status` / `versions` / `grants`). There is no raw zip upload — the CLI bundles and uploads for you, and admin review is the only step that happens exclusively server-side.

> `anna-app apps publish` is a composite of `apps push` + `apps cut <version>` — it creates the immutable version artifact (with frozen executa bindings) but does **not** put it on the App Store. A new app still needs `apps submit-review` → admin approval → `apps release <version>` before it is live. Until then the App Center detail (visible to you and reviewers) shows the review-candidate version's bundled tools with a `candidate` badge.

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
- [ ] *(UI apps, `schema ≥ 2`)* The version's UI bundle has been uploaded and `bundle/finalize` returned `status: bundle_ready`. The platform refuses to open windows for any version whose bundle is still `draft`. See [App UI Bundle Pipeline](/developers/apps/app-ui-bundle).
- [ ] You have installed and used the app yourself end-to-end.

## 2. Submit for review

In the Console: **Versions tab → Submit for review** (`POST /developer/apps/{id}/submit-review`), or `anna-app apps submit-review`.

The review targets a **specific version**: at submit time the newest cut version is pinned as the *review candidate* (`review_candidate_version`). The Console button names it (e.g. *Submit v1.2.0 for review*), and the Versions table marks the pinned row with a `review candidate` badge while the review is in flight. Reviewer installs, review windows, and approval all resolve to the pinned version — cutting new versions during review does **not** move the target.

Backend rules:

- The app must currently be `DRAFT`, `REJECTED`, or `PENDING_REVIEW` (re-submit; see below).
- The app must have at least one cut version (otherwise: `"提交审核前需至少创建一个版本"`).
- A release precheck runs at submission (manifest validation, executa-binding freeze dry-run, UI bundle readiness for `schema ≥ 2`). Failures come back to you as a `400` at submit time instead of surfacing to the admin at approval time.
- On success the status flips to `PENDING_REVIEW` and the candidate is pinned.

**Switching the candidate**: if you cut a new version while `PENDING_REVIEW`, run submit-review again — the Console button becomes *Switch review candidate to v⟨new⟩*. This explicitly re-pins the review to the newest cut and re-runs the precheck. Re-submitting with an unchanged candidate is an idempotent no-op; if the precheck fails, the previous candidate stays under review.

There is no email notification today.

## 3. Admin review

An admin (or super-admin with the `APPS_MGMT` section) acts on the app via:

- `POST /api/v1/super-admin/apps/{id}/approve` with body `{ "publish": bool, "notes": string? }`
  - Status must be `PENDING_REVIEW`.
  - With `publish: false` → status becomes `APPROVED`.
  - With `publish: true` → the pinned review-candidate version is published (becomes `is_latest`) and status becomes `PUBLISHED`.
  - `review_notes`, `reviewed_at`, `reviewed_by_id` are recorded.
- `POST /api/v1/super-admin/apps/{id}/reject` — status becomes `REJECTED`. You can revise and submit again.

Reviewers verify, at minimum:

- Manifest re-validates against the schema and against the live Executa catalogue.
- Listing copy and screenshots match observed behaviour.
- *(Apps declaring `"mobile"` in `ui.form_factors`)* Every hard requirement in the [mobile adaptation checklist](/developers/apps/app-mobile) is walked through in a mobile viewport — a failed row blocks approval.

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
