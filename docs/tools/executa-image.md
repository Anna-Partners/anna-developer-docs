---
title: "Image Generation — LLM Images Without an API Key"
description: "Ask the host to generate or edit images on the user's behalf, with provider selection, billing, and storage handled by Anna."
section: tools
slug: executa-image
order: 12
updated: 2026-10-23
estimated_minutes: 8
---

Image generation lets your plugin produce — or restyle — images **on the user's behalf** without shipping a provider API key, without holding S3 credentials, and without metering quota. The plugin describes the image in protocol-neutral terms; Anna routes the call through the user's preferred image provider (DALL·E 3, Stable Diffusion XL, FLUX, …), charges the user's plan, uploads the result to host storage, and returns the URL.

Available from Executa protocol **v2** onward; companion to [Sampling](/developers/tools/executa-sampling) and [Storage](/developers/tools/executa-storage).

> [!TIP]
> If your tool only needs to **embed** an existing image (e.g. a brand logo the user uploaded), use [Host Upload](/developers/tools/executa-host-upload) instead — generation is for when the pixels do not exist yet.

## Three pre-conditions

End-to-end image generation requires **all** of:

1. **v2 negotiation.** The host sends `initialize`; the plugin replies with `protocolVersion: "2.0"` and lists `client_capabilities.image` (and `image.edit` if you use `image/edit`).
2. **Manifest declaration.** Your published manifest declares the capabilities it intends to use:
   ```json
   {
     "host_capabilities": ["llm.image", "llm.image.edit"]
   }
   ```
   The publish validator rejects unknown capability strings.
3. **User grant.** The end user enabled `image_grant.generate = true` (and `image_grant.edit = true`) for this Executa in their Anna Admin panel. The grant carries `max_images_per_day` and `max_per_call` caps.

If any pre-condition is missing, the host returns `IMAGE_NOT_NEGOTIATED (-32107)` or `IMAGE_NOT_GRANTED (-32101)` and the reverse-RPC never reaches a provider.

## Wire protocol

While processing an `invoke`, emit a reverse JSON-RPC request on stdout:

### `image/generate`

```json
{
  "jsonrpc": "2.0",
  "id": "img-1",
  "method": "image/generate",
  "params": {
    "prompt": "A bold art-deco poster of the planet Mars.",
    "n": 1,
    "size": "1024x1024",
    "fit": "strict",
    "model": "fal-ai/nano-banana-2",
    "params": { "resolution": "2K", "output_format": "png" },
    "reference_image_urls": [],
    "modelPreferences": { "hints": [{ "name": "dalle-3" }] },
    "metadata": { "executa_invoke_id": "<from-context>" }
  }
}
```

