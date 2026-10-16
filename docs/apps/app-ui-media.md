---
title: "App UI Media: Video & Audio"
description: "Generate video (async jobs), synthesize speech and transcribe audio from your bundle through the host — grants, catalogue discovery, CU pre-charge, media_job events and URL lifetime."
section: apps
slug: app-ui-media
order: 16
updated: 2026-10-14
estimated_minutes: 8
category: "App UI"
---

Three Host API namespaces let an App bundle use the platform's media stack
**without holding any provider key, storage credential or billing account**:

| Namespace | Methods | Shape | Billing (request type) |
|---|---|---|---|
| `anna.video.*` | `generate`, `getJob`, `cancelJob`, `listJobs` (+ SDK sugar `generateAwait`) | **async job** — returns a `jobId`, progress via `media_job` SSE events | `APP_VIDEO_GEN` — CU **pre-charged** on submit, settled / refunded at the terminal state |
| `anna.audio.*` | `speak` (TTS), `transcribe` (STT) | **synchronous** (HTTP timeout 120 s) | `APP_TTS` per character · `APP_STT` per audio second |
| `anna.audio.session()` | realtime voice session (`sendAudio` / `setContext` / `say` / events) — see [App UI Audio Session](/developers/apps/app-ui-audio-session) | **streaming** over a host-bridge-relayed WebSocket; not an RPC | `APP_STT` per recognised second · `APP_TTS` per character |
| `anna.llm.catalog` | capability discovery | synchronous | free |

Everything travels over the normal RPC envelope (`postMessage → Host Bridge →
POST /api/v1/anna-apps/runtime/rpc`, see [App UI Host API](/developers/apps/app-ui-host-api)).
Equivalent HTTP endpoints exist under `/api/v1/copilot/app/{video,audio}/…` and
`GET /api/v1/copilot/app/models` for code running outside the iframe with an
`app_session_token`. Field-level detail (every parameter, return key and error)
lives in the Reference: [`video.*`](/developers/reference/host-api-video),
[`audio.*`](/developers/reference/host-api-audio), [`llm.catalog`](/developers/reference/host-api-llm),
[`media_job`](/developers/reference/sse-events).

## Two-layer authorization

Like `image.*`, media is gated twice. Both must pass or the call fails with
`APP_NOT_GRANTED`:

1. **Manifest** — declare the method surface you use (including `llm.catalog`
   for discovery — it goes through the same ACL as every other namespace):

   ```json
   "ui": {
     "host_api": {
       "video": ["generate", "getJob", "cancelJob", "listJobs"],
       "audio": ["speak", "transcribe"],
       "llm": ["catalog"]
     }
   }
   ```

2. **User grant** — the user enables media for *your* App in Anna Admin
   (`media_grant`). Note the per-operation flags for audio:

   ```json
   "media_grant": {
     "video": { "enabled": true },
     "audio": { "enabled": true, "speak": true, "transcribe": true }
   }
   ```

   `audio.enabled` alone is **not** enough — `speak` / `transcribe` must each be
   on. Grants default to off; the review flow shows `media_grant` to the user
   alongside `image_grant`.

There is **no platform-side daily or concurrency cap**. The user's CU quota pool
is the only limit (`APP_QUOTA_EXCEEDED`, HTTP 429 on the HTTP surface).

## Discover before you call

Durations, resolutions, aspect ratios, voices and character caps differ per
model and are **catalogue-driven**. Never hard-code them — read them:

```js
const { models, quota } = await anna.llm.catalog({ serviceType: 'video_gen' });
// models[].capabilities → { duration: {min,max,default} | {values:[…]},
//                           resolutions?, aspectRatios, imageToVideo, audio }
// models[].pricing      → { unit: 'per_second', cuByResolution | cuPerSecond, minBilledSeconds? }
// models[].isUserPreferred → the user's default for this service type
// quota.remainingCU     → what the user has left

const tts = await anna.llm.catalog({ serviceType: 'tts' });
// models[].capabilities → { voices:[{id,label,category,languages}], defaultVoice,
//                           options:{speed?, format?}, maxCharsPerCall }
```

