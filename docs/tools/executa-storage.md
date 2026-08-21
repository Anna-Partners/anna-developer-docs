---
title: "Persistent Storage (APS)"
description: "Per-user durable KV + object store hosted by Anna — no cloud account, no DB, quota and access control enforced by the host."
section: tools
slug: executa-storage
order: 11
updated: 2026-05-11
estimated_minutes: 9
---

**Anna Persistent Storage (APS)** gives an Executa plugin a small, durable, per-user **key/value + object** store hosted by Anna. There is no cloud account to provision, no credentials to ship, and no DB to run — quota and access control are enforced by Nexus.

Available from protocol **v2** onward.

![APS architecture: scopes, methods, REST mapping](/static/images/developers/executa-storage.svg)

## When to use APS

| Want to… | Use |
|---|---|
| Remember "where did the last run leave off" between invokes | KV (`storage/*`) |
| Cache an expensive computation (OCR, embeddings, derived JSON) | KV with `ttl_seconds` |
| Save a generated PDF / image / CSV the assistant can hand back to the user | Objects (`files/*`) |
| Drop a file into the **end user's drive** so other plugins can find it | Objects (`files/*` with `scope: "user"`) |

If your data is bigger than a few KB or is binary, prefer object storage — KV values are JSON and capped per-write.

## Three pre-conditions

End-to-end APS access requires **all** of:

1. **v2 negotiation.** Plugin echoes `protocolVersion: "2.0"` and exposes the storage capability in its `initialize` response (`capabilities.storage = {}` is sufficient).
2. **Manifest declaration.** `host_capabilities` lists at least one of `storage.user`, `storage.app`, `storage.tool` — only the declared scopes will be granted.
3. **User grant.** The end user enabled storage for this Executa in their Anna Admin panel. The grant pins `allowed_scopes`, `quotaBytes`, and `objectMaxBytes`.

If anything is missing, Nexus rejects the reverse RPC with `-32021 STORAGE_NOT_GRANTED`.

## Scopes

| Scope | Owner | Visibility |
|---|---|---|
| `user` | The end user | Their own dashboards & every plugin they grant. |
| `app`  | The Anna App bundle | Shared across the same app for one user. |
| `tool` | The Executa plugin | Strictly local to (user × executa). |

Defaults to `app` when `scope` is omitted. To write into the end user's drive, pass `scope: "user"` on the same `files/*` methods — the per-scope grant is enforced by the `storage_token`'s `allowed_scopes` claim, not by the method name.

> [!TIP]
> Prefer `tool` for transient state. Ask for `user` only when the user obviously benefits from cross-tool reuse — e.g. saving a generated PDF into their **My Files**.

## Wire protocol

