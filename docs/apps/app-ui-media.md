---
title: "App UI Media: Video, Music & Audio"
description: "Generate video and music (async jobs), synthesize speech and transcribe audio from your bundle through the host — grants, catalogue discovery, CU pre-charge, idempotency, media_job events and URL lifetime."
section: apps
slug: app-ui-media
order: 16
updated: 2026-10-23
estimated_minutes: 10
category: "App UI"
---

Four Host API namespaces let an App bundle use the platform's media stack
**without holding any provider key, storage credential or billing account**:

| Namespace | Methods | Shape | Billing (request type) |
|---|---|---|---|
| `anna.video.*` | `generate`, `getJob`, `cancelJob`, `listJobs` (+ SDK sugar `generateAwait`) | **async job** — returns a `vjob_…` id, progress via `media_job` SSE events | `APP_VIDEO_GEN` — CU **pre-charged** on submit, settled / refunded at the terminal state |
| `anna.music.*` | `generate`, `getJob`, `cancelJob`, `listJobs` (+ `generateAwait`) | **async job** — returns a `mjob_…` id, same `media_job` events; `idempotencyKey` replay within 24 h | `APP_MUSIC_GEN` — pre-charged per song / per second / per started minute (model's billing unit), settled / refunded |
| `anna.audio.*` | `speak` (TTS), `transcribe` (STT) | **synchronous** (HTTP timeout 120 s) | `APP_TTS` per character · `APP_STT` per audio second |
| `anna.audio.session()` | realtime voice session (`sendAudio` / `setContext` / `say` / events) — see [App UI Audio Session](/developers/apps/app-ui-audio-session) | **streaming** over a host-bridge-relayed WebSocket; not an RPC | `APP_STT` per recognised second · `APP_TTS` per character |
| `anna.llm.catalog` | capability discovery | synchronous | free |

Everything travels over the normal RPC envelope (`postMessage → Host Bridge →
POST /api/v1/anna-apps/runtime/rpc`, see [App UI Host API](/developers/apps/app-ui-host-api)).
Equivalent HTTP endpoints exist under `/api/v1/copilot/app/{video,music,audio}/…` and
`GET /api/v1/copilot/app/models` for code running outside the iframe with an
`app_session_token`. Field-level detail (every parameter, return key and error)
lives in the Reference: [`video.*`](/developers/reference/host-api-video),
[`music.*`](/developers/reference/host-api-music), [`audio.*`](/developers/reference/host-api-audio), [`llm.catalog`](/developers/reference/host-api-llm),
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
       "music": ["generate", "getJob", "cancelJob", "listJobs"],
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
     "music": { "enabled": true },
     "audio": { "enabled": true, "speak": true, "transcribe": true }
   }
   ```

   `audio.enabled` alone is **not** enough — `speak` / `transcribe` must each be
   on. Grants default to off; the review flow shows `media_grant` to the user
   alongside `image_grant`.

There is **no platform-side daily or concurrency cap**. The user's CU quota pool
is the only limit (`APP_QUOTA_EXCEEDED`, HTTP 429 on the HTTP surface).

## Discover before you call

Durations, resolutions, aspect ratios, lyrics support, output formats, voices
and character caps differ per model and are **catalogue-driven**. Never hard-code them — read them:

```js
const { models, quota } = await anna.llm.catalog({ serviceType: 'video_gen' });
// models[].capabilities → { duration: {min,max,default} | {values:[…]},
//                           resolutions?, aspectRatios, imageToVideo, audio }
// models[].pricing      → { unit: 'per_second', cuByResolution | cuPerSecond, minBilledSeconds? }
// models[].isUserPreferred → the user's default for this service type
// quota.remainingCU     → what the user has left

const music = await anna.llm.catalog({ serviceType: 'music_gen' });   // see “Music: async jobs”

