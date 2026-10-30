---
title: "App UI Browser Permissions: Microphone, Camera, Fullscreen & More"
description: "Declare the browser features (Permissions Policy) your App iframe needs — microphone, camera, fullscreen, wake lock — with ui.browser_permissions; how the host delegates them, what is implied, and how to debug 'not allowed in this document'."
section: apps
slug: app-ui-browser-permissions
order: 18
updated: 2026-10-23
estimated_minutes: 6
category: "App UI"
---

Your App runs inside a sandboxed iframe on the Anna Dashboard. Browser
features such as `getUserMedia` (microphone / camera), `requestFullscreen`,
the Screen Wake Lock API or `navigator.clipboard.read()` are governed by the
browser's **Permissions Policy**, and the host denies every one of them
unless your manifest asks for it. This is a different layer from the
[Host API](/developers/apps/app-ui-host-api):

| Layer | What it controls | Who enforces it | Where you declare it |
|---|---|---|---|
| Host API ACL | Which host functions your bundle may call (`anna.audio.transcribe`, `anna.llm.complete`, …) — billing, quotas, server-side grants | Anna host (RPC dispatcher) | `ui.host_api.<namespace>: [method, …]` |
| Browser permissions | Which **Web APIs** your iframe document may use (`getUserMedia`, `requestFullscreen`, `wakeLock.request`, …) | The **browser**, via the iframe `allow` attribute and the bundle's `Permissions-Policy` response header | `ui.browser_permissions: [feature, …]` |

`microphone` is not a host function — the host does not *provide* a
microphone, it only decides whether to delegate the browser feature to your
document. That is why it has its own field instead of living inside
`ui.host_api.audio`.

## Declaring features

```json
{
  "ui": {
    "bundle": { "entry": "index.html" },
    "host_api": { "audio": ["speak", "transcribe"] },
    "browser_permissions": ["microphone"]
  }
}
```

`ui.browser_permissions` is an optional list (default `[]`). Values must come
from the allow-list below; duplicates and unknown values fail
`anna-app validate` and publish with the same message
(`browser_permissions contains an unsupported feature: ['payment']`).

| Feature | Tier | Browser still prompts the user? | Shown to users at install / review | Typical use |
|---|---|---|---|---|
| `microphone` | privacy | yes (`getUserMedia` prompt) | `device.microphone` | recording for `audio.transcribe`, voice input |
| `camera` | privacy | yes | `device.camera` | QR scanning, photo capture (desktop; see mobile note) |
| `geolocation` | privacy | yes | `device.geolocation` | location-aware features |
| `display-capture` | privacy | yes (picks a window / screen) | `device.screen` | screen recording / sharing |
| `clipboard-read` | privacy | yes (Chromium prompt) | `clipboard.read` | paste images / rich text |
| `fullscreen` | capability | no (needs a user gesture) | — | presentations, players |
| `autoplay` | capability | no | — | music / video apps resuming playback |
| `picture-in-picture` | capability | no | — | players |
| `screen-wake-lock` | capability | no | — | presentations, playback, timers |
| `web-share` | capability | no (needs a user gesture) | — | system share sheet |

Everything else (`payment`, `usb`, `midi`, `xr-spatial-tracking`,
`publickey-credentials-get`, `sync-xhr`, motion sensors) is rejected.
`clipboard-write` needs no declaration — the browser's default already allows
it for your same-origin document.

**Privacy-tier** features appear in the App's permission summary (install
consent, App detail, reviewer view) as the codes above, whether you declared
them explicitly or they were implied (below). Reviewers may ask you to
explain their use in your listing description.

## What the host does with it

For every effective feature the host opens **two gates**, from the same
server-side computation, so they can never disagree:

1. the outer iframe gets `allow="microphone 'src'; fullscreen 'src'"` (`'src'`
   = your App document);
2. the bundle assets are served with
   `Permissions-Policy: microphone=(self), fullscreen=(self), camera=(), …`.

Undeclared features stay `()` — the browser rejects the API call *before*
asking the user, with `NotAllowedError: Permission denied` and a console line
`Permissions policy violation: microphone is not allowed in this document`.
The iframe `sandbox` attribute is unrelated and is never changed by this
field.

## Implied grants

Two existing declarations keep implying features so published Apps do not
change behaviour. Declaring the feature explicitly as well is allowed and
recommended for clarity:

| You declare | Implied browser permission |
|---|---|
| `"host_api": { "audio": ["session"] }` ([realtime voice session](/developers/apps/app-ui-audio-session)) | `microphone` — the session captures the mic inside your iframe |
| `"csp_overrides": { "frame-src": ["https://www.youtube.com"] }` ([embedded players](/developers/apps/app-ui-bundle)) | `autoplay`, `encrypted-media`, `fullscreen`, `picture-in-picture` — for your document **and** the declared embed origins, so the nested player can be re-delegated the feature |

`"audio": ["transcribe"]` does **not** imply the microphone: transcription can
run on uploaded files or URLs, so recording is a separate decision you make
with `"browser_permissions": ["microphone"]`.

## Checking at runtime

Gate your UI so a missing permission degrades gracefully instead of throwing:

```js
function featureAllowed(name) {
  const policy = document.permissionsPolicy ?? document.featurePolicy;
  return policy ? policy.allowsFeature(name) : true;
}

micButton.disabled = !featureAllowed('microphone');
micButton.title = micButton.disabled
  ? 'Add "microphone" to ui.browser_permissions in manifest.json'
  : '';
```

## Local development

`anna-app dev` (CLI ≥ 0.1.63) applies the same two gates as production: the
harness iframe's `allow` and the dev bundle's `Permissions-Policy` header come
from the runtime, so an App that records without declaring `microphone` fails
locally exactly as it fails on the Dashboard.

`anna-app validate` scans your bundle for the governed APIs and warns when the
matching feature is neither declared nor implied:

```
⚠ browser-permissions: bundle/voice.js: bundle calls getUserMedia / MediaRecorder but "microphone" or "camera" is not declared in ui.browser_permissions — the Dashboard will deny it (Permissions-Policy)
```

It is a warning (not an error, even with `--strict`) because the scan is a
text heuristic.

## Mobile

Inside the Anna mobile app your bundle runs in a native WebView, not an
iframe, so the `Permissions-Policy` header is the only gate — the same
declaration works. `microphone` is supported (the OS prompt appears on the
first `getUserMedia`). `camera` via `getUserMedia` is **not yet available on
mobile** — it is denied regardless of the declaration; use the host-mediated
`mobile.camera_capture` method instead (see
[App Mobile](/developers/apps/app-mobile)).

## Troubleshooting

`Permissions policy violation: X is not allowed in this document`

1. Open the manifest the Dashboard is actually running (the published
   version, not your working copy) and confirm `X` is in
   `ui.browser_permissions` or implied as above.
2. In DevTools, inspect the App iframe: the `allow` attribute must contain
   `X 'src'`; the Network response for your entry HTML must contain
   `X=(self)` in `Permissions-Policy`. If either is missing, the running
   version predates your manifest change — republish.
3. If both are present and the call still fails, the **user** denied the
   browser prompt — reset it from the site information panel in the address
   bar.
