---
title: "Public Share Links"
description: "Publish rendered static content to a long-lived, revocable public URL with the share.* Host API."
section: apps
slug: app-public-share
order: 15
updated: 2026-11-27
estimated_minutes: 6
category: "App UI"
---

The `share.*` Host API turns files your App already stores in [APS object storage](/developers/apps/app-ui-host-api) into a **platform-hosted, long-lived public URL**. Anyone with the link opens it in a plain browser — no Anna account, no App install, no model calls. The platform is a dumb static host: it never renders or interprets your content, so everything the page needs (viewer JS, CSS, fonts, images) must be baked into the snapshot.

Typical use: a slide-deck App renders HTML slides, uploads them with `files.*`, then publishes a share link the user can send around.

## Declare the capability

`share.*` publishes user content to the open internet, so it is one of the five [capability declarations](/developers/apps/app-manifest#capability-declarations):

```jsonc
{
  "schema": 4,
  "ui": {
    "bundle": { "format": "static-spa", "entry": "index.html", "external_origins": [] },
    "host_api": { "share": true }
  }
}
```

Calls without the declaration fail with `share_not_declared`.

## Publish

1. Write every file of the finished document to your App's own object storage (`files.upload_init` → PUT → `files.upload_finalize`). Only **finalized** objects in your own `scope=app` space can be published.
2. Call `share.publish`:

```js
const pub = await anna.share.publish({
  paths: [
    "decks/42/index.html",
    "decks/42/style.css",
    "decks/42/og.png",
  ],
  entry: "decks/42/index.html",   // must be text/html and one of paths
  title: "Q3 Product Plan",        // shell <title> + OG title
  description: "Quarterly planning deck",
  thumbnail_path: "decks/42/og.png", // optional OG image (png/jpeg/webp, in paths)
});
// pub.url → https://shares.anna.page/s/<pub_id>/
```

The platform server-side-copies each object into an immutable snapshot. The snapshot is **decoupled from your working files**: editing or deleting the originals never changes a published link.

Relative paths inside the snapshot default to the longest common directory prefix being stripped (`decks/42/index.html` → `index.html`), so relative references between your files keep working. Pass an explicit `path_map: { "<aps path>": "<relative path>" }` when you need full control.

## What the viewer sees

The public URL is a two-layer page on a dedicated share domain:

- a **platform shell** with the document title, a UGC notice naming your App, a report button and an *Open in Anna* link back to your App's store page (`?from_share=<pub_id>`) — your growth loop;
- your snapshot inside a **sandboxed iframe** (opaque origin, `connect-src 'none'`): scripts run, but cannot reach cookies, storage or the network. Append `?embed=1` to the share URL for a chrome-less variant suitable for embedding in third-party sites.

Content is never indexed (`noindex`); the OG tags make links unfurl nicely in chat apps.

## Republish, update, revoke

```js
// Same URL, new content — version is bumped atomically.
await anna.share.publish({ ...sameArgs, pub_id: pub.pub_id });

// Metadata only (never touches the snapshot).
await anna.share.update({ pub_id: pub.pub_id, title: "Q3 Plan (final)" });

// Tombstone the URL. Irreversible.
await anna.share.revoke({ pub_id: pub.pub_id });

// Everything this (user, app) has published.
const { items } = await anna.share.list({});
```

**Revocation semantics**: the shell page revalidates on every open, so a revoked link shows the tombstone immediately; cached subresources can linger in CDNs for **at most 5 minutes**. Treat that as the platform's contract when you communicate revocation to users. An optional `expires_at` (ISO 8601) auto-tombstones the link when it passes.

## Limits

| Limit | Value |
|---|---|
| Snapshot total size | ≤ 100 MB |
| Files per snapshot | ≤ 200 |
| Single file | ≤ 50 MB |
| Active publications per (user, app) | ≤ 20 |
| `share.publish` rate | ≤ 10 / user / hour |
| Quota | Snapshot bytes count against the user's APS storage quota (released on revoke / expiry) |

Allowed content types: `text/html`, `text/css`, `application/javascript`, `application/json`, `image/{png,jpeg,gif,webp,avif,svg+xml}`, `font/{woff,woff2,ttf,otf}`, `audio/mpeg`, `video/mp4`, `text/plain`. The entry must be `text/html`; SVG is allowed only as a subresource. Anything else fails with `share_type_not_allowed`.

## Abuse handling

Published pages carry a report button. Repeated reports hide a publication pending review; platform moderators can take a publication down permanently. Your App sees both states as non-`active` in `share.list`.

## Local development

`anna-app dev` (CLI ≥ 0.1.68) ships an in-memory `share.*` stub: `publish` snapshots your objects (requires `--storage aps` with a real account — the same mode you needed to write them) and serves the result from the harness origin at `/s/<pub_id>/…`, so the returned URL opens in your browser just like production. Publications do not survive a harness restart.

## Error codes

See the [Host API error table](/developers/apps/app-ui-host-api#error-codes) — `share_not_declared`, `share_invalid_entry`, `share_type_not_allowed`, `share_limit_exceeded`, `share_quota_exceeded`, `share_rate_limited`, `share_not_found`.