const tts = await anna.llm.catalog({ serviceType: 'tts', voiceLanguage: 'zh' }); // voiceLanguage optional
// models[].capabilities → { voices:[{id,label,category,languages,gender?,accent?,age?,tags?}],
//                           defaultVoice, maxCharsPerCall, timestamps?,
//                           options: { <key>: { type:'range'|'select'|'boolean'|'text',
//                                               min?,max?,step?,values?,default,scope,label?,help? } } }
// models[].pricing      → { unit: 'per_1k_chars', cuPer1kChars }
// models[].isPlatformDefault → who the host routes to when the user has no preference
```

`options` is a **self-describing schema** — every knob a model accepts (`speed`,
`pitch`, `volume`, `instruction`, `stability`, `similarity_boost`, `style`, `vol`,
`emotion`, `language`, `timestamps`, `format`, …) with its type, range and
default. Render it generically; keys differ per model (ElevenLabs exposes
`stability` but not `pitch`; Qwen-Audio-TTS exposes `instruction`; MiniMax
exposes `vol` −12..12 `pitch` and `emotion`). The default model is
`models.find(m => m.isUserPreferred) ?? models.find(m => m.isPlatformDefault)`.

Only service types your App is **granted** are returned — an ungranted type
yields an empty list, never an error, so you can feature-detect and degrade.
Passing parameters outside a model's capability space fails with
`VIDEO_INVALID_REQUEST` / `AUDIO_VOICE_INVALID` / `AUDIO_TEXT_TOO_LONG` /
`AUDIO_OPTION_INVALID`, each echoing the allowed space in `error.data.allowed`
(option errors also carry `data.key` and `data.reason ∈ out_of_range | not_allowed | too_long | type`).

Image models (`serviceType: 'image_gen' | 'image_edit'`) use the same `options`
schema (`size`, `aspect_ratio`, `resolution`, `quality`, `n`, `output_format`, …) —
see [App UI Host API → image](/developers/apps/app-ui-host-api#image).

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

## Music: async jobs

`music.generate` is the **same kind of surface as video in a different
modality**: it shares the job table, the `media_job` events, the
pre-charge → settle → refund state machine and the 30-min URL rule. Two
things are music-specific:

1. **Models differ a lot, and the host never downgrades silently.** Lyrics vs.
   instrumental-only, model-decided vs. caller-set length, `mp3` vs. `wav`,
   reference image — read it from the catalogue and build your form from it:

   ```js
   const { models } = await anna.llm.catalog({ serviceType: 'music_gen' });
   // capabilities: lyrics, lyricsMode ('field' | 'prompt_embedded'), lyricsMaxChars,
   //   instrumentalOnly, duration ({type:'fixed', typicalMaxSec} | {type:'range', min, max, default}),
   //   formats, defaultFormat, referenceImage, promptMinChars, promptMaxChars, options
   // pricing: cuPerSong | cuPerSecond | cuPerMinute (+ roundUp)
   ```

   A field the resolved model cannot honour fails with
   `MUSIC_FEATURE_UNSUPPORTED` (`-32165`) and `data.alternatives` listing models
   that can — offer the switch to the user instead of guessing.

2. **Idempotency.** Pass `idempotencyKey` (≤64 chars `[A-Za-z0-9_\-:.]`). The
   same key within 24 h (same user + App) returns the existing job with
   `idempotentReplay: true` and is **never charged twice** — this is how a
   "Generate" button survives double-clicks and iframe reloads.

```js
const song = await anna.music.generateAwait({
  prompt: 'melancholic cinematic piano, slow ~70 BPM, rainy night',
  lyrics: model.capabilities.lyrics ? lyricsTextarea.value : undefined,
  instrumental: !model.capabilities.lyrics,
  durationSec: model.capabilities.duration.type === 'range' ? 45 : undefined,
  model: model.modelName,
  clientTag: 'scene-3-score',
  idempotencyKey: `scene-3-score-v${version}`,
}, {
  onProgress: (p) => status.textContent = `${p.state} · queue ${p.progress?.queuePosition ?? '-'}`,
  signal: abortController.signal,        // → music.cancelJob
  timeoutMs: 10 * 60 * 1000,
});

