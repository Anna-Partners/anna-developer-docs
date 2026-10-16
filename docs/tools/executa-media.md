---
title: "Media — Video Jobs, TTS & STT Without an API Key"
description: "Ask the host to generate short videos (async jobs), synthesize speech and transcribe audio on the user's behalf, with provider selection, CU billing, and storage handled by Anna."
section: tools
slug: executa-media
order: 13
updated: 2026-10-12
estimated_minutes: 10
---

Media lets your plugin produce **short videos** and **speech audio**, and **transcribe recorded audio**, on the user's behalf without shipping a provider API key, without holding S3 credentials, and without metering quota. The plugin describes the clip, narration or recording in protocol-neutral terms; Anna routes the call through the platform's video/TTS/STT providers, charges the user's CU pool, uploads any result bytes to host storage, and returns a presigned URL (or, for transcription, the text).

Available from Executa protocol **v2** onward; companion to [Image Generation](/developers/tools/executa-image) and [Sampling](/developers/tools/executa-sampling).

> [!NOTE]
> **Video is asynchronous.** Unlike `image/generate` (seconds), video renders for minutes. `video/generate` returns a **job** immediately; you then poll `video/get_job` until a terminal state (or let the SDK's `generate_await` helper do it). `audio/speak` and `audio/transcribe` stay synchronous.

## Three pre-conditions

End-to-end media generation requires **all** of:

1. **v2 negotiation.** The host sends `initialize`; the plugin replies with `protocolVersion: "2.0"` and lists `client_capabilities.video` (and `audio.speak` / `audio.transcribe` for the audio methods).
2. **Manifest declaration.** Your published manifest declares the capabilities it intends to use:
   ```json
   {
     "host_capabilities": ["llm.video", "llm.audio.speak", "llm.audio.transcribe"]
   }
   ```
   The publish validator rejects unknown capability strings. Each audio method has its **own** capability — declaring `llm.audio.speak` does not unlock `audio/transcribe`.
3. **User grant.** The end user enabled the **media grant** (`media_grant.audio.enabled = true`, with the `speak` / `transcribe` sub-toggles; `media_grant.video.enabled` for video) for this Executa in their Anna Admin panel.

If any pre-condition is missing, the host returns `VIDEO_NOT_GRANTED (-32120)` / `AUDIO_NOT_GRANTED (-32140)` and the reverse-RPC never reaches a provider. There are **no per-feature rate caps** beyond that — the user's CU quota pool is the only user-level gate; a small **per-invoke budget** (video jobs, TTS characters, STT seconds) protects against a runaway single invoke.

> [!NOTE]
> `audio/transcribe` requires host **matrix ≥ 2026-10-12** (`METHOD_AUDIO_TRANSCRIBE`). On an older host the SDK call fails with `method_not_found`, which the SDKs surface as `AUDIO_NOT_GRANTED` — treat it as "feature unavailable", not as a user-permission problem.

## Billing: pre-charge + refund

`video/generate` responds with `estimatedCostCU`, which is **charged immediately** from the user's CU pool. If the job later fails, expires, or is cancelled while queued, the hold is **fully refunded**. `audio/speak` bills synchronously by character count and `audio/transcribe` by audio duration (`billedCostCU` in the response; ledger request types `EXECUTA_TTS` / `EXECUTA_STT`).

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
    "voice": "longanlingxin",
    "expiresIn": 1800
  }
}
```

`model` / `voice` echo what the host actually resolved (useful when you left them unset). With `delivery: "inline"` small artifacts come back as `audioBase64` instead of `url`. An invalid `voice` fails with `AUDIO_VOICE_INVALID (-32145)` whose `error.data.allowed` lists the model's valid voices — **voice ids are model-specific** (e.g. `qwen-audio-3.0-tts-*` use `longanlingxin` / `longanfengyue` …, the realtime `qwen3-tts-*` family uses `Cherry` / `Serena`), so either omit `voice` to get the model's default or pick one from `anna.llm.catalog({serviceType:"tts"})`.

### `audio/transcribe`

Synchronous speech-to-text for a recording of **≤ 10 minutes**. Send the audio **inline** (`audioBase64`, ≤ 10 MB decoded — the usual case for push-to-talk / local recordings) **or** by public `https` URL (`audioUrl`, ≤ 25 MB, SSRF-guarded); exactly one of the two.

```json
{
  "jsonrpc": "2.0",
  "id": "stt-1",
  "method": "audio/transcribe",
  "params": {
    "audioBase64": "<base64 wav/mp3/webm/ogg/flac/m4a>",
    "format": "wav",
    "language": "zh"
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": "stt-1",
  "result": {
    "text": "我现在该出什么",
    "durationSec": 2.8,
    "durationExact": true,
    "language": "zh",
    "billedCostCU": 1,
    "model": "qwen-audio-3.1-asr-flash"
  }
}
```

| Param | Required | Notes |
| --- | --- | --- |
| `audioBase64` | one of | Inline bytes, base64. ≤ 10 MB decoded. SDKs encode for you. |
| `audioUrl` | one of | Public `https://` URL, ≤ 25 MB. Content-Type decides the format. |
| `format` | with `audioBase64` | `wav` \| `mp3` \| `webm` \| `ogg` \| `flac` \| `m4a`. |
| `language` | no | BCP-47-ish hint (`zh`, `en`); default auto. Echoed back. |
| `model` | no | Catalogue hint; the host resolves an STT model otherwise. |

`durationSec` is **exact** for `wav` (parsed from the header) and a byte-based **estimate** for compressed formats (`durationExact: false`). The 600 s cap is enforced exactly for `wav`; other formats are bounded by the byte caps. Billing is by audio duration (`EXECUTA_STT`).

**Per-invoke seconds budget.** Like `audio/speak`'s character budget, the host reserves the estimated seconds against the `media_token` claim `max_audio_seconds` (default **600**, tracked per `tool_invoke_id` for 30 min) before calling the provider and settles to the real `durationSec` afterwards. Exceeding it fails fast with `AUDIO_INVOKE_BUDGET_EXCEEDED (-32148)` — split long recordings across invokes rather than retrying.

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

    # Push-to-talk: 16 kHz mono PCM16 wav captured locally → text
    stt = await media.transcribe(audio_bytes=wav_bytes, format="wav", language="zh")
    question = stt["text"]
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

const { text } = await media.transcribe({ audioBuffer: wavBuffer, format: "wav", language: "zh" });
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

stt, err := c.TranscribeBytes(wavBytes, "wav", "zh", 90*time.Second)
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
| `-32127` | `VIDEO_CONCURRENCY_EXCEEDED` | Per-invoke video job budget exhausted (`media_token` claim `max_video_jobs`, default **2**, tracked per `tool_invoke_id` for 30 min). There is no platform-wide concurrency cap — the CU pool is the only user-level gate. |
| `-32128` | `VIDEO_CONTENT_REJECTED`     | Provider safety system rejected the prompt/image. |
| `-32140` | `AUDIO_NOT_GRANTED`          | Media token / manifest / user grant does not allow this audio method (`speak` and `transcribe` are gated separately). Also what SDKs report when the host is too old to know `audio/transcribe`. |
| `-32141` | `AUDIO_QUOTA_EXCEEDED`       | CU pool cannot cover the character-count / duration price. |
| `-32142` | `AUDIO_TEXT_TOO_LONG`        | `text` exceeds the model's per-call character cap, **or** the per-invoke character budget (`max_audio_chars`, default 8000) is exhausted — the message says which. |
| `-32143` | `AUDIO_TOO_LONG`             | Input audio exceeds the transcription caps: > 10 MB inline, > 25 MB by URL, or > 600 s (`wav`). `error.data.allowed` carries the cap. |
| `-32144` | `AUDIO_PROVIDER_ERROR`       | Upstream TTS/STT provider error, or the `audioUrl` could not be fetched. |
| `-32145` | `AUDIO_VOICE_INVALID`        | Unknown `voice` — `error.data.allowed` lists valid voices. |
| `-32146` | `AUDIO_MODEL_UNAVAILABLE`    | No active TTS/STT model matches the request. |
| `-32147` | `AUDIO_CONTENT_REJECTED`     | Provider safety system rejected the text. |
| `-32148` | `AUDIO_INVOKE_BUDGET_EXCEEDED` | Per-invoke transcription seconds budget exhausted (`max_audio_seconds`, default 600, per `tool_invoke_id`). |

## Pitfalls

> [!IMPORTANT]
> **Returned URLs expire (~30 min).** Never store `result.url` in durable state. Store `jobId` instead and call `video/get_job` again — every call re-signs a fresh URL for free. To keep the bytes forever, persist via [`host/uploadFile`](/developers/tools/executa-host-upload).

> [!WARNING]
> **Respect the invoke timeout.** A video job can out-live your tool invoke. If the SDK's await helper times out (`VideoJobTimeout`), the job **keeps rendering server-side** — return the `jobId` to the caller so a later invoke can recover the result via `video/get_job`, instead of resubmitting (and re-billing) the prompt.

> [!TIP]
> **Model-dependent parameter spaces.** Don't hardcode durations or resolutions. A `VIDEO_INVALID_REQUEST (-32122)` response carries the allowed values in `error.data`; omit optional params to let the model's defaults apply.

> [!TIP]
> **Recording format for `audio/transcribe`.** Prefer **16 kHz mono PCM16 `wav`** for short push-to-talk clips: the host measures duration exactly (so the 600 s cap and the per-invoke budget are precise) and no decoder is involved. 10 min of 16 kHz mono wav is ≈ 19 MB — above the 10 MB inline cap — so for long recordings either chunk by sentence or upload once and pass `audioUrl`. Always set `format` for inline audio; omitting it is a `VIDEO_INVALID_REQUEST (-32122)`.

## See also

- App-side companion (anna-app bundle, Host API): `anna.video.*` / `anna.audio.*` in the app runtime SDK
- App + plugin sample: [`anna-executa-examples/examples/anna-app-media-studio/`](https://github.com/openclaw/anna-executa-examples/tree/main/examples/anna-app-media-studio) (bundles the `clip-narrator` media executa)
- Persist generated bytes back to host: [Host Upload](/developers/tools/executa-host-upload)
- Image generation (synchronous sibling): [Image Generation](/developers/tools/executa-image)
- Lifecycle & v2 handshake: [Lifecycle](/developers/tools/executa-lifecycle)
