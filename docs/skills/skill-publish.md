---
title: "Publishing a Skill"
description: "Submit your skill so other users can discover and install it."
section: skills
slug: skill-publish
order: 4
updated: 2026-04-23
estimated_minutes: 5
---

Once your skill is stable, publishing puts it in the Explore catalogue alongside the platform-bundled skills. Because **a Skill is just an Executa with `executa_type="skill"`**, it shares the *exact same* draft / version / visibility pipeline as a Tool Executa — same wizard, same REST surface, same Hub.

## 1. Prepare

- [ ] `SKILL.md` has the required frontmatter (`name`, `description`).
- [ ] `metadata.matrix` declares `execution_mode`, `category_name`, and (if applicable) `requires` / `install` / `uninstall`.
- [ ] Body is self-contained — no references to files outside the skill folder.
- [ ] You have a one-line and one-paragraph description ready for the listing.
- [ ] Optional: a screenshot/GIF showing the skill in action.

> [!WARNING]
> Don't include credentials, `.env` files, or anything you wouldn't paste into a public gist. The skill body ships verbatim to anyone who installs it.

## 2. Create the Skill via the wizard

The `/executa` page has a draft-first flow shared by both Executa flavours — you pick `Skill` at step 1 and the rest of the wizard adapts:

```
POST   /api/v1/executas/my/drafts                    → reserves tool_id (executa_type="skill")
PATCH  /api/v1/executas/my/drafts/{id}               → fill in skill_content + metadata
POST   /api/v1/executas/my/drafts/{id}/commit        → promote draft → Skill Executa
```

The UI walks through:

1. **Name & type** — pick `Skill`. The server returns a `tool_id` like `skill-{author_handle}-{slug}-{uniq}` you can copy into App manifests.
2. **Body & metadata** — paste the markdown of `SKILL.md`. The wizard parses your frontmatter (`metadata.matrix`) and surfaces `execution_mode`, `category_name`, and dependency declarations as form fields.
3. **Capabilities & docs** — logo, README, sample prompts.
4. **Visibility** — `private`, `app_bundled`, or `public`.
5. **Commit** — the draft becomes a real Skill Executa.

Drafts auto-expire after 24 h if you don't commit (server-enforced TTL).

Direct REST mirrors are available for scripting:

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/v1/executas/my/skills` | List your Skill Executas |
| `POST` | `/api/v1/executas/my/skills/import` | Create a Skill from a JSON payload (server-side validates the frontmatter) |
| `GET`  | `/api/v1/executas/my/skills/{id}/detail` | Fetch full Skill detail |
| `PUT`  | `/api/v1/executas/my/skills/{id}` | Update body / metadata |
| `DELETE` | `/api/v1/executas/my/skills/{id}` | Delete the Skill |
| `GET`  | `/api/v1/executas/my/skills/{id}/export` | Round-trip the skill back to a payload you can re-import |
| `POST` | `/api/v1/executas/my/skills/{id}/publish` | Promote to `visibility=public` (Pro / Max) |
| `POST` | `/api/v1/executas/my/skills/{id}/unpublish` | Revert to `private` |
| `POST` | `/api/v1/executas/my/skills/{id}/visibility` | Set visibility explicitly (`private` / `app_bundled` / `public`) |
| `POST` | `/api/v1/executas/my/skills/{id}/versions` | Freeze a new immutable version snapshot |

## 3. Visibility model

| Visibility | Where it appears | Who can install |
|---|---|---|
| `private` | Only your `/executa` workspace | Only you |
| `app_bundled` | Hidden from Explore, installable as part of any Anna App that bundles it | Anyone who installs the host App |
| `public` | Listed in the Explore Hub | Anyone |

Use `app_bundled` when the skill only makes sense alongside a particular App.

## 4. Versioning

Every `POST /my/skills/{id}/versions` call freezes the current body + metadata into an immutable `ExecutaVersion`. If nothing changed since the last published version, the call returns `409 Conflict` so you don't ship empty updates.

Apps that pin a `min_version` see content frozen at that snapshot; users on auto-update get the latest snapshot at install time.

## 5. Bundle into an App

The highest-leverage distribution is being part of an Anna App. See [What is an Anna App](/developers/apps/app-intro) for how Apps bundle skills, tools, and prompts into a one-click install.

> [!NOTE]
> Self-hosted catalogues are on the roadmap. For now everything goes through the public Explore Hub review.