`model` (exact catalogue name; unknown → `IMAGE_MODEL_UNAVAILABLE` with
`data.allowed`), `params` (per-model option schema; unknown keys are dropped and
echoed in `ignoredParams`) and `fit` (`nearest` default — closest size, same
orientation; `strict` → `IMAGE_SIZE_UNSUPPORTED` with `data.allowed`) share the
semantics of the App-side `image.generate`, see
[App UI Host API → image](/developers/apps/app-ui-host-api#image).
`modelPreferences.hints` is legacy and only consulted when `model` is absent.

The host responds with the bare result (no wrapper). Alongside `images[]` and
`model` it echoes `requestedSize`, `size` (what the provider actually produced),
`sizeAdjusted`, `aspectRatio`, `fit`, `params` and `ignoredParams`:

```json
{
  "jsonrpc": "2.0",
  "id": "img-1",
  "result": {
    "images": [
      {
        "url": "https://r2.anna.partners/exec/.../poster.png",
        "mimeType": "image/png",
        "width": 1024,
        "height": 1024
      }
    ],
    "model": "dall-e-3",
    "quota_used": { "images_today": 3, "images_quota": 50 }
  }
}
```

### `image/edit`

```json
{
  "jsonrpc": "2.0",
  "id": "img-2",
  "method": "image/edit",
  "params": {
    "image_url": "https://r2.anna.partners/exec/.../poster.png",
    "prompt": "Restyle in a cyberpunk aesthetic. Preserve composition.",
    "n": 1,
    "mask_url": null
  }
}
```

`mask_url` is optional. Not every provider supports masks — if the user's preferred provider does not, the host returns `MASK_UNSUPPORTED (-32312)`.

## Async jobs & re-signing

> Since nexus dispatcher 0.29.0 / matrix image-jobs release (2026-10-21).
> Design: `platform-media-generation-image-jobs.md` §11.

`image/generate` and `image/edit` block the invoke for the whole render —
fine for a 0.5K thumbnail (~5 s), hostile to the invoke budget for 2K/4K or
`quality: "high"` output (60–120 s). The same `image_token` now also carries an
async-job family identical in shape to `music/*`:

| Reverse RPC | Body | Returns |
| --- | --- | --- |
| `image/generate_async` | `image/generate` body + `clientTag?`, `idempotencyKey?` | `{jobId: "ijob_…", kind: "image", state: "queued", estimatedCostCU, deadlineAt, idempotentReplay}` |
| `image/edit_async` | `image/edit` body + `clientTag?`, `idempotencyKey?` | same (needs token `allow_edit` + `llm.image.edit`) |
| `image/get_job` | `{jobId}` | `ImageJobView` — `result.images[].{url, r2Key, mimeType, width, height, expiresIn}`; every `url` re-signed per call |
| `image/cancel_job` | `{jobId}` | `{state: "cancelled", refunded: true}` (queued) · `{state: "running", cancelPending: false}` (provider refused) |
| `image/resign` | `{r2Keys: string[]}` (1–20) | `{urls: [{r2Key, url, expiresIn}]}` — re-sign already-paid artifacts for 7 days |

Rules that differ from the sync calls:

- **Billing.** CU is **pre-charged** for `n` at submit and settled on the
  actual image count (shortfall refunded; failed / cancelled / expired /
  provider-rejected → full refund). `request_type` is `EXECUTA_IMAGE_GEN` /
  `EXECUTA_IMAGE_EDIT` as before.
- **Per-invoke `max_images`** is reserved by `n` **at submit time** and is *not*
  released when the job later fails or is cancelled — it is a runaway guard,
  not billing (the CU hold is). A rejected submit or an idempotent replay does
  release it.
- **Idempotency.** Pass `idempotencyKey` (`^[A-Za-z0-9_\-:.]{1,64}$`, suggested
  `f"{tool_invoke_id}:{attempt}"`); the same key within 24 h returns the
  existing job with `idempotentReplay: true` and never charges twice.
- **Ownership.** `get_job` / `cancel_job` only see jobs **this Executa**
  submitted — App-side `ijob_…` (and other Executas') answer
  `IMAGE_JOB_NOT_FOUND`. `resign` accepts any artifact key owned by the
  invoking user (sync `r2_key`, job `r2Key`, even video / music keys); one
  foreign key fails the whole call with `IMAGE_ASSET_NOT_FOUND` (`data.index`).
- **Timeouts.** Job control calls are capped at 60 s on the Agent; the SDK
  `*_await` wrappers poll every 5 s for up to 9 min by default. Keep the wait
  inside `ctx.remaining_s()` — for longer renders return `jobId` from the
  invoke and resume with `get_job` on the next call.

```python
from executa_sdk import ImageClient, ImageError, ImageJobTimeout

image = ImageClient()
try:
    job = await image.generate_await(
        "A bold art-deco poster of the planet Mars.",
        n=2, model="fal-ai/nano-banana-2", params={"resolution": "4K"},
        idempotency_key=f"{ctx.invoke_id}:1",
        await_timeout_s=min(540, ctx.remaining_s() - 10),
        on_progress=lambda p: log(p.get("phase"), p.get("queuePosition")),
    )
    urls = [im["url"] for im in job["result"]["images"]]
except ImageJobTimeout as t:
    return {"pending_job_id": t.job_id}          # resume with image.get_job next invoke
except ImageError as e:
    if e.code == -32115:                          # IMAGE_CONTENT_REJECTED — not billed
        ...

# later / another invoke
fresh = await image.resign([im["r2Key"] for im in job["result"]["images"]])
```

Node: `imageGenerateAsync` / `imageEditAsync` / `imageGetJob` / `imageCancelJob` /
`imageResign` / `imageGenerateAwait` / `imageEditAwait`; Go:
`GenerateAsync` / `EditAsync` / `GetJob` / `CancelJob` / `Resign` /
`GenerateAwait` / `EditAwait` (`*JobTimeoutError` carries `JobID`).

## SDK examples

### Python

```python
from executa_sdk import ImageClient, ImageError

image = ImageClient(write_frame=_write_frame)

try:
    result = await image.generate(
        prompt="A bold art-deco poster of the planet Mars.",
        n=1,
        size="1024x1024",
        metadata={"executa_invoke_id": invoke_id},
        timeout=120.0,
    )
except ImageError as e:
    # e.code in {-32101, -32102, -32107, …}
    return _make_response(req_id, error={"code": e.code, "message": e.message})
```

### Node.js

```js
import { ImageClient } from "executa-sdk";

const image = new ImageClient({ writeFrame });
const result = await image.generate({
  prompt: "A bold art-deco poster of the planet Mars.",
  n: 1,
  size: "1024x1024",
  timeoutMs: 120000,
});
```

### Go

```go
import imageclient "github.com/openclaw/anna-executa-examples/sdk/go/image"

c := imageclient.New(writeFrame)
res, err := c.Generate(imageclient.GenerateRequest{
    Prompt: "A bold art-deco poster of the planet Mars.",
    N:      1,
    Size:   "1024x1024",
}, 120*time.Second)
```

## Error reference

| Code     | Constant                 | Meaning |
| -------- | ------------------------ | ------- |
| `-32101` | `IMAGE_NOT_GRANTED`      | User has not enabled `image_grant.generate` for this Executa. |
| `-32102` | `IMAGE_QUOTA_EXCEEDED`   | User exhausted `max_images_per_day`. |
| `-32103` | `IMAGE_PROVIDER_ERROR`   | Upstream provider 5xx / model error. |
| `-32104` | `IMAGE_INVALID_REQUEST`  | Bad `size`, empty `prompt`, etc. |
| `-32105` | `IMAGE_TIMEOUT`          | Provider exceeded host wall-clock. |
| `-32106` | `IMAGE_MAX_IMAGES_EXCEEDED` | `n` > `image_grant.max_per_call`. |
| `-32107` | `IMAGE_NOT_NEGOTIATED`   | Manifest did not list `llm.image`, or v2 not negotiated. |
| `-32108` | `IMAGE_USER_DENIED`      | User declined an in-the-moment confirm prompt. |
| `-32109` | `IMAGE_NO_MODEL_AVAILABLE` | User has no image provider configured. |
| `-32110` | `IMAGE_MODEL_UNAVAILABLE` | `model` not found / not an image model (`data.allowed` = valid names); or no routable image model. |
| `-32111` | `IMAGE_SIZE_UNSUPPORTED` | `fit: "strict"` and `size` / `aspect_ratio` outside the model's declared space, or `nearest` found no same-orientation candidate (`data.allowed`). |
| `-32112` | `IMAGE_OPTION_INVALID`   | A `params` value violates the model's option schema (`data.{key, reason, allowed}`). |
| `-32113` | `IMAGE_JOB_NOT_FOUND`    | Unknown `jobId`, or a job not submitted by this Executa. |
| `-32114` | `IMAGE_JOB_NOT_CANCELLABLE` | Job already terminal. |
| `-32115` | `IMAGE_CONTENT_REJECTED` | Provider safety / content policy rejection — not billed. Since 0.29.0 the **sync** calls return this instead of `IMAGE_PROVIDER_ERROR` for safety refusals. |
| `-32116` | `IMAGE_JOB_EXPIRED`      | Job passed its 15-min deadline — refunded (job `error.code` only). |
| `-32117` | `IMAGE_ASSET_NOT_FOUND`  | `image/resign`: a key is not owned by the user or malformed (`data.index`); nothing signed. |
| `-32311` | `EDIT_NOT_SUPPORTED`     | Selected provider does not support `image/edit`. |
| `-32312` | `MASK_UNSUPPORTED`       | Provider supports edit but not masks. |
| `-32313` | `N_UNSUPPORTED`          | Provider supports edit but not `n > 1`. |
| `-32314` | `REFERENCE_FETCH_FAILED` | `reference_image_urls[i]` was unreachable. |

## Pitfalls

> [!WARNING]
> **`n` is capped per-call AND per-day.** `image_grant.max_per_call` caps any single call; `max_images_per_day` is a rolling 24-hour counter shared across every Executa+app combo the user has granted image to. Surface the canonical error code and let the user adjust the grant — never silently retry with smaller `n`.

> [!IMPORTANT]
> **Returned URLs expire.** R2 presigned URLs last ~30 min. Keep `images[].r2_key` (sync) / `result.images[].r2Key` (job) instead and call `image/resign` to get a fresh URL for up to 7 days; for durable storage persist via [`host/uploadFile`](/developers/tools/executa-host-upload). Treat the URL as an ephemeral artifact, not durable storage.

> [!TIP]
> **Reference images count against the `reference_image_urls[]` quota.** Each URL the host fetches is one inbound network hop billed against the user's monthly bandwidth. Keep the count small (≤ 3).

## See also

- App-side companion (anna-app bundle, Host API): [`image.*` reference](/developers/reference/host-api-image)
- Plugin sample: [`anna-executa-examples/examples/python/image-poster/`](https://github.com/openclaw/anna-executa-examples/tree/main/examples/python/image-poster)
- Persist generated bytes back to host: [Host Upload](/developers/tools/executa-host-upload)
- Lifecycle & v2 handshake: [Lifecycle](/developers/tools/executa-lifecycle)
