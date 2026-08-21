---
title: "Host Upload — Persist Files Without S3 Credentials"
description: "Hand a file (or its bytes) to Anna; the host stores it in shared R2 and returns a presigned download URL — your plugin never sees an S3 key."
section: tools
slug: executa-host-upload
order: 13
updated: 2026-05-27
estimated_minutes: 7
---

`host/uploadFile` lets your plugin persist a file — text, image bytes, an LLM transcript, anything under the user's MIME allow-list — to Anna's shared R2 bucket **without holding S3 credentials**. The host writes the object under a stable per-user / per-tool / per-invoke key and returns a presigned download URL. The plugin never touches an AWS SDK and the file inherits the user's plan-level retention.

Available from Executa protocol **v2** onward; pairs naturally with [Image Generation](/developers/tools/executa-image) (persist a generated PNG outside its 30-minute window) and [Sampling](/developers/tools/executa-sampling) (persist an LLM summary).

> [!TIP]
> Use Host Upload for **ephemeral / shareable** artefacts (≤ 80 MiB total per invoke, short presigned URLs). For durable per-user data that survives across invokes — caches, notes, files in the user's drive — use [Persistent Storage (APS)](/developers/tools/executa-storage) instead.

## Three pre-conditions

End-to-end `host/uploadFile` access requires **all** of:

1. **v2 negotiation.** Reply to `initialize` with `protocolVersion: "2.0"` and a non-empty `capabilities.upload` claim (an empty object is fine).
2. **Manifest declaration.** Your published manifest declares the host capability:
   ```json
   { "host_capabilities": ["host.upload"] }
   ```
   The publish validator rejects unknown capability strings.
3. **User grant.** The end user enabled `upload_grant` for this Executa in Anna Admin. The grant carries:
   ```json
   {
     "enabled": true,
     "maxFiles": 16,
     "maxFileBytes": 26214400,
     "allowedPurposes": ["image_input", "image_reference", "user_artifact"]
   }
   ```
   `maxFiles` and `maxFileBytes` (single-file cap) feed the per-invoke counters. There is **no MIME allowlist**: any type that is not on the host's hard denylist (executables, `image/svg+xml`) is accepted — Office formats included. Inline-rendering risk is controlled at serve time instead: every `download_url` carries a signed `Content-Disposition` (`inline` only for `image/*` / `audio/*` / `video/*` / `application/pdf`, `attachment` for everything else).

Missing any pre-condition surfaces as `UPLOAD_NOT_GRANTED (-32201)` (capability / manifest / grant) or `UPLOAD_NOT_NEGOTIATED (-32210)` (no `upload_token` in the invoke context — usually means the host did not authorize this Executa at invoke time).

## Wire protocol

`host/uploadFile` is a single reverse-RPC method with three payload modes selected by `params.mode`:

```
inline      → base64 bytes (≤ 8 MiB)   ── 1 hop
negotiate   → presigned PUT URL        ── 2 hops (negotiate + plugin PUT)
confirm     → finalise presigned upload ── 1 hop (HEAD on R2 + GET url)
```

