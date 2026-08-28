---
title: "Mobile Support"
description: "Declare `form_factors`, adapt your bundle for the Anna mobile launcher, and pass the mobile review checklist."
section: apps
slug: app-mobile
order: 16
updated: 2026-08-26
estimated_minutes: 6
category: "App UI"
---

Anna Apps can run inside the Anna mobile app (iOS/Android). The mobile shell embeds the **same sandboxed iframe, SDK, and host RPC pipeline** as the desktop dashboard — your bundle runs unchanged. What changes is the container: one full-screen window at a time, a navigation stack instead of floating windows, and touch instead of mouse.

The mobile launcher only shows apps that **declare** mobile support. Nothing about your app changes on desktop when you opt in.

## Declaring mobile support

Add `form_factors` to the `ui` section of your manifest:

```jsonc
{
  "schema": 2,
  "ui": {
    "form_factors": ["desktop", "mobile"],
    "bundle": { "entry": "index.html" },
    "views": [
      {
        "name": "main",
        "title": "Main",
        "default": true,
        "entry": "index.html",
        // Optional: a mobile-specific entry. Defaults to `entry` —
        // a single responsive entry is recommended.
        "mobile_entry": "mobile.html"
      }
    ]
  }
}
```

- `form_factors` — list of `"desktop"` / `"mobile"`. **Defaults to `["desktop"]`**: existing apps never appear in the mobile launcher until they opt in.
- `views[].mobile_entry` — optional per-view mobile entry HTML. When the window is opened from a mobile container, the platform serves `mobile_entry` instead of `entry`. Prefer a single responsive entry; use `mobile_entry` only when your desktop UI is too heavy to adapt.

Declaring `"mobile"` affects three surfaces: the Anna mobile launcher lists your app, the App Store shows a "📱 Mobile ready" badge, and reviewers apply the mobile checklist below.

## Adaptation requirements (review-enforced)

Apps that declare `"mobile"` are checked against every row of this table during review, in a mobile viewport. Each row lists how a reviewer verifies it — use the same method yourself before submitting.

| Requirement | How it is verified |
|---|---|
| **Responsive layout usable at ≥ 320 px width** | DevTools iPhone SE (320×568) viewport walkthrough: no horizontal scrolling, no clipped controls, core flows completable |
| **Safe-area handling** — pad with `env(safe-area-inset-*)` or the shell-injected `--anna-safe-area-*` CSS variables | Grep the bundle for either token + notch-device walkthrough (content must not sit under the status bar / home indicator). The variables are `0` on desktop, so applying them is always safe |
| **Touch targets ≥ 44×44 pt** | Spot-check the primary action buttons and list-row controls |
| **No hover-only interactions** | Grep the bundle for `:hover`; every hover-revealed action needs a touch-reachable equivalent (visible button, long-press, or menu) |
| **No dependence on multi-window / window-geometry host APIs** | The mobile shell is a single-window stack. `window.open_view` works (it pushes onto the stack), but layouts that assume side-by-side windows or call geometry methods (move/resize) must degrade gracefully — geometry calls are no-ops on mobile |
| **Do not override the shell-injected `viewport` meta** | Grep the bundle HTML for `<meta name="viewport"` — remove your own; the mobile shell injects the correct one |

## Testing without a device

The mobile shell is a plain nexus page. From a desktop browser you can exercise the full mobile RPC path:

1. Open the app once from the dashboard (or `POST /api/v1/anna-apps/runtime/windows`) and note the `window_uuid`.
2. Load `/api/v1/anna-apps/runtime/mobile-shell?wid=<window_uuid>` with an `Authorization: Bearer <access token>` header on the first request (a request-interceptor extension, or `fetch` + document rewrite). The endpoint sets a scoped runtime cookie and serves the shell.
3. Use DevTools device emulation for the viewport/touch checks in the table above.

During local development, `anna-app dev` validates `form_factors` / `mobile_entry` like any other manifest field (requires CLI ≥ 0.1.50).

## Review

Reviewers treat the table above as **hard requirements** for any app declaring `"mobile"` — a failed row blocks approval the same way a broken manifest does. Apps that do not declare mobile are reviewed for desktop only and show "Desktop only" on their store page. See [Publishing an App](/developers/apps/app-publish) for the overall pipeline.

Next: [App UI Manifest](/developers/apps/app-ui-manifest) for the full `ui` field reference.
