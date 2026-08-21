---
title: "Platform Authorization"
description: "Connect Google / X / GitHub / Notion / Slack once in Anna — every plugin that asks for the credential name receives it automatically."
section: tools
slug: executa-authorization
order: 8
updated: 2026-05-11
estimated_minutes: 7
---

**Platform Authorization** is Anna's central credential broker. Users connect a third-party service **once** in `/settings/authorizations`; every Executa plugin that declares the same credential name is automatically wired up at invoke time — no per-plugin OAuth flow, no API key juggling.

This page explains how the broker works, which providers are first-class, and the conventions a plugin should follow to plug in for free.

![Platform Authorization: providers, resolution priority, plugin invoke](/static/images/developers/executa-authorization.svg)

## How a plugin gets credentials

Every plugin lists the secrets it needs in its `describe` manifest:

```json
{
  "credentials": [
    {
      "name": "GMAIL_ACCESS_TOKEN",
      "display_name": "Gmail Access Token",
      "description": "Auto-injected when the user has connected Google in /settings/authorizations.",
      "required": true,
      "sensitive": true
    }
  ]
}
```

When the Agent invokes a tool, it injects resolved values into `params.context.credentials` — the LLM never sees them:

```json
{
  "method": "invoke",
  "params": {
    "tool": "send_mail",
    "arguments": { "to": "…", "body": "…" },
    "context": {
      "credentials": { "GMAIL_ACCESS_TOKEN": "ya29.…" }
    }
  }
}
```

See the [Credentials](/developers/tools/executa-credentials) page for the full manifest schema.

## Resolution priority

For each name in `credentials[].name`, the resolver searches in this order:

| # | Source | When to use |
|---|---|---|
| 1 | **Platform credentials** | The user has connected this provider in `/settings/authorizations`. Highest priority. |
| 2 | **Plugin-level credentials** | The user pasted a value into the per-plugin settings dialog. |
| 3 | **Process environment** | Local-development fallback only — present when running the binary directly outside the Agent. |

The first hit wins. There is **no** tool-id allowlist: any plugin asking for `GMAIL_ACCESS_TOKEN` receives it, as long as the user has granted Google access.

## How a credential name maps to a provider

Each provider in the registry declares a `credential_mapping` from **plugin-facing names** to either a placeholder (`$access_token`) or a literal field key. Examples below are taken verbatim from the platform's provider registry.

### Google (OAuth2)

```python
credential_mapping = {
    "GOOGLE_ACCESS_TOKEN":        "$access_token",
    "GMAIL_ACCESS_TOKEN":         "$access_token",
    "GOOGLE_WORKSPACE_CLI_TOKEN": "$access_token",
    "GOOGLE_DOCS_ACCESS_TOKEN":   "$access_token",
    "GOOGLE_SHEETS_ACCESS_TOKEN": "$access_token",
}
```

`$access_token` resolves to the live OAuth access_token, refreshed transparently if expired.

> [!NOTE]
> YouTube scopes are **not available**: Google's authorization server rejects requests that combine YouTube scopes with other API scopes such as `drive.file` (`Error 400: invalid_request — scopes cannot be requested together`), so they were removed from the Google provider.

### X / Twitter (OAuth2 + PKCE)

```python
credential_mapping = {
    "TWITTER_ACCESS_TOKEN": "$access_token",
    "X_ACCESS_TOKEN":       "$access_token",
}
```

### GitHub / Notion / Slack (API key)

```python
# GitHub
{ "GITHUB_TOKEN": "GITHUB_TOKEN", "GITHUB_ACCESS_TOKEN": "GITHUB_TOKEN" }

# Notion
{ "NOTION_TOKEN": "NOTION_TOKEN", "NOTION_API_KEY": "NOTION_TOKEN" }

# Slack
{ "SLACK_BOT_TOKEN": "SLACK_BOT_TOKEN", "SLACK_TOKEN": "SLACK_BOT_TOKEN" }
```

The literal-key form maps the plugin's requested name to the underlying field stored in `user_platform_credentials.credentials_encrypted`.

## Supported providers (current registry)

| Provider | Auth | Recommended credential names |
|---|---|---|
| **Google** | OAuth2 (Gmail / Calendar / Drive / Docs scopes) | `GOOGLE_ACCESS_TOKEN`, `GMAIL_ACCESS_TOKEN`, `GOOGLE_DOCS_ACCESS_TOKEN`, `GOOGLE_SHEETS_ACCESS_TOKEN`, `GOOGLE_WORKSPACE_CLI_TOKEN` |
| **X (Twitter)** | OAuth2 + PKCE (20 scopes) | `TWITTER_ACCESS_TOKEN`, `X_ACCESS_TOKEN` |
| **GitHub** | API key (Personal Access Token) | `GITHUB_TOKEN`, `GITHUB_ACCESS_TOKEN` |
| **Notion** | API key (Integration Token) | `NOTION_TOKEN`, `NOTION_API_KEY` |
| **Slack** | API key (Bot User OAuth Token) | `SLACK_BOT_TOKEN`, `SLACK_TOKEN` |
| **OpenAI** | API key (BYO) | `OPENAI_API_KEY` |
| **Anthropic** | API key (BYO) | `ANTHROPIC_API_KEY` |

