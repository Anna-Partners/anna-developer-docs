---
title: "Image Generation — LLM Images Without an API Key"
description: "Ask the host to generate or edit images on the user's behalf, with provider selection, billing, and storage handled by Anna."
section: tools
slug: executa-image
order: 12
updated: 2026-05-26
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
    "reference_image_urls": [],
    "modelPreferences": { "hints": [{ "name": "dalle-3" }] },
    "metadata": { "executa_invoke_id": "<from-context>" }
  }
}
```

The host responds with the bare result (no wrapper):

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
| `-32110` | `IMAGE_STORAGE_ERROR`    | Host failed to persist generated image to R2. |
| `-32311` | `EDIT_NOT_SUPPORTED`     | Selected provider does not support `image/edit`. |
| `-32312` | `MASK_UNSUPPORTED`       | Provider supports edit but not masks. |
| `-32313` | `N_UNSUPPORTED`          | Provider supports edit but not `n > 1`. |
| `-32314` | `REFERENCE_FETCH_FAILED` | `reference_image_urls[i]` was unreachable. |

## Pitfalls

> [!WARNING]
> **`n` is capped per-call AND per-day.** `image_grant.max_per_call` caps any single call; `max_images_per_day` is a rolling 24-hour counter shared across every Executa+app combo the user has granted image to. Surface the canonical error code and let the user adjust the grant — never silently retry with smaller `n`.

> [!IMPORTANT]
> **Returned URLs expire.** R2 presigned URLs default to 1 hour. If you store the URL in APS / app state, plan to refresh via `image/generate` regen, or persist via [`host/uploadFile`](/developers/tools/executa-host-upload) into a longer-lived key. Treat the URL as ephemeral artifact, not durable storage.

> [!TIP]
> **Reference images count against the `reference_image_urls[]` quota.** Each URL the host fetches is one inbound network hop billed against the user's monthly bandwidth. Keep the count small (≤ 3).

## See also

- App-side companion (anna-app bundle, Host API): [`image.*` reference](/developers/reference/host-api-image)
- Plugin sample: [`anna-executa-examples/examples/python/image-poster/`](https://github.com/openclaw/anna-executa-examples/tree/main/examples/python/image-poster)
- Persist generated bytes back to host: [Host Upload](/developers/tools/executa-host-upload)
- Lifecycle & v2 handshake: [Lifecycle](/developers/tools/executa-lifecycle)