Only service types your App is **granted** are returned — an ungranted type
yields an empty list, never an error, so you can feature-detect and degrade.
Passing parameters outside a model's capability space fails with
`VIDEO_INVALID_REQUEST` / `AUDIO_VOICE_INVALID` / `AUDIO_TEXT_TOO_LONG`, each
echoing the allowed space in `error.data.allowed`.

## Video: async jobs

`video.generate` returns within ~1 s. The host validates against the
catalogue, **holds `estimatedCostCU`** from the user's quota, submits to the
provider queue and persists the job. From there:

```
generate ──► queued ──► running ──► succeeded   (hold settled → billedCostCU)
                │          │
                │          └─────► failed      (hold fully refunded)
                └─ cancelJob ────► cancelled   (hold fully refunded)
running ─ cancelJob ─► provider cancel; if already rendering → {state:'running', cancelPending:false}, no refund
```

Progress arrives as `media_job` SSE events
(`payload = {jobId, seq, state, progress?:{phase, queuePosition}, result?, billedCostCU?}`,
`seq` strictly monotonic — drop out-of-order frames). **Events are an
accelerator; `getJob` is the truth.** The SDK combines both:

```js
const job = await anna.video.generateAwait({
  prompt: 'Aerial drone shot over a misty pine forest at sunrise',
  durationSec: 5, resolution: '768p', aspectRatio: '16:9',
  clientTag: 'scene-3-broll',
}, {
  onProgress: (p) => status.textContent = `${p.state} · queue ${p.progress?.queuePosition ?? '-'}`,
  signal: abortController.signal,        // → video.cancelJob
  timeoutMs: 10 * 60 * 1000,
});

videoEl.src = job.result.url;            // presigned R2 GET, ~30 min TTL
videoEl.onerror = async () => { videoEl.src = await job.result.refreshUrl(); };
```

Image-to-video: pass `imageUrl` (an `https` URL — R2 presigned URLs and
`web.image_fetch` products work) on a model whose `capabilities.imageToVideo` is
true; `aspectRatio` then follows the image.

### Reload recovery

An iframe reload loses in-memory job handles. On start-up:

```js
const { jobs } = await anna.video.listJobs({ state: 'running' });
for (const j of jobs) resumeTracking(j.jobId, j.clientTag);   // subscribe + poll
```

`clientTag` (≤120 chars, set on `generate`) is how you map jobs back to your own
entities (scenes, timeline clips).

## Audio: synchronous TTS and STT

```js
// TTS — voices come from the catalogue, never from a hard-coded list
const cat = await anna.llm.catalog({ serviceType: 'tts' });
const model = cat.models.find(m => m.isUserPreferred) ?? cat.models[0];
const out = await anna.audio.speak({
  text: 'Welcome to Timeline Studio.',
  voice: model.capabilities.defaultVoice,
  format: 'mp3',                // or 'wav'
  delivery: 'url',              // 'inline' → audioBase64 for products ≤ 1 MB
});
new Audio(out.url).play();      // ~30 min TTL; out.model tells you who spoke

// STT — whole recording, ≤ 10 min
const blob = new Blob(chunks, { type: 'audio/webm' });
const b64 = btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
const { text } = await anna.audio.transcribe({ audioBase64: b64, format: 'webm', language: 'zh' });
```

Limits: `text` ≤ the model's `maxCharsPerCall` (1000–2000 depending on tier);
`speed` 0.5–2.0; inline audio ≤ 10 MB, URL fetch ≤ 25 MB, duration ≤ 10 min.
Knobs a model does not support (e.g. `speed` on ElevenLabs, `timestamps` on
Qwen) are ignored and never surcharged. Split long narration into sentences —
quality-tier TTS synthesizes roughly 16 characters per second.

