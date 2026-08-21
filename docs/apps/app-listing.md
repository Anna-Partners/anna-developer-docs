---
title: "Listing Fields"
description: "The store-facing metadata you fill in on the Listing tab of the Developer Console."
section: apps
slug: app-listing
order: 6
updated: 2026-04-22
estimated_minutes: 4
category: "Distribution & Lifecycle"
---

The **Listing** tab of the [Developer Console](/developer) writes directly to the `AnnaApp` row. None of these fields live in the manifest — they are stored once and shared across every version of the app.

## Fields

| Field | Storage column | Required | Constraints |
|---|---|---|---|
| Name | `name` | yes | 1–120 chars |
| Slug | `slug` | yes (create only) | 3–80 chars; pattern `^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$` (no leading/trailing hyphen); globally unique; **immutable after creation** |
| Category | `category` | yes | One of: `productivity`, `developer-tools`, `creative`, `data`, `lifestyle`, `education`, `communication`, `entertainment`, `utilities` |
| Short description (tagline) | `tagline` | no | ≤160 chars |
| Long description | `description` | no | ≤20000 chars |
| Logo URL | `logo_url` | no | ≤500 chars. See [Logo upload](#logo-upload) for the recommended path |
| Cover URL | `cover_url` | no | ≤500 chars |
| Screenshots | `screenshots[]` | no | List of URLs, **max 6**. The Console accepts one URL per line |
| Homepage URL | `homepage_url` | no | ≤500 chars |
| Support URL | `support_url` | no | ≤500 chars |
| Privacy URL | `privacy_url` | no | ≤500 chars |

## Logo upload

The recommended way to set a logo is the **Upload logo** button, which calls `POST /api/v1/developer/apps/{id}/logo`:

- Accepts `image/jpeg`, `image/png`, `image/webp`, `image/gif`.
- Max **2 MB** raw upload.
- Server-side: EXIF-rotated, centre-cropped to a square, resized to **256×256**, encoded as **WebP** (quality 88).
- Uploaded to the platform R2 CDN; the returned `logo_url` is written back to the app and the form field.
- Requires R2 to be configured server-side; otherwise the endpoint returns 503.

You can also paste an external URL directly into the `logo_url` field; the platform will not re-host it.

## What is **not** in the listing

- **Tags** — `tags` lives inside the manifest (free-form, stored only, not surfaced in the App Store today).
- **Starter prompts**, **persona**, **default model**, **temperature**, **greeting** — none of these exist anywhere in the schema.
- **What's new / changelog** — per-version, lives on `AnnaAppVersion.changelog`, not on the app listing.

## Locking and editability

- `slug` is sent on `POST /developer/apps` and can never be changed; the Console disables the field after creation, and the `PATCH /developer/apps/{id}` endpoint silently ignores it.
- All other listing fields can be updated at any time via `PATCH /developer/apps/{id}`. Updates do not require re-review.

Next: [Publishing your app](/developers/apps/app-publish).