All three return a single envelope (see [Result shape](#result-shape)).

### `mode: "inline"` (recommended for ≤ 8 MiB)

```json
{
  "jsonrpc": "2.0",
  "id": "u-1",
  "method": "host/uploadFile",
  "params": {
    "mode": "inline",
    "filename": "summary.txt",
    "mime_type": "text/plain",
    "purpose": "user_artifact",
    "content_b64": "<base64 of bytes>"
  }
}
```

> [!IMPORTANT]
> **Hard 8 MiB cap on inline (decoded bytes).** This is a server constant (`INLINE_MAX_BYTES`), independent of `maxFileBytes`. Anything larger MUST use negotiate → PUT → confirm. The host returns `UPLOAD_TOO_LARGE (-32204)` after base64 decoding if exceeded.

### `mode: "negotiate"` (any size up to `maxFileBytes`)

```json
{
  "mode": "negotiate",
  "filename": "video.mp4",
  "mime_type": "video/mp4",
  "purpose": "user_artifact",
  "expected_bytes": 52428800
}
```

`expected_bytes` is optional but recommended — it lets the host reject oversized uploads before signing the URL.

The response carries a short-lived (default **5 min**) presigned PUT URL:

```json
{
  "r2_key": "exec-uploads/prod/<uuid>/<tool>/<invoke>/user_artifact/...",
  "put_url": "https://<bucket>.r2.cloudflarestorage.com/...?X-Amz-Signature=...",
  "headers": { "Content-Type": "video/mp4" },
  "expires_in": 300,
  "expires_at": "2026-07-13T12:05:00Z",
  "_meta": { "mode": "presigned-put" }
}
```

The plugin then `PUT`s the bytes directly to `put_url` with `Content-Type: <mime_type>` (no `Authorization` header — the URL is pre-signed) and finally:

### `mode: "confirm"`

```json
{
  "mode": "confirm",
  "r2_key": "<verbatim r2_key from negotiate response>"
}
```

`confirm` HEADs the R2 object, validates the upload landed, settles the byte counter against the per-invoke quota, and returns the canonical envelope (with `download_url`).

## Result shape

All three modes return the same envelope (only `_meta.mode` differs):

```json
{
  "r2_key":       "exec-uploads/<env>/<user>/<tool>/<invoke>/<purpose>/<ts>_<rand>_<name>",
  "download_url": "https://r2.anna.partners/...?X-Amz-Signature=...",
  "url":          "https://r2.anna.partners/...?X-Amz-Signature=...",
  "mime_type":    "image/png",
  "size_bytes":   204800,
  "bytes":        204800,
  "expires_at":   "2026-07-13T12:30:00Z",
  "expires_in":   1800,
  "_meta":        { "mode": "inline" }
}
```

| Field | Type | Notes |
|---|---|---|
| `r2_key` | string | Opaque storage key. Treat as a handle, not a navigable path. |
| `download_url` | string | Presigned **GET** URL, valid until `expires_at`. **Canonical** — matches the SDKs and examples. |
| `url` | string | Legacy alias of `download_url`, kept for Executas published before the field alignment. |
| `mime_type` | string | Echoes the request (lower-cased). |
| `size_bytes` | integer | Decoded / actual size after upload. **Canonical.** |
| `bytes` | integer | Legacy alias of `size_bytes`. |
| `expires_at` | string | Absolute UTC expiry of `download_url` (ISO 8601). **Canonical.** |
| `expires_in` | integer | Legacy alias: seconds until expiry (default 30 min). Re-call `mode: "confirm"` with the same `r2_key` to mint a fresh URL at zero quota cost. |

> [!NOTE]
> Both field sets are always returned. New code should read `download_url` / `size_bytes` / `expires_at`; the `url` / `bytes` / `expires_in` aliases remain for backward compatibility.

> [!IMPORTANT]
> The returned `url` is **transient** — typically 30 minutes. If the artefact needs to survive longer, either persist the `r2_key` and re-sign on demand via `confirm`, or copy the bytes into [APS files](/developers/tools/executa-storage#object-uploads-two-step).

## SDK examples

### Python

```python
from executa_sdk import HostUploadClient

upload = HostUploadClient(write_frame=_write_frame)

result = await upload.upload_inline(
    filename="poster.png",
    mime_type="image/png",
    content=png_bytes,           # raw bytes; SDK base64-encodes
    purpose="user_artifact",
    timeout=60.0,
)
print(result["download_url"], result["size_bytes"], "expires_at", result["expires_at"])
```

### Node.js

```js
import { HostUploadClient } from "executa-sdk";

const upload = new HostUploadClient({ writeFrame });
const out = await upload.uploadInline({
  filename: "poster.png",
  mimeType: "image/png",
  content: pngUint8,          // Uint8Array; SDK base64-encodes
  purpose: "user_artifact",
});
```

### Go

```go
import upload "github.com/openclaw/anna-executa-examples/sdk/go/host_upload"

c := upload.New(writeFrame)
res, err := c.UploadInline(upload.InlineRequest{
    Filename: "poster.png",
    MimeType: "image/png",
    Content:  pngBytes,
    Purpose:  "user_artifact",
}, 60*time.Second)
```

## Error reference

The plugin sees these JSON-RPC errors (wire codes & names are normative in the Anna Agent runtime):

| Code     | Constant                    | Meaning |
| -------- | --------------------------- | ------- |
| `-32201` | `UPLOAD_NOT_GRANTED`        | Capability missing, manifest didn't declare `host.upload`, or `upload_grant.enabled = false`. |
| `-32202` | `QUOTA_EXCEEDED`            | Plan upload quota exhausted. |
| `-32203` | `INVALID_REQUEST`           | Bad `mode`, missing `filename` / `mime_type`, malformed `content_b64`, etc. |
| `-32204` | `TOO_LARGE`                 | Decoded bytes exceed `maxFileBytes` or the 8 MiB inline cap. |
| `-32205` | `MIME_REJECTED`             | `mime_type` malformed or on the host hard denylist (executables, `image/svg+xml`). The per-token MIME allowlist was removed — any other type is accepted. |
| `-32206` | `PURPOSE_REJECTED`          | `purpose` not in the protocol whitelist (`image_input` / `image_reference` / `user_artifact`) or not in `allowedPurposes`. |
| `-32207` | `STORAGE_ERROR`             | R2 5xx / network. Also wraps subcall timeouts (`errorName: "subcall_timeout"`). |
| `-32208` | `TIMEOUT`                   | Provider call exceeded the host wall-clock. |
| `-32209` | `USER_DENIED`               | User declined an in-the-moment confirm prompt. |
| `-32210` | `UPLOAD_NOT_NEGOTIATED`     | v2 not negotiated, or reverse-RPC invoked outside an invoke context. |
| `-32211` | `MAX_FILES_EXCEEDED`        | Per-invoke `maxFiles` hit. |
| `-32212` | `NOT_FOUND`                 | `confirm` on an unknown `r2_key` (object not uploaded yet, or wrong tool / invoke). |
| `-32213` | `PRESIGN_FAILED`            | Host could not sign the PUT URL. |
| `-32602` | `MISSING_INVOKE_CONTEXT` / `UNKNOWN_INVOKE_CONTEXT` | Reverse RPC could not be correlated with a parent invoke — see below. |

### Concurrent invokes: propagate `context.invoke_id`

`negotiate` r2_keys are scoped to the **parent invoke**; `confirm` validates ownership. When your Executa serves multiple `tools.invoke` calls concurrently, each `host/uploadFile` reverse RPC **must** carry `params.context.invoke_id` of its own parent invoke, or the host cannot associate the calls and rejects with `MISSING_INVOKE_CONTEXT` (it never guesses — guessing is how `r2_key does not belong to this invoke` used to happen intermittently). The SDKs stamp the field automatically once you wrap the tool handler:

```python
from executa_sdk import bind_invoke

def handle_invoke(req_id, params):
    with bind_invoke(params):          # binds params.context.invoke_id
        ...                            # negotiate / PUT / confirm here
```

```js
const { bindInvoke } = require("@anna/executa-sdk");
await bindInvoke(params, async () => { /* negotiate / PUT / confirm */ });
```

Single-invoke-at-a-time plugins keep working without the field (the host falls back to the sole active invoke).

## Quota & limits

| Limit | Default | Source |
|---|---|---|
| Inline payload (decoded) | **8 MiB** | `INLINE_MAX_BYTES` |
| Single-file size cap | **20 MiB** (token default); grants typically widen to **25 MiB** | `upload_token.max_file_bytes`, `upload_grant.maxFileBytes` |
| Per-invoke total bytes | **80 MiB** | `upload_token.max_total_bytes` |
| Per-invoke file count | **16** | `upload_token.max_files`, `upload_grant.maxFiles` |
| Presigned PUT URL TTL | **300 s** | `DEFAULT_PRESIGN_PUT_EXPIRY` |
| Returned GET URL TTL | **~30 min** | `R2_TRANSIENT_PRESIGN_EXPIRY` |
| `upload_token` TTL | **600 s** (10 min) | JWT `aud=executa-upload` |
| Default `allowedPurposes` | `image_input`, `image_reference`, `user_artifact` | `DEFAULT_UPLOAD_ALLOWED_PURPOSES` |

Treat `QUOTA_EXCEEDED`, `MAX_FILES_EXCEEDED`, and `TOO_LARGE` as **non-retryable** within the same invocation; treat `STORAGE_ERROR` / `TIMEOUT` as retryable with backoff (≤ 2 attempts).

## Pitfalls

> [!WARNING]
> **Inline payload is base64.** Wire size is ≈ 1.33 × the decoded bytes. A 7 MiB file becomes ~9.3 MiB on the wire — if your stdio frame writer caps at 8 MiB you'll truncate before the host even sees the request. SDKs encode for you, but if you hand-build frames, size-check the **encoded** length.

> [!IMPORTANT]
> **`r2_key` is opaque, not navigable.** Do not parse or construct it. The host owns the layout (`exec-uploads/<env>/<user>/<tool>/<invoke>/<purpose>/<ts>_<rand>_<name>`); future migrations may change it. Use `url` to share, `r2_key` only as an opaque handle for `confirm`.

> [!TIP]
> **`purpose` drives lifecycle policy.** Pick the most accurate value:
> - `image_input` — bytes the user uploaded into the plugin (model input).
> - `image_reference` — reference images passed to `image/generate`.
> - `user_artifact` — anything the plugin produced and wants to hand back to the user (default).
>
> Anything else returns `PURPOSE_REJECTED (-32206)`.

> [!CAUTION]
> **SVG is blocked.** `image/svg+xml` can carry executable JS → XSS risk. Use PNG / JPEG / WebP instead. Other blocked MIME types: `application/x-msdownload`, `application/x-msdos-program`, `application/x-executable`, `application/x-sharedlib`.

## See also

- App-side companion (anna-app bundle, Host API): [`upload.*` reference](/developers/reference/host-api-upload)
- Plugin sample: [`anna-executa-examples/examples/python/image-poster/`](https://github.com/openclaw/anna-executa-examples/tree/main/examples/python/image-poster) — uses `host/uploadFile` to persist a generated poster.
- Image generation: [Image (Tool)](/developers/tools/executa-image)
- Durable per-user storage: [Persistent Storage (APS)](/developers/tools/executa-storage)
- Lifecycle & v2 handshake: [Lifecycle](/developers/tools/executa-lifecycle)