After v2 is live, every `invoke` request also carries a short-lived `storage_token` inside `params.context` (see [Lifecycle](/developers/tools/executa-lifecycle#per-invoke-context-injection)). Reverse RPCs go out on the same stdin/stdout channel as sampling:

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "method": "storage/set",
  "params": {
    "scope": "tool",
    "key":   "lastRun/cursor",
    "value": { "page": 7, "ts": "2026-05-01T11:22:33Z" },
    "ttl_seconds": 86400
  }
}
```

The Agent forwards every storage RPC over HTTP to Nexus's `/api/v1/storage/*` endpoints, attaching the `storage_token` as `Authorization: Bearer …`.

### Methods

| Method | Purpose | Body / query |
|---|---|---|
| `storage/get` | Read one JSON value by key | `key`, `scope` |
| `storage/set` | Write one JSON value | `key`, `value`, `ttl_seconds?`, `if_match?` |
| `storage/delete` | Soft-delete a key | `key`, `scope` |
| `storage/list` | List keys by prefix (paged) | `prefix`, `cursor?`, `limit?` |
| `files/upload_begin` | Mint a presigned PUT URL | `path`, `content_type`, `size_bytes` |
| `files/upload_complete` | Commit after PUT succeeds | `path`, `etag` |
| `files/download_url` | Mint a time-limited GET URL | `path` |
| `files/list` | List objects by prefix | `prefix`, `cursor?` |
| `files/delete` | Soft-delete an object | `path` |

Pass `scope: "user"` on any `files/*` method to target the user drive; the request is authorised iff the `storage_token`'s `allowed_scopes` claim includes `user`.

### Result shapes

| Method | Success result |
|---|---|
| `storage/get` (hit) | `{"value": …, "exists": true, "etag": "…"}` |
| `storage/get` (miss) | `{"value": null, "exists": false, "etag": null}` |
| `storage/set` | `{"etag": "…", "size_bytes": …}` |
| `storage/delete` | `{"deleted": true}` |
| `storage/list` | `{"items": [...], "next_cursor": …}` |
| `files/upload_begin` | `{"presigned_url": "https://…", "fields": {…}, "expires_at": …}` |
| `files/upload_complete` | `{"path": "…", "etag": "…", "size_bytes": …}` |
| `files/download_url` | `{"url": "https://…", "expires_at": …}` |

> [!IMPORTANT]
> The Agent normalises 404s on `storage/get` into `{"value": null, "exists": false}` so you can use the documented `cur["exists"]` pattern. **Do not** assume the value is missing just because `cur["value"]` is falsy — it may be a legitimate `0`, `""`, `false`, or `[]`.

## Optimistic concurrency

Always pass `if_match` (the previous `etag`) on overwrite to avoid lost updates:

```python
cur = await rpc("storage/get", { "scope": "tool", "key": "notes/123" })
notes = cur["value"] if cur["exists"] else []
notes.append({ "ts": now(), "text": new_text })

await rpc("storage/set", {
    "scope": "tool",
    "key":   "notes/123",
    "value": notes,
    "if_match": cur.get("etag"),     # missing on first write — that's fine
})
```

A failed precondition surfaces as `-32023 PRECONDITION_FAILED`; re-read and retry.

## Worked example — caching an OCR result

```python
import hashlib, json, sys, uuid, queue, threading

# (single-reader / dispatch boilerplate omitted — see Sampling page)

def cache_ocr(invoke_id: str, image_bytes: bytes) -> str:
    sha = hashlib.sha256(image_bytes).hexdigest()
    cur = rpc("storage/get", {"scope": "tool", "key": f"ocr/{sha}"})
    if cur["exists"]:
        return cur["value"]["text"]

    text = run_ocr(image_bytes)                   # expensive
    rpc("storage/set", {
        "scope": "tool",
        "key":   f"ocr/{sha}",
        "value": { "text": text, "ranAt": now_iso() },
        "ttl_seconds": 30 * 24 * 3600,            # 30 days
    })
    return text
```

For a runnable plugin, see the upstream
[`examples/python/storage-notebook/`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/python/storage-notebook).

## Object uploads — two-step

Direct PUT to R2 is the recommended path for any binary or anything bigger than a few KB:

```text
①  files/upload_begin  ──▶  { presigned_url, fields, expires_at }
②  HTTP PUT to presigned_url with the bytes
③  files/upload_complete  ──▶  { path, etag, size_bytes }
```

The two-step shape lets the bytes go directly to R2 without round-tripping through the Agent's stdio. Skip step ③ and the object is silently garbage-collected after a few minutes.

## Quota & limits

| Limit | Default | Where set |
|---|---|---|
| Per-user total bytes | **5 GB** | `PlanMetric.storage_quota_bytes`, plan-overridable |
| Single KV value | **64 KB** (advisory; hard cap configured per env) | `STORAGE_ERR_VALUE_TOO_LARGE` if exceeded |
| Single object | per-grant `objectMaxBytes` | host returns `-32024 QUOTA_EXCEEDED` |
| Per-invoke storage RPCs | **200** (default `max_calls` in `storage_token`) | `STORAGE_ERR_RATE_LIMITED` if exceeded |
| `storage_token` TTL | **600 s** | JWT `aud=aps-storage` |

Treat `RATE_LIMITED` and `QUOTA_EXCEEDED` as **non-retryable** within the same invocation; treat `UPSTREAM_ERROR` as retryable with backoff.

## Error codes

| Code | Name | Meaning |
|---|---|---|
| `-32021` | `STORAGE_NOT_GRANTED` | Missing token, missing capability, or scope not allowed. |
| `-32022` | `NOT_FOUND` | Key / path does not exist (only surfaced where it's not normalised away). |
| `-32023` | `PRECONDITION_FAILED` | `if_match` etag mismatch. |
| `-32024` | `QUOTA_EXCEEDED` | Plan storage quota exhausted. |
| `-32025` | `VALUE_TOO_LARGE` | KV value above per-call ceiling. |
| `-32026` | `RATE_LIMITED` | Per-invoke RPC budget exhausted. |
| `-32027` | `INVALID_PATH` | Reserved / out-of-bucket path. |
| `-32028` | `INVALID_REQUEST` | Missing required field, wrong type. |
| `-32029` | `UPSTREAM_ERROR` | Network / 5xx from Nexus REST. |

## Built-in user-storage tools

For LangChain agents, Nexus auto-registers six high-level wrappers under the `user_storage_*` namespace:

```
user_storage_get / set / delete / list /
user_storage_files_save_text / user_storage_files_get_url
```

The agent never sees the raw RPC; the tool wraps each call in a soft **5-write / 20-read per-invocation** budget and returns the same JSON envelope as above. Users can disable these per-account via `UserSettings.disable_user_storage_tools`.

## Best practices

1. **Default to `tool` scope.** Move to `app` only when several views of the same Anna App share state, and `user` only when the data is genuinely user-owned.
2. **Encode metadata in the key, not the value.** `notes/{noteId}` is searchable via `storage/list`; embedded JSON fields are not.
3. **Keep individual KV values small** — anything bigger than a few KB belongs in objects.
4. **Always pass `if_match` on overwrite.** Lost updates are silent and miserable to debug.
5. **Set TTLs on cache-shaped data.** Quota is a finite resource shared with the user's other plugins.
6. **Treat the response as authoritative.** Always read back the `etag` after a write — never assume your client already knows it.

## See also

- [Lifecycle & Capability Negotiation](/developers/tools/executa-lifecycle)
- [Sampling](/developers/tools/executa-sampling) — sister reverse-RPC capability
- [Protocol Specification](/developers/tools/executa-protocol)
- [Common Pitfalls](/developers/tools/executa-pitfalls)
