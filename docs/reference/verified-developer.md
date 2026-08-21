---
title: "Verified Developer"
description: "What the Verified Developer flag unlocks, and how to activate it."
section: reference
slug: verified-developer
order: 1
updated: 2026-08-10
estimated_minutes: 3
---

**Verified Developer** is the status that lets you create and manage **Anna Apps** in the App Store. It is a single boolean on your user record (`User.is_verified_developer`), independent of email verification (`is_verified`). You can activate it yourself — see [How to activate](#how-to-activate) below.

> [\!IMPORTANT]
> Verified Developer status is required **only for publishing Anna Apps**. You can ship Executas (Tools and Skills) into the Executa Hub without it — see [Publishing a Tool](/developers/tools/executa-publish) and [Publishing a Skill](/developers/skills/skill-publish). Promoting an Executa to `visibility=public` requires a paid subscription, but not the Verified Developer flag.

## What the flag unlocks

When `is_verified_developer = true`, the platform lets you call every developer-side Anna App endpoint mounted under `/api/v1/developer/apps/*`:

- `GET    /api/v1/developer/apps` — list your apps
- `POST   /api/v1/developer/apps` — create a new app
- `PATCH  /api/v1/developer/apps/{app_id}` — edit metadata
- `POST   /api/v1/developer/apps/{app_id}/logo` — upload a square logo (≤2 MB, JPEG/PNG/WebP/GIF; auto-resized to 256×256 WebP)
- `GET    /api/v1/developer/apps/{app_id}/versions`, `POST .../versions`, `POST .../versions/{id}/publish`
- `POST   /api/v1/developer/apps/{app_id}/submit-review`
- `POST   /api/v1/developer/apps/{app_id}/archive`
- `POST   /api/v1/developer/apps/validate-manifest`

Without the flag, these endpoints return `403 Verified developer status required.`

## How to activate

Activation is **self-service and instant** — no application form, no waiting for staff:

1. Sign in and verify your email address (OAuth sign-ups are verified automatically).
2. Open the **Developer Console** (`/developer`). If you are not yet a developer you will see the activation card.
3. Read and accept the **[Developer Terms of Service](/developers/reference/developer-terms)**, optionally pick your public `developer_handle`, and click **Activate developer access**.

Behind the scenes this calls `POST /api/v1/developer/profile/activate` with your accepted ToS version. The endpoint is **browser-session only** (PATs are rejected) and records `developer_activated_at` plus the accepted `developer_tos_version` on your account.

Preconditions checked server-side:

| Check | Failure |
|---|---|
| Self-serve activation enabled on this deployment | `404` |
| Browser session (no `Authorization: Bearer`) | `403 PAT_NOT_ALLOWED` |
| Email verified | `403 EMAIL_NOT_VERIFIED` |
| Not previously revoked by an admin | `403 DEVELOPER_REVOKED` |
| ToS accepted, current version | `400 TOS_NOT_ACCEPTED` / `409 TOS_VERSION_MISMATCH` |

If self-serve activation is disabled on your deployment, status is granted manually by a platform administrator — contact platform staff through your usual channel.

## What the flag does **not** change

- It is **not** required to create or publish a Tool or Skill Executa.
- It does **not** affect ranking, trust scores, review SLAs, or quotas.
- It does **not** unlock any private API or extra runtime capability beyond the `/api/v1/developer/apps/*` surface above.
- It is independent of email verification (`is_verified`), subscription tier, and superuser status.
- The App Store "Official" badge marks **first-party** apps only; it is not tied to this flag.

## Two related fields

| Field | Type | Purpose |
|---|---|---|
| `developer_handle` | string, 2–39 chars, globally unique | Your public developer slug (e.g. `studio-acme`). Your apps publish as `@handle/slug`. Set via `PUT /api/v1/developer/profile/handle` or `anna-app account set-handle`. |
| `developer_profile` | Markdown, ≤2000 chars | Your public developer bio. |

Handles follow GitHub-username grammar (lowercase letters, digits, single hyphens), reserved words (`anna`, `official`, `admin`, …) are blocked, and renaming away from a handle freezes the old name for 90 days.

## Fair-use limits

To keep the review queue healthy, publishing is rate-limited per developer (defaults; deployments may tune them):

- App creation: 10 per day.
- Submissions for review: 5 per day.
- Active (non-archived) apps: 20 total.

## Revocation

A platform administrator can revoke the flag at any time. Revocation blocks further calls to the developer endpoints **and blocks self-service re-activation** — only an administrator can restore access. Revocation does not delete your existing apps; apps you have already published continue serving installed users until they are explicitly archived or rejected.

## Version release review

Depending on deployment configuration, publishing a **new version of an already-live app** may require an additional admin release review: the version is parked as `in release review` and goes live only after approval. Your currently-live version keeps serving users in the meantime. The CLI and Developer Console surface this state on the version row.