audioEl.src = song.result.url;           // presigned R2 GET, ~30 min TTL
audioEl.onerror = async () => { audioEl.src = await song.result.refreshUrl(); };
// song.result.{mimeType, durationSec, lyrics?, seed?}; song.billedCostCU
```

`music.listJobs` / `music.getJob` / `music.cancelJob` mirror their video
counterparts exactly (reload recovery via `listJobs({state:'running'})`,
`clientTag` correlation, full refund when cancelled while `queued`). Music and
video job lists are separate — `music.listJobs` never returns `vjob_…` ids.
Catalogue entries may carry a `licenseNote`; surface it before commercial use.

## Image: async jobs & re-signing

`anna.image.generate` / `anna.image.edit` stay **synchronous and unchanged** —
a 0.5K single image is back in ~5 s and that path is the right default. Two
things used to be impossible on the image line and are now additive opt-ins
(`@anna-ai/app-runtime` ≥ 0.25.0, dispatcher 0.29.0; manifest `ui.host_api.image`
must list the new method names; the existing `image_grant` applies — no new grant):

1. **Jobs for long renders.** 2K/4K or `quality: "high"` images take 60–120 s;
   held open in a sync call they time out and are lost on reload — while the
   user has already been charged. `image.generateAsync` / `image.editAsync`
   take the **same body** as the sync methods plus `clientTag?` /
   `idempotencyKey?` and return an `ijob_…` immediately. The job shares the
   video / music table, `media_job` events (`kind: "image"`), the
   pre-charge → settle → refund machine (one job = one user action = `n`
   images; CU is held for `n` and **settled on the actual count**), the
   24 h `idempotencyKey` replay, `image.listJobs` reload recovery
   (`listJobs({state:'running'})` then `image.getJob` for fresh URLs) and
   `image.cancelJob` (queued = full refund). Validation and error codes are **byte-identical** to
   the sync path.

   ```js
   const job = await anna.image.generateAwait({
     prompt: 'art-deco poster of Mars', n: 2,
     model: 'fal-ai/nano-banana-2', aspect_ratio: '9:16', params: { resolution: '4K' },
     clientTag: 'poster-v3', idempotencyKey: `poster-v3:${attempt}`,
   }, {
     onProgress: (p) => status.textContent = `${p.state} · queue ${p.queuePosition ?? '-'}`,
     signal: abortController.signal,            // → image.cancelJob
   });
   for (const im of job.result.images) gallery.add(im.url, im.r2Key);   // url ≈ 30 min; r2Key → resign
   job.billedCostCU;                            // ≤ estimatedCostCU (settled on actual output)
   // editAwait({ image_url, mask_url?, prompt, … }) is the edit twin.
   ```

2. **Re-signing already-paid artifacts.** Every image result — sync
   `images[].r2_key` or job `result.images[].r2Key` — can be re-signed for the
   object's 7-day lifetime with `anna.image.resign({ r2Keys })`
   (`{ urls: [{ r2Key, url, expiresIn }] }`, input order), so a refreshed tab or
   a failed first download no longer means a lost, already-billed image.
   `image.getJob` re-signs every URL in the view as well. One key that is not
   yours (or malformed) fails the **whole call** with `IMAGE_ASSET_NOT_FOUND`
   (`data.index`) — never partial success.

   ```js
   img.onerror = async () => {
     const { urls } = await anna.image.resign({ r2Keys: [img.dataset.r2Key] });
     img.src = urls[0].url;
   };
   ```

`anna.llm.catalog({ serviceType: 'image_gen' | 'image_edit' })` entries carry
`capabilities.jobs: true` and `image_edit` entries now report the real
`options.n.max` (= your `image_grant.maxPerCallEdit`). Behaviour change on the
sync path: a provider safety rejection is `IMAGE_CONTENT_REJECTED` (`-32115`,
HTTP 400) instead of `APP_PROVIDER_ERROR`.

## Audio: synchronous TTS and STT

```js
// TTS — voices come from the catalogue, never from a hard-coded list
const cat = await anna.llm.catalog({ serviceType: 'tts' });
const model = cat.models.find(m => m.isUserPreferred) ?? cat.models[0];
const out = await anna.audio.speak({
  text: 'Welcome to Timeline Studio.',
  model: model.modelName,       // optional; omitted → user preference → platform default
  voice: model.capabilities.defaultVoice,
  format: 'mp3',                // must be in options.format.values for that model
  delivery: 'url',              // 'inline' → audioBase64 for products ≤ 1 MB
  params: { stability: 0.3, similarity_boost: 0.8 },   // any key from capabilities.options
});
new Audio(out.url).play();      // ~30 min TTL; out.model tells you who spoke
out.params;                     // what actually reached the provider, normalised
out.ignoredParams;              // keys this model does not declare — dropped, never surcharged

