---
title: "Local Dev with --llm (PAT setup)"
description: "Develop apps that call llm.complete or anna.agent.session against a real Nexus from your laptop."
section: apps
slug: local-dev-llm
order: 17
updated: 2026-06-07
estimated_minutes: 6
category: "App UI"
---

> **Goal:** make `anna.llm.complete(...)` and `anna.agent.session(...)`
> work in `anna-app dev` without packaging the desktop app.
>
> **Non-goal:** running the platform host (Nexus) itself locally — this
> doc assumes you connect to a remote Nexus (staging or prod) over HTTPS.

---

## 1. One-time: log in (mints a Developer PAT)

```bash
anna-app login --host https://nexus.example.com
```

What this does:

1. Starts a **device-flow login** at
   `POST /api/v1/anna-apps/dev/login/start`.
2. Opens your browser to the verification URL; you approve while
   signed in to Nexus normally.
3. Polls `/dev/login/poll` until approval; receives a long-lived JWT
   PAT (audience `aps-dev-pat`, type `anna_app_dev_pat`, default
   90-day TTL, `aps:dev` scope).
4. Atomically writes it to
   `~/.local/share/anna-app/credentials.json` (mode 600) keyed by host.

The PAT does **not** grant LLM access by itself — it only lets the CLI
mint short-lived `app_session_token`s for any app you own.

### List / revoke PATs

Web dashboard → **Developer Tokens** (`/dashboard/dev/tokens`):

- `GET /api/v1/anna-apps/dev/tokens?include_revoked=false` → list
- `POST /api/v1/anna-apps/dev/tokens/{token_id}/revoke` → 204

Revoked PATs are rejected on next mint with `401 token_revoked`. The
CLI surfaces this and asks you to re-login.

---

## 2. Run your app with `--llm real`

```bash
cd my-app
anna-app dev --llm real
```

The harness:

1. Loads the PAT for the matching host.
2. On every `anna.llm.complete` / `anna.agent.session.*` call inside
   the iframe, calls `POST /api/v1/anna-apps/dev/session/mint` with
   `{pat, kind, submode, fixed_client_id, app_id}`.
