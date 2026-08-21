---
title: "FAQ"
description: "Answers to the questions developers most often ask."
section: reference
slug: faq
order: 4
updated: 2026-04-23
estimated_minutes: 5
---

## Building

### Do I have to use Python / Node / Go for a Tool Executa?

No. The protocol is JSON-RPC over stdio — anything that can read a line and print a line works. Rust, Ruby, C#, Bash, even a compiled C binary. The three languages we document just have ready-made examples in [`anna-executa-examples`](https://github.com/whtcjdtc2007/anna-executa-examples).

### Are Tools and Skills the same thing?

They are the two flavours of one umbrella concept, **Executa** — same database table, same draft → version → visibility lifecycle, same Hub. A *Tool* is the executable flavour (a process speaking JSON-RPC); a *Skill* is the declarative flavour (a `SKILL.md` folder). See [Concepts](/developers/overview/concepts).

### Can my Tool Executa call other Tool Executas?

Not directly. Each Tool runs in its own process and only sees its own stdin/stdout/stderr and the env vars passed at spawn time. If you need composition, either:

- Bundle the Tools into an **Anna App** so the user installs them together; or
- Ship a **Skill** whose body teaches Anna *when* to call each Tool — the LLM does the orchestration.

### Is there an SDK?

No. The protocol is small enough that "the SDK" would be tens of lines. The example repos linked above stand in for thin wrappers.

### Does a Skill execute the bash / python in its body?

No. The skill loader wraps every Skill — regardless of `execution_mode` — as a prompt-mode LangChain tool that returns the skill's markdown body to the LLM, decorated with an execution-mode hint and any declared dependencies. Running anything is the agent's job, via its built-in `exec` / `command` tools. `execution_mode` is purely a hint that helps the LLM pick the right execution path.

## Distribution

### Do I need Verified Developer status to publish?

Only for **Anna Apps**. Tool and Skill Executas can be created and made `public` by any user with a paid subscription (a server-side paid-plan check). Apps require the `is_verified_developer` flag — see [Verified Developer](/developers/reference/verified-developer).

### What is the App review flow?

The app status cycles through:

1. `draft` — created by the developer.
2. `pending_review` — set by `POST /api/v1/developer/apps/{id}/submit-review` (requires at least one version).
3. `approved` or `rejected` — decided by a platform admin via `POST /api/v1/super-admin/apps/{id}/approve` or `.../reject`. An admin can publish in the same call (`publish=true`).
4. `published` — visible in the public catalogue.
5. `archived` — set by the developer (`/archive`) or admin; existing installs keep working but new users can't discover it.

There is no documented review SLA in the codebase.

### Can I delete a published Executa?

`DELETE /api/v1/executas/my/{tools|skills}/{id}` does a **hard delete** when nothing references the Executa, and a **soft archive** (sets `archived=True`) when a published `AnnaAppVersion` snapshot still references it — so other users' installed Apps don't break. Versions snapshotted into a published App are immutable; you can't selectively delete them.

### Can I delete a published Anna App?

There's no hard-delete endpoint for an App once it's published. Use `POST /api/v1/developer/apps/{id}/archive` to set status to `archived`: existing installs keep working, new users can't discover it. If you need a published version pulled for a security issue, contact platform support.

### Can I publish under a company name?

Yes — once an admin grants you Verified Developer status they can also set your `developer_handle` (e.g. `studio-acme`, ≤80 chars, globally unique) and `developer_profile` (Markdown bio). Both fields surface on App listings.

### Are there fees?

The platform doesn't charge submission or listing fees. Promoting an Executa to `visibility=public` does require a paid Anna subscription (Free accounts get `403 Publishing to the public Hub requires a paid plan.`). Apps themselves carry no price tag — developer revenue comes from the usage-based revenue share (see the Earnings view in the Developer Console).

## Versioning & rollouts

### What does versioning actually look like?

Two parallel mechanisms, depending on the artifact:

- **Executa (Tool / Skill)**: each `POST /my/{tools|skills}/{id}/versions` call freezes the current row into an immutable `ExecutaVersion`. Apps that bundle the Executa pin a `min_version`.
- **Anna App**: each app has its own `AnnaAppVersion` rows with their own version strings, changelogs, and `published_at`. Publishing a new version sets `is_latest=True` for that row.

There is no automatic semver-aware staged rollout, no per-version deprecation flag, and no in-app prompt asking users to "accept" a major bump — those behaviours don't exist in the current code.

### Can I do a staged rollout / canary?

Not today. All published versions are visible to every eligible user immediately.

## Credentials & data

### Where are user credentials stored?

In the platform-managed credential store; the Tool process receives them as **environment variables** declared in its manifest at spawn time. Your Tool doesn't see plaintext outside those env vars. See [Credentials & OAuth](/developers/tools/executa-credentials).

### Can my Tool store user data?

Yes — to its own scratch space under the user's data directory. Don't write outside it, don't write secrets, and don't assume the platform will sync the directory across devices. If you need durable cross-device state, point the user at an external service they authenticate against.

### Does Anna read my Tool's stderr?

Yes. The runtime captures stderr and surfaces it in tool execution traces visible to the user. Treat stderr as user-readable debug output — useful for diagnostics, but never log secrets there.

## Support

### Where do I report a platform bug?

Use your usual platform support channel (forum, support email). There is no dedicated in-app "Report a Bug" form documented in the codebase.

### Where do I propose a feature?

Same channel. Triage cadence isn't fixed.

## Anything else?

If your question isn't here, search the rest of the Developer Hub or open a support request through your usual channel. We'll add answers here as they come up.
