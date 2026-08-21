---
title: "Credentials"
description: "How plugins declare and consume API keys / tokens injected by the platform."
section: tools
slug: executa-credentials
order: 7
updated: 2026-05-11
estimated_minutes: 6
---

Most useful tools need secrets — an API key, a bearer token. Anna stores those for the user (encrypted at rest), then injects them into every `invoke` call as part of the request payload.

## Declare credentials in the manifest

List every secret your plugin needs in the `credentials` field of `describe`:

```json
{
  "credentials": [
    {
      "name": "WEATHER_API_KEY",
      "display_name": "OpenWeatherMap API Key",
      "description": "Get one at https://openweathermap.org/api",
      "required": true,
      "sensitive": true
    },
    {
      "name": "WEATHER_UNITS",
      "display_name": "Temperature Units",
      "description": "metric / imperial / standard",
      "required": false,
      "sensitive": false,
      "default": "metric"
    }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Identifier the Agent uses as the dict key when injecting (use `UPPER_SNAKE_CASE`) |
| `display_name` | string | no | Shown in the credential settings UI; defaults to `name` |
| `description` | string | no | Help text shown to users |
| `required` | boolean | no | Defaults to `true`; the plugin won't be enabled until required keys are set |
| `sensitive` | boolean | no | Defaults to `true`; sensitive values are encrypted at rest and rendered as password fields |
| `default` | string | no | Pre-filled value (only useful for non-sensitive options) |

> [!NOTE]
> The protocol does **not** model OAuth providers/scopes. If you need OAuth (Google, GitHub, Notion…), perform the flow inside your plugin's setup helper or via the platform's centralized authorization (see [Platform authorization](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/docs/authorization.md)) and surface the resulting access token as a single sensitive credential.

## How credentials reach the plugin

When the user has configured the credentials, the Agent passes them inside every `invoke` request:

```json
{
  "jsonrpc": "2.0",
  "method": "invoke",
  "id": 7,
  "params": {
    "tool": "get_weather",
    "arguments": { "city": "Tokyo" },
    "context": {
      "credentials": {
        "WEATHER_API_KEY": "sk_live_…",
        "WEATHER_UNITS": "metric"
      }
    }
  }
}
```

`params.context.credentials` is **never** visible to the LLM. Read it inside your `invoke` handler.

### Python pattern

```python
def tool_get_weather(city: str, *, credentials: dict | None = None) -> dict:
    creds = credentials or {}
    # 1) Prefer Agent-injected credentials
    api_key = creds.get("WEATHER_API_KEY") or os.environ.get("WEATHER_API_KEY")
    units   = creds.get("WEATHER_UNITS")   or os.environ.get("WEATHER_UNITS", "metric")

    if not api_key:
        return {"success": False, "error": "WEATHER_API_KEY not configured"}

    # ... call the upstream API ...
    return {"success": True, "data": {"city": city, "units": units, "…": "…"}}


def handle_invoke(req_id, params):
    tool = params.get("tool")
    args = params.get("arguments") or {}
    creds = (params.get("context") or {}).get("credentials") or {}
    if tool == "get_weather":
        return {"id": req_id, "result": tool_get_weather(**args, credentials=creds)}
    …
```

### Node.js pattern

```javascript
function invoke(tool, args, context = {}) {
  const creds = context.credentials || {};
  if (tool === "list_messages") {
    const token = creds.GMAIL_ACCESS_TOKEN || process.env.GMAIL_ACCESS_TOKEN;
    if (!token) return { success: false, error: "GMAIL_ACCESS_TOKEN not configured" };
    // … fetch with `Authorization: Bearer ${token}`
    return { success: true, data: { messages: [/* … */] } };
  }
}
```

## Three-tier resolution

The Agent merges credentials from three sources before sending them in `context.credentials`:

1. **Platform authorization** — secrets the user configured once at `/settings/authorizations`.
2. **Plugin-level credentials** — secrets entered specifically for this plugin (REST: `PUT /api/v1/executas/my/{user_executa_id}/credentials`).
3. **Environment variables** — fallback that *your plugin* implements for local development (the Agent does not export envs from credentials).

## Local development

For local iteration there is no Agent running, so use environment variables and your plugin's fallback path:

```bash
WEATHER_API_KEY=your_key python plugin.py
GMAIL_ACCESS_TOKEN=ya29… node plugin.js
```

## Security guidelines

> [!WARNING]
> - **Never log secrets** — stderr is captured into traces.
> - **Never persist credentials to disk** from the plugin. The platform owns persistence.
> - **Treat credentials as request-scoped.** A long-running plugin may serve multiple users; do not cache credentials in module-level globals.
> - **Echo only redacted previews** in responses (e.g. `sk_…last4`) — anything you put in `result.data` is visible to the LLM.

## Reference

- Full sample with multi-credential support: [`docs/authorization.md`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/docs/authorization.md).
- Per-language credential plugins: [`credential_plugin.py`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/python/credential_plugin.py), [`credential_plugin.js`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/nodejs/credential_plugin.js), [`credential_plugin.go`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/go/credential_plugin.go).
- Google OAuth flow: `google_oauth_plugin.*` in each language directory.
