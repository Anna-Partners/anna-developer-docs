---
title: "Media Generation — Video Jobs & TTS Without an API Key"
description: "Ask the host to generate short videos (async jobs) and synthesize speech on the user's behalf, with provider selection, CU billing, and storage handled by Anna."
section: tools
slug: executa-media
order: 13
updated: 2026-10-08
estimated_minutes: 10
---

Media generation lets your plugin produce **short videos** and **speech audio** on the user's behalf without shipping a provider API key, without holding S3 credentials, and without metering quota. The plugin describes the clip or narration in protocol-neutral terms; Anna routes the call through the platform's video/TTS providers, pre-charges the user's CU pool, uploads the result to host storage, and returns a presigned URL.

Available from Executa protocol **v2** onward; companion to [Image Generation](/developers/tools/executa-image) and [Sampling](/developers/tools/executa-sampling).

> [!NOTE]
> **Video is asynchronous.** Unlike `image/generate` (seconds), video renders for minutes. `video/generate` returns a **job** immediately; you then poll `video/get_job` until a terminal state (or let the SDK's `generate_await` helper do it). `audio/speak` stays synchronous.

## Three pre-conditions

End-to-end media generation requires **all** of:

1. **v2 negotiation.** The host sends `initialize`; the plugin replies with `protocolVersion: "2.0"` and lists `client_capabilities.video` (and `audio.speak` if you use `audio/speak`).
2. **Manifest declaration.** Your published manifest declares the capabilities it intends to use:
   ```json
   {
     "host_capabilities": ["llm.video", "llm.audio.speak"]
   }
   ```
   The publish validator rejects unknown capability strings.
3. **User grant.** The end user enabled the **media grant** (`media_grant.enabled = true`, with `video` / `audio_speak` toggles) for this Executa in their Anna Admin panel.

If any pre-condition is missing, the host returns `VIDEO_NOT_GRANTED (-32120)` / `AUDIO_NOT_GRANTED (-32140)` and the reverse-RPC never reaches a provider. There are **no per-feature rate caps** beyond that — the user's CU quota pool is the only gate.

## Billing: pre-charge + refund

`video/generate` responds with `estimatedCostCU`, which is **charged immediately** from the user's CU pool. If the job later fails, expires, or is cancelled while queued, the hold is **fully refunded**. `audio/speak` bills synchronously by character count (`billedCostCU` in the response).

## Wire protocol

While processing an `invoke`, emit a reverse JSON-RPC request on stdout:

### `video/generate`

```json
{
  "jsonrpc": "2.0",
  "id": "vid-1",
  "method": "video/generate",
  "params": {
    "prompt": "Aerial drone shot over a misty pine forest at sunrise.",
    "durationSec": 5,
    "resolution": "720p",
    "aspectRatio": "16:9",
    "generateAudio": false,
    "imageUrl": null,
    "model": null,
    "clientTag": "my-tool-123"
  }
}
```

With `imageUrl` the clip is driven by that image (image-to-video; `aspectRatio` then follows the image). `model` is an optional catalog hint — a miss falls back to the user's preferred / admin-default video model. Allowed `durationSec` / `resolution` / `aspectRatio` values are **model-dependent**; out-of-range values are rejected with `VIDEO_INVALID_REQUEST (-32122)` carrying the allowed range in `error.data`.

The host responds immediately with the queued job:

```json
{
  "jsonrpc": "2.0",
  "id": "vid-1",
  "result": {
    "jobId": "vjob_7f3a…",
    "state": "queued",
    "estimatedCostCU": 40,
    "deadlineAt": "2026-10-08T12:30:00Z"
  }
}
```

### `video/get_job`

```json
{ "jsonrpc": "2.0", "id": "vid-2", "method": "video/get_job", "params": { "jobId": "vjob_7f3a…" } }
```

Returns the authoritative snapshot — `state` is one of `queued | running | succeeded | failed | cancelled | expired`, with an optional `progress` object while running. On `succeeded`:

```json
{
  "jsonrpc": "2.0",
  "id": "vid-2",
  "result": {
    "jobId": "vjob_7f3a…",
    "state": "succeeded",
    "model": "fal-ai/bytedance/seedance/v1/lite/text-to-video",
    "billedCostCU": 40,
    "result": {
      "url": "https://r2.anna.partners/media/.../vjob_7f3a….mp4",
      "mimeType": "video/mp4",
      "durationSec": 5,
      "width": 1280,
      "height": 720,
      "expiresIn": 1800
    }
  }
}
```

`result.url` is a presigned GET (~30 min TTL) that is **freshly re-signed on every `video/get_job` call** — that is also the recovery path after URL expiry (no regeneration, no extra billing).

### `video/cancel_job`

```json
{ "jsonrpc": "2.0", "id": "vid-3", "method": "video/cancel_job", "params": { "jobId": "vjob_7f3a…" } }
```

Cancelling a **queued** job is guaranteed and fully refunds the CU hold. Cancelling a **running** job is best-effort — the provider may refuse, in which case the job runs to terminal and is billed normally.

### `audio/speak`

```json
{
  "jsonrpc": "2.0",
  "id": "aud-1",
  "method": "audio/speak",
  "params": {
    "text": "Welcome to the generated clip.",
    "voice": null,
    "language": null,
    "speed": 1.0,
    "format": "mp3",
    "delivery": "url"
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": "aud-1",
  "result": {
    "url": "https://r2.anna.partners/media/.../narration.mp3",
    "mimeType": "audio/mpeg",
    "charCount": 30,
    "billedCostCU": 1,
    "model": "qwen-audio-3.0-tts-plus",
    "voice": "Cherry",
    "expiresIn": 1800
  }
}
```

`model` / `voice` echo what the host actually resolved (useful when you left them unset). With `delivery: "inline"` small artifacts come back as `audioBase64` instead of `url`. An invalid `voice` fails with `AUDIO_VOICE_INVALID (-32145)` whose `error.data.allowed` lists the model's valid voices.

## SDK examples

### Python

```python
from executa_sdk import MediaClient, MediaError, VideoJobTimeout

media = MediaClient(write_frame=_write_frame)

try:
    view = await media.generate_await(
        prompt="Aerial drone shot over a misty pine forest at sunrise.",
        duration_sec=5,
        resolution="720p",
        client_tag=f"my-tool-{invoke_id}",
        on_progress=lambda p: print(f"progress: {p}", file=sys.stderr),
    )
    video_url = view["result"]["url"]

    narration = await media.speak(text="Welcome to the clip.", delivery="url")
except VideoJobTimeout as e:
    # Job still rendering server-side — recover later via video/get_job
    return _make_response(req_id, error={"code": e.code, "message": e.message, "data": e.data})
except MediaError as e:
    # e.code in {-32120…-32128, -32140…-32147}
    return _make_response(req_id, error={"code": e.code, "message": e.message})
```

### Node.js

```js
import { MediaClient } from "executa-sdk";

const media = new MediaClient({ writeFrame });

const view = await media.generateAwait({
  prompt: "Aerial drone shot over a misty pine forest at sunrise.",
  durationSec: 5,
  resolution: "720p",
  pollIntervalMs: 5000,
  awaitTimeoutMs: 540000,
  onProgress: (p) => console.error("progress:", p),
});

const narration = await media.speak({ text: "Welcome to the clip.", delivery: "url" });
```

### Go

```go
import mediaclient "github.com/anna-executa/sdk/go/media"

c := mediaclient.New(mediaclient.DefaultFrameWriter())
view, err := c.GenerateAwait(mediaclient.GenerateRequest{
    Prompt:      "Aerial drone shot over a misty pine forest at sunrise.",
    DurationSec: 5,
    Resolution:  "720p",
}, 5*time.Second, 9*time.Minute)

out, err := c.Speak(mediaclient.SpeakRequest{
    Text:     "Welcome to the clip.",
    Delivery: "url",
}, 120*time.Second)
```

## Error reference

| Code     | Constant                     | Meaning |
| -------- | ---------------------------- | ------- |
| `-32120` | `VIDEO_NOT_GRANTED`          | User has not enabled the media grant's video toggle for this Executa. |
| `-32121` | `VIDEO_QUOTA_EXCEEDED`       | User's CU pool cannot cover `estimatedCostCU`. |
| `-32122` | `VIDEO_INVALID_REQUEST`      | Bad `durationSec` / `resolution` / `aspectRatio`, empty prompt, etc. `error.data` carries the allowed range. |
| `-32123` | `VIDEO_PROVIDER_ERROR`       | Upstream provider 5xx / render failure (CU hold refunded). |
| `-32124` | `VIDEO_MODEL_UNAVAILABLE`    | Hinted model is not active, or no video model is configured. |
| `-32125` | `VIDEO_JOB_NOT_FOUND`        | Unknown `jobId` (or not owned by this user). |
| `-32126` | `VIDEO_JOB_NOT_CANCELLABLE`  | Job already terminal. |
| `-32127` | `VIDEO_CONCURRENCY_EXCEEDED` | Reserved — not currently enforced (CU pool is the only gate). |
| `-32128` | `VIDEO_CONTENT_REJECTED`     | Provider safety system rejected the prompt/image. |
| `-32140` | `AUDIO_NOT_GRANTED`          | User has not enabled the media grant's audio toggle for this Executa. |
| `-32141` | `AUDIO_QUOTA_EXCEEDED`       | CU pool cannot cover the character-count price. |
| `-32142` | `AUDIO_TEXT_TOO_LONG`        | `text` exceeds the model's per-call character cap. |
| `-32143` | `AUDIO_TOO_LONG`             | Input audio exceeds the transcription length cap. |
| `-32144` | `AUDIO_PROVIDER_ERROR`       | Upstream TTS provider error. |
| `-32145` | `AUDIO_VOICE_INVALID`        | Unknown `voice` — `error.data.allowed` lists valid voices. |
| `-32146` | `AUDIO_MODEL_UNAVAILABLE`    | No active TTS model matches the request. |
| `-32147` | `AUDIO_CONTENT_REJECTED`     | Provider safety system rejected the text. |

## Pitfalls

> [!IMPORTANT]
> **Returned URLs expire (~30 min).** Never store `result.url` in durable state. Store `jobId` instead and call `video/get_job` again — every call re-signs a fresh URL for free. To keep the bytes forever, persist via [`host/uploadFile`](/developers/tools/executa-host-upload).

> [!WARNING]
> **Respect the invoke timeout.** A video job can out-live your tool invoke. If the SDK's await helper times out (`VideoJobTimeout`), the job **keeps rendering server-side** — return the `jobId` to the caller so a later invoke can recover the result via `video/get_job`, instead of resubmitting (and re-billing) the prompt.

> [!TIP]
> **Model-dependent parameter spaces.** Don't hardcode durations or resolutions. A `VIDEO_INVALID_REQUEST (-32122)` response carries the allowed values in `error.data`; omit optional params to let the model's defaults apply.

## See also

- App-side companion (anna-app bundle, Host API): `anna.video.*` / `anna.audio.*` in the app runtime SDK
- App + plugin sample: [`anna-executa-examples/examples/anna-app-media-studio/`](https://github.com/openclaw/anna-executa-examples/tree/main/examples/anna-app-media-studio) (bundles the `clip-narrator` media executa)
- Persist generated bytes back to host: [Host Upload](/developers/tools/executa-host-upload)
- Image generation (synchronous sibling): [Image Generation](/developers/tools/executa-image)
- Lifecycle & v2 handshake: [Lifecycle](/developers/tools/executa-lifecycle)