3. Caches the resulting `app_session_token` per `(window_uuid, kind)` and
   keeps it live: when a cached token is near expiry it transparently calls
   `POST /api/v1/anna-apps/dev/session/refresh` (which also slides the
   session's idle window) instead of minting a brand-new session.
4. Forwards the iframe RPC to the production endpoint
   (`/api/v1/copilot/app/...`) with the `Authorization: Bearer <token>`
   header.

Counts against your real quota and shows up in your usage dashboard.

### 2.1 Session lifecycle in dev

The harness mirrors the production session lifecycle (see
[llm-and-agent.md §3.0–§5](llm-and-agent.md)) using PAT-authed dev
endpoints, so an expired or restart-orphaned session never wedges your
loop:

| App call | Dev endpoint | Notes |
|---|---|---|
| `session.run` / `session.cancel` | (mint/refresh) → `/copilot/app/agent` | Token is auto-refreshed first; if the *session* is expired you get `APP_SESSION_EXPIRED`. |
| `session.refresh` | `POST /dev/session/refresh` | Re-mints + slides idle window. |
| `session.delete` | `POST /dev/session/revoke` | **Token-free** — releases by `app_session_uuid` even when the token is gone, so a dead session stops occupying quota. (When a live token exists the harness uses the token `DELETE` instead.) |
| `session.list` | `GET /dev/sessions?pat=…&app_slug=…` | Lists this app's sessions from the DB — lets your UI recover handles after a CLI restart. |

Because the harness re-derives tokens from the PAT + uuid, **restarting
`anna-app dev` does not strand existing sessions**: hand the saved
`app_session_uuid` back (resume/refresh) and the harness mints a fresh
token from the live row.

#### Dev session admin endpoints

All are PAT-authed (`{pat: ...}` in the body, or `?pat=` for the GET) and
scoped to apps you own:

| Endpoint | Body / query | Returns |
|---|---|---|
| `POST /api/v1/anna-apps/dev/session/refresh` | `{pat, app_session_uuid, ttl_seconds?}` | `{app_session_uuid, token, expires_in, expires_at, max_lifetime_at, …}` |
| `POST /api/v1/anna-apps/dev/session/revoke` | `{pat, app_session_uuid}` | `{revoked: true}` |
| `POST /api/v1/anna-apps/dev/session/revoke-all` | `{pat, app_slug?\|app_id?\|executa_id?, only_expired?}` | `{revoked: <count>}` |
| `GET /api/v1/anna-apps/dev/sessions` | `?pat=&app_slug=&include_expired=&limit=` | `{sessions: [{app_session_uuid, kind, submode, expires_at, max_lifetime_at, …}]}` |

`revoke-all` with `only_expired: true` is a handy "garbage-collect my dead
sessions" call during heavy local iteration.


---

## 3. `--llm mock` (deterministic, free, offline)

```bash
anna-app dev --llm mock --mock-llm fixtures/replies.jsonl
```

Each line of the JSONL fixture is a `MockEntry`:

```jsonl
{"ns":"llm","method":"complete","match":{"contentIncludes":"weather"},"result":{"role":"assistant","content":{"type":"text","text":"sunny"},"model":"mock","stopReason":"endTurn"}}
{"ns":"agent","method":"session.run","events":[{"payload":{"event":"token","text":"hello"}},{"payload":{"event":"token","text":" world"}}]}
```

- `match.contentIncludes` is a substring filter against the call
  payload (case-sensitive).
- For agent runs, `events: [...]` are emitted as `rpc.stream` frames
  in order; the harness adds a final `done: true` terminator.
- If no entry matches, the harness returns a generic echo so your app
  never crashes mid-demo.

This mode is what CI uses — see
[tests/llm-bridge.test.ts](https://github.com/talentai/anna-app-cli/blob/main/tests/llm-bridge.test.ts).

---

## 4. `--llm off` (or `--no-llm`)

Use this when you're iterating on UI that doesn't need LLM and want
zero network calls:

```bash
anna-app dev --no-llm
```

Every handled call returns:

```json
{ "ok": false, "error": { "code": "llm_disabled", "message": "harness started with --no-llm" } }
```

Your app code should handle this gracefully (e.g. show a "LLM disabled
in dev" placeholder).

---

## 5. Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `no PAT on disk` | Never logged in for this host | `anna-app login --host …` |
| `PAT expired` | Default 90-day TTL elapsed | Re-login |
| `session.mint failed: HTTP 403` | Manifest doesn't grant the requested kind/submode | Check `host_api.llm` / `host_api.agent.session` |
| `APP_SESSION_EXPIRED` on run/refresh | Session crossed its idle (30 min agent) or hard (24 h) deadline | Create a fresh session; expired ones auto-release quota |
| `APP_SESSION_TOKEN_EXPIRED` | Capability token lapsed but session is alive | Retry — the harness self-heals the token; or call `session.refresh` |
| Session can't be deleted after restart | Lost the in-memory token handle | Use token-free `session.delete` (PAT) or `POST /dev/session/revoke` with the uuid |
| `permission_denied` from the iframe | Manifest grant missing | Same as above |
| Tokens you didn't expect | Apps you forgot leaving sessions open | `revoke-all` (`only_expired:true`) or revoke the PAT |


---

## 6. Security notes

- The PAT is a bearer credential. Never commit `credentials.json` or
  paste its contents in screenshots.
- Mint calls hit a **dev-only** endpoint (`/api/v1/anna-apps/dev/...`).
  Production never accepts a PAT directly — only short-lived
  `app_session_token`s.
- Revoking a PAT in the dashboard is immediate; subsequent mint calls
  fail with `401 token_revoked`. Existing minted tokens still work
  until they naturally expire (~10 min).
- Quotas, rate limits, and per-app billing apply identically to
  `--llm real` and a packaged production app.

---

## 7. Related

- App-side API reference: [llm-and-agent.md](llm-and-agent.md).
- Design spec (host internals): `docs/design/app-llm-and-agent-access.md`.
