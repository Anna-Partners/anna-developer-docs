---
title: "App UI Bundle Pipeline"
description: "Upload your static SPA bundle for a schema-2 Anna App version: init, file PUTs, finalize."
section: apps
slug: app-ui-bundle
order: 11
updated: 2026-04-28
estimated_minutes: 5
category: "App UI"
---

A `schema: 2` Anna App version is bound 1:1 to an immutable **bundle** — the static assets your iframe loads. This page covers the upload pipeline. The bundle is stored in R2 under `anna-app-bundles/<env>/<slug>/<version>/<relative_path>` and served at `GET /anna-apps/{slug}/{version}/{path}` with per-bundle CSP and `Cache-Control: public, max-age=31536000, immutable`.

## Quotas

Enforced at `bundle/init`:

| Limit | Value |
|---|---|
| Total bundle size | **50 MB** |
| File count | **2,000** |
| Per-file size | **10 MB** |
| Path safety | No `..`, no `\`, no `//`, no leading `/`, must match `^[A-Za-z0-9_./\-]+$` |

Allowed `content_type` values (`ALLOWED_BUNDLE_CONTENT_TYPES`):

```
text/html, text/css, text/plain
application/javascript, text/javascript, application/json
application/wasm
image/png, image/jpeg, image/gif, image/webp, image/svg+xml, image/avif
font/woff, font/woff2, application/font-woff, application/font-woff2,
font/ttf, font/otf, application/octet-stream (fonts only)
audio/mpeg, audio/wav, audio/ogg
video/mp4, video/webm
```

## Status machine

```
        bundle/init
draft ───────────────► draft
                         │
              all files PUT successfully + sha256/byte_size match
                         │
                         ▼
                    bundle/finalize
                         │
                         ▼
                   bundle_ready (immutable)
```

Once `bundle_ready`, the bundle cannot be edited. Ship a new version to change assets.

## Step 1 — `bundle/init`

```http
POST /api/v1/developer/apps/{app_id}/versions/{version_id}/bundle/init
Content-Type: application/json

{
  "file_map": {
    "index.html": {
      "byte_size": 8421,
      "sha256":    "ab12...",
      "content_type": "text/html"
    },
    "assets/app.js": {
      "byte_size": 92314,
      "sha256":    "cd34...",
      "content_type": "application/javascript"
    },
    "assets/app.css": {
      "byte_size": 1244,
      "sha256":    "ef56...",
      "content_type": "text/css"
    }
  }
}
```

Response:

```jsonc
{
  "bundle_id": "01J...",
  "status": "draft",
  "files": [
    {
      "relative_path": "index.html",
      "byte_size": 8421,
      "sha256": "ab12...",
      "content_type": "text/html",
      "presigned_put_url": "https://r2.example.com/...?X-Amz-Signature=...",  // 10-min TTL
      "proxy_upload_url":  "/api/v1/developer/apps/{app_id}/versions/{version_id}/bundle/file?path=index.html"
    },
    …
  ]
}
```

You have **two ways** to upload each file:

1. **Direct PUT** to `presigned_put_url` (recommended; bypasses Nexus). Set `Content-Type` to the value you declared in `file_map`.
2. **Proxy upload** — `multipart/form-data` POST to `proxy_upload_url` with field `file=<binary>`. Use this when your network blocks the R2 endpoint.

If you need to retry, just call `bundle/init` again on the same version with the same `file_map`; the existing draft is replaced.

## Step 2 — `bundle/finalize`

After every file is in R2, finalize:

```http
POST /api/v1/developer/apps/{app_id}/versions/{version_id}/bundle/finalize
```

The backend runs:

1. `HEAD` each R2 object — confirms it exists.
2. Re-checks `byte_size` and (if R2 returned `x-amz-checksum-sha256`) the `sha256`.
3. Confirms `manifest.ui.bundle.entry` is present in the uploaded set.
4. Marks `status = bundle_ready` and stamps `finalized_at`.

Failure modes:

| HTTP / payload | Meaning |
|---|---|
| `409 bundle_already_finalized` | Already `bundle_ready`; nothing to do |
| `412 file_missing` (`{path}`) | File not yet uploaded to R2 |
| `412 sha256_mismatch` (`{path}`) | The R2 object's checksum disagrees with the declared `sha256`; re-upload |
| `412 entry_not_in_bundle` | `manifest.ui.bundle.entry` references a path you didn't upload |

## Step 3 — Inspect

```http
GET /api/v1/developer/apps/{app_id}/versions/{version_id}/bundle
```

Returns the full `BundleDetail`:

```jsonc
{
  "bundle_id": "01J...",
  "status": "bundle_ready",
  "total_bytes": 102109,
  "file_count": 3,
  "finalized_at": "2026-04-28T08:14:29Z",
  "files": [
    { "relative_path": "index.html", "byte_size": 8421, "sha256": "ab12...", "content_type": "text/html" },
    …
  ]
}
```

## Step 4 — Publish the version

Only after `status == bundle_ready` may you publish. The `open_app_view` runtime call refuses to mount a window when the version's bundle is not ready (returns `bundle_not_ready`). Publishing flow itself is unchanged: see [Publishing an app](/developers/apps/app-publish).

## How assets are served at runtime

```
GET /anna-apps/{slug}/{version}/{relative_path}

Response headers:
  Content-Type: <declared>
  Content-Security-Policy: <built from manifest.ui.csp_overrides + external_origins>
  X-Content-Type-Options: nosniff
  Cross-Origin-Resource-Policy: same-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  ETag: "<sha256>"
  Cache-Control: public, max-age=31536000, immutable
```

Two extra rules apply to the entry HTML:

- The runtime requires `Sec-Fetch-Dest: iframe` on requests for the entry HTML when the header is sent (modern browsers always send it). Direct top-level navigations to the bundle URL are rejected with `403 must_be_iframed`.
- The bundle URL embeds **no authentication** — the iframe uses query params `?wid=<window_uuid>&t=<jwt>` to bootstrap, then upgrades to `postMessage` RPC.

## Local development tips

- Keep the file count low (`<200`) — every file is a separate R2 object.
- Pre-compute `sha256` with whatever your build system supports (`shasum -a 256 <file>`). The backend uses these to ETag responses.
- Reuse the same `entry` filename across versions to keep deep-links (`#/route`) stable; the version is part of the URL anyway.
- If you must skip Anna and serve directly during local dev, point the `<iframe>` at your localhost — but you lose the per-bundle CSP guarantees and the SDK will refuse `connect()` because the JWT is bound to the deployed `version_id`.

Next: [App UI SDK](/developers/apps/app-ui-sdk).