> [!TIP]
> Need to call an LLM as part of your tool? Don't ask for `OPENAI_API_KEY` — use [Sampling](/developers/tools/executa-sampling) instead. Sampling lets you call the user's preferred provider on their quota, with no API key shipped at all.

## API surface

Standard endpoints under `/api/v1/platform-credentials`:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/providers` | List all supported providers |
| `GET` | `/my` | Current user's authorization status across all providers |
| `GET` | `/my/{provider_id}` | Detail for one provider (scopes, email, last refresh) |
| `GET` | `/oauth/{provider_id}/authorize` | Begin OAuth flow (redirect) |
| `GET` | `/oauth/{provider_id}/callback` | OAuth callback handler |
| `PUT` | `/api-key/{provider_id}` | Set / update an API key |
| `GET` | `/api-key/{provider_id}/status` | Whether an API key is configured |
| `DELETE` | `/my/{provider_id}` | Disconnect (revokes upstream where supported) |
| `POST` | `/my/{provider_id}/refresh` | Force-refresh an OAuth token |

Plugins should not call these directly — they are for the Anna UI. Plugins receive the resolved value via `context.credentials` as shown above.

## Security model

- **Encrypted at rest.** All stored credentials are encrypted with **AES-256-GCM** using a server-side key; plaintext never reaches the database.
- **LLM-isolated.** Credentials live in `params.context.credentials`, **never** in tool parameters. The LLM cannot see them and cannot leak them in conversation.
- **Least privilege.** OAuth flows ask only for scopes the user explicitly approves — e.g. Gmail read-only without send.
- **Auto-refresh.** OAuth `access_token`s are refreshed transparently using the stored `refresh_token` when expired.
- **Revocable.** Disconnecting a provider revokes the token upstream where the provider supports it (Google, Twitter, …).

## Author best practices

### 1 · Align names with `credential_mapping`

```jsonc
// ✅ Matches the registry — auto-injected for any user who has connected Google
{ "name": "GMAIL_ACCESS_TOKEN" }

// ❌ Custom name — the platform cannot map this; user must enter it manually
{ "name": "MY_GMAIL_KEY" }
```

### 2 · Read from `context` first, env as fallback

```python
def send_mail(args, *, credentials: dict | None = None):
    creds = credentials or {}
    token = creds.get("GMAIL_ACCESS_TOKEN") or os.environ.get("GMAIL_ACCESS_TOKEN")
    if not token:
        return {"success": False, "error": "GMAIL_ACCESS_TOKEN not configured"}
    # … use token …
```

### 3 · Never expose credentials as tool parameters

```jsonc
// ✅ Hidden from the LLM
{ "credentials": [{ "name": "GITHUB_TOKEN" }],
  "tools": [{ "name": "create_issue",
              "parameters": [{ "name": "title", "type": "string" }] }] }

// ❌ The LLM sees and can leak this
{ "tools": [{ "name": "create_issue",
              "parameters": [{ "name": "github_token", "type": "string" },
                             { "name": "title",        "type": "string" }] }] }
```

### 4 · Mark sensitive values

```json
{ "name": "API_SECRET", "sensitive": true }
```

`sensitive: true` switches the settings UI to a password input and keeps the value out of UI echoes.

### 5 · Provide clear acquisition instructions

```json
{
  "name": "GITHUB_TOKEN",
  "display_name": "Personal Access Token",
  "description": "GitHub → Settings → Developer settings → Personal access tokens (fine-grained recommended)"
}
```

## Adding a new provider

Adding a provider is a single server-side registration in the platform's provider registry — no DB schema change:

```python
_register(
    CredentialProviderDef(
        provider_id="my-service",
        name="My Service",
        icon="my-service",
        description="My Service API",
        website="https://my-service.com",
        auth_type="api_key",
        api_key_fields=[
            CredentialFieldDef(
                name="MY_SERVICE_TOKEN",
                display_name="API Token",
                description="Get one at https://my-service.com/settings/api",
            ),
        ],
        credential_mapping={ "MY_SERVICE_TOKEN": "MY_SERVICE_TOKEN" },
    )
)
```

Open a PR; the new tile shows up at `/settings/authorizations` automatically.

## See also

- [Credentials](/developers/tools/executa-credentials) — manifest schema for `credentials[]`
- [Sampling](/developers/tools/executa-sampling) — for LLM access without an API key
- [Common Pitfalls](/developers/tools/executa-pitfalls)