> **Need streaming?** Live ASR with partial results, streaming TTS and barge-in
> are the **realtime voice session** — `anna.audio.session()`, declared as
> `"audio": ["session"]` and relayed by the host page rather than sent as an
> RPC. See [App UI Audio Session](/developers/apps/app-ui-audio-session). The
> synchronous `audio.speak` will **never** change shape to return a `jobId`; a
> long-form API would arrive as a separate `audio.speakAsync`.

## URL lifetime and durable storage

All media results (`result.url`, `audio.speak` `url`, URLs inside `media_job`
events) are presigned R2 GETs with a **~30 min TTL** (`expiresIn`). Rules:

- Never persist a presigned URL. On a 403 during playback, call `video.getJob`
  (or `job.result.refreshUrl()`) to re-sign.
- To keep a result, fetch the bytes and store them through
  [`upload.negotiate` / `upload.confirm`](/developers/reference/host-api-upload) — this
  counts toward your App's storage quota and is the "import into asset library"
  path.
- Video objects are cleaned up 7 days after the terminal state; job rows are
  kept 30 days for billing (`getJob` still answers, without `result.url`).
- CSP: allow the host's R2 hostname (`https:`) in `media-src` / `img-src` so
  `<video>` / `<audio>` elements can load the URLs.

## Error reference

Every error's `data` carries `{errorName, retryable, docs}` and, for validation
errors, `allowed`.

| Code | Name | When |
|---|---|---|
| `-32001` | `APP_NOT_GRANTED` | manifest surface missing **or** user `media_grant` flag off |
| `-32015` | `APP_QUOTA_EXCEEDED` | CU pool exhausted (HTTP 429) |
| `-32122` | `VIDEO_INVALID_REQUEST` | video params outside the catalogue; also the generic validator for audio shapes (empty text, bad format/delivery/speed) |
| `-32123` | `VIDEO_PROVIDER_ERROR` | provider submit/render failure — hold refunded, retryable |
| `-32124` | `VIDEO_MODEL_UNAVAILABLE` | no routable video model / unknown hint |
| `-32125` | `VIDEO_JOB_NOT_FOUND` | unknown or foreign `jobId` |
| `-32126` | `VIDEO_JOB_NOT_CANCELLABLE` | job already terminal |
| `-32128` | `VIDEO_CONTENT_REJECTED` | moderation rejected prompt/image — not billed |
| `-32142` | `AUDIO_TEXT_TOO_LONG` | over `maxCharsPerCall` (`data.allowed.maxCharsPerCall`) |
| `-32143` | `AUDIO_TOO_LONG` | recording > 10 min / > 25 MB |
| `-32144` | `AUDIO_PROVIDER_ERROR` | TTS/STT provider failure — retryable |
| `-32145` | `AUDIO_VOICE_INVALID` | unknown voice (`data.allowed` = valid voices) |
| `-32146` | `AUDIO_MODEL_UNAVAILABLE` | no routable TTS/STT model |
| `-32147` | `AUDIO_CONTENT_REJECTED` | moderation rejected the text — not billed |

Executa plugins get the same capabilities through reverse RPC
(`video/generate`, `video/get_job`, `video/cancel_job`, `audio/speak`,
`audio/transcribe`) with plugin-side gates (`host_capabilities`, `media_token`, per-invoke budgets) —
see [Executa media](/developers/tools/executa-media).

## See also

- [App UI Host API](/developers/apps/app-ui-host-api) — envelope, ACL model, generic error codes
- [App UI Manifest](/developers/apps/app-ui-manifest) — `ui.host_api.video` / `.audio` grant table
- [App UI Audio Session](/developers/apps/app-ui-audio-session) — realtime voice: streaming ASR / TTS, barge-in, `setContext`, `say`
- [Executa media](/developers/tools/executa-media) — the plugin-side mirror
- Reference: [`video.*`](/developers/reference/host-api-video) · [`audio.*`](/developers/reference/host-api-audio) · [`media_job`](/developers/reference/sse-events)
