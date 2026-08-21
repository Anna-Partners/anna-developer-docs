---
title: "Publishing a Tool"
description: "From local prototype to a discoverable, installable Executa tool."
section: tools
slug: executa-publish
order: 13
updated: 2026-05-11
estimated_minutes: 6
---

The `/executa` page hosts the Tool / Skill lifecycle: create a draft, fill in the manifest, then choose how widely to publish it. Pro / Max users may publish their own tools.

## 1. Stabilise the manifest

Before publishing, do a self-review:

- [ ] Tool `name`s are stable. Renaming after publish breaks every saved conversation that referenced them.
- [ ] Each `description` reads well to an LLM — it's the prompt the model uses to decide whether to call your tool.
- [ ] Parameters are typed; arrays declare `items` so the LLM passes a real list, not a JSON-encoded string.
- [ ] Failure paths return `{ "success": false, "error": "…actionable message…" }` (or a JSON-RPC `error` for programmer errors).
- [ ] Credentials are declared with stable `name`s.
- [ ] `version` follows SemVer.
- [ ] Plugin process is **long-running** (loops on stdin until EOF). A one-shot process passes `describe` once and then shows up as **Stopped** in the UI forever — see [Common pitfalls](/developers/tools/executa-intro#common-pitfalls).

> [!IMPORTANT]
> **Identity is the server-minted `tool_id` — nothing else.** You **cannot** pick this string yourself; it is always `tool-{author_handle}-{slug}-{uniq}`, reserved by the **🪣 Mint** button, and the platform passes it to the Agent when the tool is installed.
>
> The Agent no longer reads a self-reported manifest `name` (neither the one your binary returns from `describe` nor the one in the archive `manifest.json`). You do **not** need to bake the `tool_id` into either of them. The Agent UI joins user-installed tools to running plugins via the minted `tool_id`.

## 2. Mint a stable `tool_id` first

Open the `/executa` page, switch to the **My Tools** tab, and click **Create Tool**. In the form:

1. Fill in **Name** and **Type** (`tool` / `skill`).
2. Click the **🪪 Mint** button next to the Tool ID field. **This step is mandatory** — the Tool ID input is read-only and the **Create** button is disabled until you mint.

Mint reserves a stable `tool_id` (`tool-{author_handle}-{slug}-{uniq}`) and locks it for your account. Copy this ID — you'll bake it into the binary in the next step. The button then shows **🔒 Minted**, and the ID is yours for the next 24 h even if you walk away (drafts expire after 24 h if never committed).

> [!IMPORTANT]
> **Mint-only policy.** Tool IDs are entirely server-controlled; clients cannot supply or override `tool_id` via the REST API or UI. Any `tool_id` field on a `POST /executas/my/tools` payload is silently dropped. The only way to obtain an ID is via the **🪪 Mint** flow (`POST /executas/my/drafts` → `POST /executas/my/drafts/{id}/commit`).

> [!IMPORTANT]
> Mint **before** building. The `tool_id` is the canonical identity the Agent uses to install, route, and pin versions of your tool. If you publish a binary first, you'll have to rebuild and re-upload everything to align them.

## 3. Build & host artifacts (binary distribution)

Now that you have the `tool_id`, build your tool and host the assets on GitHub Releases or any HTTPS CDN — follow [Binary Distribution](/developers/tools/executa-binary) for platform-key naming. You no longer need to embed the `tool_id` into the manifest your binary returns from `describe` or the `manifest.json` at the archive root; the platform tracks identity via the minted `tool_id` and passes it to the Agent at install time.

If you ship via `uv` / `npm` / `pipx` / `homebrew` instead, publish to that registry now; the Agent installs from there. (Local-only tools can skip this section.)

## 4. Fill in the rest of the form and publish

Back on the `/executa` Create Tool form (the draft you minted in step 2 is still open), fill in the remaining fields and click **Create**:

1. **Manifest** — paste the JSON your binary returns from `describe`. The form auto-extracts tools, credentials, and version.
2. **Distribution** — pick `distribution_type` (`uv` / `npm` / `homebrew` / `binary` / `pipx` / `local`), set `package_name`, `executable_name`, and:
   - For `binary`: the per-platform URLs you hosted in step 3.
   - For `local`: the absolute path to a local archive on the Agent machine (`.tar.gz` / `.tgz` / `.zip` / raw single executable). The Agent runs the **same install pipeline as `binary`** — extracts the archive into `tools/{tool_id}/v{version}/`, resolves the entrypoint, creates the `current` symlink, and registers the bin shim. This means Local **fully supports multi-file binaries** (PyInstaller `--onedir`, native `.so`, etc.); see [Local archive distribution](/developers/tools/executa-binary#local-archive-distribution-no-urls-no-upload).
3. **Capabilities & docs** — logo URL, README, sample prompts, capability tags.
4. **Visibility** — `private`, `app_bundled`, or `public` (see below).

Clicking **Create** promotes the draft into a real Executa under your account. The `tool_id` you minted in step 2 stays the same.

> [!NOTE]
> The whole flow is UI-driven on `/executa`; you don't need to call any HTTP endpoints by hand. The page handles draft reservation, manifest patching, and commit for you.

## 5. Choose a visibility

| Visibility | Where it appears | Who can install |
|---|---|---|
| `private` | Only your `/executa` workspace | Only you |
| `app_bundled` | Hidden from the Explore Hub, but installable as part of any Anna App that bundles it | Anyone who installs the host App |
| `public` | Listed in the Explore Hub | Anyone |

Use `app_bundled` when your tool is meant to ship alongside a specific Anna App rather than as a standalone offering. Switch between the three states using the visibility segmented control on each tool card in **My Tools** — no API call required.

## 5a. Iterate before publishing — the dev loop

You do **not** need to flip visibility to `public` (i.e. **Publish**) to test that your tool installs on an Agent. Doing so prematurely is the common cause of "every failed install leaves a useless tool behind". The intended dev loop is:

1. **Create** the Executa with `visibility=private`, and **Mint** a `tool_id` (sections 2 & 4 above). Don't click Publish yet.
2. From **/executa → My Tools**, click the install/enable toggle so a `UserExecuta` row is created for your account.
3. Go to **/agents → Install Essentials**. Your unpublished private Executa is picked up by the same batch installer the published ones use — `is_published` is **not** a filter on this path.
4. If the install fails, edit the Executa (description, `distribution_url`, `binary_urls`, manifest, …) and click Install Essentials again. **The same `tool_id` is reused on every retry — no new tool created, no cleanup needed.**
5. Only once the install succeeds end-to-end do you promote `visibility` to `app_bundled` (for a host Anna App) or `public` (Hub listing). The first promotion is the point at which an immutable `ExecutaVersion` snapshot is frozen.

> [!TIP]
> Editing an already-bundled tool is allowed and safe: the live row is mutable, but every published Anna App version pins to the **frozen `ExecutaVersion` snapshot** taken at its release, so existing users are not affected. The edit modal shows a banner reminding you of this.

## 6. Publish a new version

When you ship a manifest or binary update, click **New Version** on the tool card. Each publish freezes an immutable `ExecutaVersion` snapshot so apps that pin to a version see stable content. The version number auto-bumps SemVer patch unless you set a specific value in the manifest first.

If the manifest hasn't changed since the last published version, the action is rejected with "No content changes since the last published version" — update the manifest before re-publishing.

## 7. Promote inside an Anna App

The most common discovery path for a tool isn't the Hub — it's an Anna App that bundles it. Once your tool exists (any visibility), an Anna App can list its `tool_id` in the App manifest. See [What is an Anna App](/developers/apps/app-intro).

> [!TIP]
> Tools that don't appear in any App typically see a small fraction of the installs of those that do. Bundle your tool into a complementary App to maximise distribution.