// STT — whole recording, ≤ 10 min. Recording INSIDE the iframe needs
// "browser_permissions": ["microphone"] in manifest.ui — `transcribe` alone
// does not grant the mic (see /developers/apps/app-ui-browser-permissions).
const blob = new Blob(chunks, { type: 'audio/webm' });
const b64 = btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
const { text } = await anna.audio.transcribe({ audioBase64: b64, format: 'webm', language: 'zh' });
```

> **Recording in the iframe?** `getUserMedia` / `MediaRecorder` are governed
> by the browser's Permissions Policy, not by `host_api`. Declare
> `"browser_permissions": ["microphone"]` in `manifest.ui` or the Dashboard
> rejects the call with `NotAllowedError` before the user is even asked
> (`transcribe` accepts uploaded files / URLs too, so it does not imply the
> microphone). Details: [App UI Browser Permissions](/developers/apps/app-ui-browser-permissions).

Limits: `text` ≤ the model's `maxCharsPerCall` (1000–2000 depending on tier);
inline audio ≤ 10 MB, URL fetch ≤ 25 MB, duration ≤ 10 min. Per-model knobs are
validated against `capabilities.options` — a value outside its range/enum fails
with `AUDIO_OPTION_INVALID` (`data.{key, reason, allowed}`). Knobs a model does
not declare (e.g. `pitch` on ElevenLabs, `timestamps` on Qwen) are dropped,
listed in `ignoredParams`, and never surcharged. The legacy top-level
`speed` / `language` / `timestamps` / `format` fields still work and are merged
into `params` (explicit `params` wins). Split long narration into sentences —
quality-tier TTS synthesizes roughly 16 characters per second.

**ElevenLabs on the platform.** `fal-ai/elevenlabs/tts/eleven-v3` exposes only
`stability` (upstream limitation). For the full voice-settings quartet
(`stability`, `similarity_boost`, `style`, `speed` 0.7–1.2) pick
`fal-ai/elevenlabs/tts/multilingual-v2` (quality) or
`fal-ai/elevenlabs/tts/turbo-v2.5` (latency). Try any model interactively in the
Developer Console Playground (`/developer?view=playground`).

> **Need streaming?** Live ASR with partial results, streaming TTS and barge-in
> are the **realtime voice session** — `anna.audio.session()`, declared as
> `"audio": ["session"]` and relayed by the host page rather than sent as an
> RPC. See [App UI Audio Session](/developers/apps/app-ui-audio-session). The
> synchronous `audio.speak` will **never** change shape to return a `jobId`; a
> long-form API would arrive as a separate `audio.speakAsync`.

## URL lifetime and durable storage

All media results (video / music `result.url`, `audio.speak` `url`, URLs inside `media_job`
events) are presigned R2 GETs with a **~30 min TTL** (`expiresIn`). Rules:

- Never persist a presigned URL. On a 403 during playback, call `video.getJob` /
  `music.getJob` (or `job.result.refreshUrl()`) to re-sign.
- To keep a result, fetch the bytes and store them through
  [`upload.negotiate` / `upload.confirm`](/developers/reference/host-api-upload) — this
  counts toward your App's storage quota and is the "import into asset library"
  path.
- Video and music objects are cleaned up 7 days after the terminal state; job rows are
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
| `-32161` | `MUSIC_PROVIDER_ERROR` | music provider submit/render failure — hold refunded, retryable |
| `-32162` | `MUSIC_INVALID_REQUEST` | malformed music field (prompt too short/long, non-integer `durationSec`, unknown `options` key, bad `idempotencyKey` / `referenceImageUrl`) — `data.allowed` echoes the model's space |
| `-32163` | `MUSIC_MODEL_UNAVAILABLE` | no routable text-to-music model / unknown hint |
| `-32164` | `MUSIC_JOB_NOT_FOUND` | unknown, foreign or `vjob_…` `jobId` |
| `-32165` | `MUSIC_FEATURE_UNSUPPORTED` | resolved model cannot deliver a requested feature — `data.{feature, model, alternatives}`; never downgraded silently |
| `-32166` | `MUSIC_LYRICS_TOO_LONG` | over `lyricsMaxChars` (`data.{maxChars, actualChars}`) |
| `-32167` | `MUSIC_JOB_NOT_CANCELLABLE` | music job already terminal |
| `-32168` | `MUSIC_CONTENT_REJECTED` | provider safety system rejected prompt / lyrics / image — not billed |
| `-32107` | `IMAGE_PER_CALL_EXCEEDED` | `n` > `image_grant.maxPerCallGenerate` / `maxPerCallEdit` (`data.allowed.maxN`) — sync and async |
| `-32110` | `IMAGE_MODEL_UNAVAILABLE` | unknown / non-image `model` (`data.allowed`) |
| `-32111` | `IMAGE_SIZE_UNSUPPORTED` | `fit: 'strict'` and the size / ratio is outside the model's space (`data.allowed`) |
| `-32112` | `IMAGE_OPTION_INVALID` | a `params` value violates the model's option schema (`data.{key, reason, allowed}`) |
| `-32113` | `IMAGE_JOB_NOT_FOUND` | unknown, foreign or `vjob_…` / `mjob_…` `jobId` |
| `-32114` | `IMAGE_JOB_NOT_CANCELLABLE` | image job already terminal (HTTP 409) |
| `-32115` | `IMAGE_CONTENT_REJECTED` | provider safety / content policy rejected the prompt or image — not billed; **also the sync path since 0.29.0** (was `APP_PROVIDER_ERROR`) |
| `-32116` | `IMAGE_JOB_EXPIRED` | job passed its 15-min deadline without a terminal event — refunded (job `error.code` only) |
| `-32117` | `IMAGE_ASSET_NOT_FOUND` | `image.resign`: a key is not yours or malformed (`data.index`) — nothing is signed |
| `-32312` | `IMAGE_EDIT_MASK_UNSUPPORTED` | `mask_url` on a model without `capabilities.edit.mask` |
| `-32142` | `AUDIO_TEXT_TOO_LONG` | over `maxCharsPerCall` (`data.allowed.maxCharsPerCall`) |
| `-32143` | `AUDIO_TOO_LONG` | recording > 10 min / > 25 MB |
| `-32144` | `AUDIO_PROVIDER_ERROR` | TTS/STT provider failure — retryable |
| `-32145` | `AUDIO_VOICE_INVALID` | unknown voice (`data.allowed` = valid voices) |
| `-32146` | `AUDIO_MODEL_UNAVAILABLE` | no routable TTS/STT model |
| `-32147` | `AUDIO_CONTENT_REJECTED` | moderation rejected the text — not billed |
| `-32149` | `AUDIO_OPTION_INVALID` | a `params` value violates the model's `options` schema (`data.{key, reason, allowed}`) |

Executa plugins get the same capabilities through reverse RPC
(`video/generate`, `video/get_job`, `video/cancel_job`, `music/generate`, `music/get_job`,
`music/cancel_job`, `audio/speak`, `audio/transcribe`) with plugin-side gates (`host_capabilities`, `media_token`, audio per-invoke budgets) —
see [Executa media](/developers/tools/executa-media). The image job surface
(`image/generate_async`, `image/edit_async`, `image/get_job`, `image/cancel_job`,
`image/resign`) rides the existing `image_token` — see [Executa image](/developers/tools/executa-image#async-jobs-re-signing).

## Local development

`anna-app dev` has **no offline implementation** of the media stack; the
harness's LLM bridge decides what a media call does:

| Harness flag | `video.*` / `music.*` / `image.*Async` / `image.resign` / `audio.*` / `llm.catalog` |
|---|---|
| *(none — real bridge, default)* | forwarded to the real nexus `/api/v1/copilot/app/{video,music,image,audio}/…` endpoints under an `app_session_token` minted from your PAT — **real CU is charged** to your developer account, `media_job` events are pumped back into the iframe |
| `--mock-llm <fixture.jsonl>` | answered only from a matching fixture line; without one the call fails with `not_implemented` |
| `--no-llm` | `llm_disabled` |

Minimum CLI versions — the harness rejects the call with `-32601 method not
found` (and the manifest validator rejects the `ui.host_api` key) on older
builds, so check `anna-app --version` before debugging your own code:

| Surface | CLI | Bundled `@anna-ai/app-schema` |
|---|---|---|
| `video.*`, `audio.*`, `llm.catalog` | ≥ 0.1.58 | ≥ 0.26.0 |
| `music.*`, `image.generateAsync` / `editAsync` / `getJob` / `cancelJob` / `listJobs` / `resign` | ≥ **0.1.60** (`anna-app-runtime-local` ≥ 0.2.0a30) | ≥ 0.29.0 |

If your project pins an older `@anna-ai/cli` (per-app lockfile), `anna-app validate --strict`
fails with `must NOT have additional properties {"additionalProperty":"music"}` — upgrade the
CLI rather than overriding the schema range. See [Local Dev with --llm](/developers/apps/local-dev-llm)
for PAT setup and fixture format.

## See also

- [App UI Host API](/developers/apps/app-ui-host-api) — envelope, ACL model, generic error codes
- [App UI Manifest](/developers/apps/app-ui-manifest) — `ui.host_api.video` / `.music` / `.audio` grant table
- [App UI Audio Session](/developers/apps/app-ui-audio-session) — realtime voice: streaming ASR / TTS, barge-in, `setContext`, `say`
- [Executa media](/developers/tools/executa-media) — the plugin-side mirror
- [Model capabilities](/developers/reference/model-capabilities) — every TTS / image / video / music model's options, limits and CU prices (generated from the catalogue)
- [Model options form](/developers/reference/model-options-form) — the shared component that renders `capabilities.options` (try it live)
- Reference: [`video.*`](/developers/reference/host-api-video) · [`music.*`](/developers/reference/host-api-music) · [`audio.*`](/developers/reference/host-api-audio) · [`media_job`](/developers/reference/sse-events)
