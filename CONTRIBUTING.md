# Contributing to the Anna Developer Docs

Thanks for helping keep the docs true. Corrections like
[forum #248](https://forum.anna.partners/t/248) are exactly what this repo
exists for — as pull requests instead of forum prose.

## What lives where

| Path | What it is | How to change it |
| --- | --- | --- |
| `docs/<section>/<slug>.md` | Articles rendered at `https://anna.partners/developers/<section>/<slug>` | PR |
| `reference-data/reference.json` + `reference-data/shards/` | The structured Reference catalogue at `/developers/reference` | PR — source-tagged sections are machine-checked against the published `@anna-ai/app-schema` (CI `reference-validate`) |
| `docs/reference/developer-terms.md` | Legal text | **Admin-only** — community changes are not accepted |
| Sidebar sections, rendering, styling | Platform code (private) | Not in this repo — open a doc-request issue |

Runtime **behavior** problems (the platform does something wrong, not the docs
describing it wrong) belong on the [forum](https://forum.anna.partners/), not here.

## Before you open a PR

1. **Verify against a real version.** State the runtime and CLI version you
   tested against in the PR body. If engineering confirmed the behavior in a
   forum thread, link it.
2. **Run the checks locally:**

   ```bash
   pip install -r requirements.txt
   python scripts/validate.py
   python scripts/check_links.py
   python scripts/build_bundle.py --dry-run
   ```

3. **Preview:** any Markdown previewer is fine for prose. Pixel-exact
   rendering (admonitions, code-copy buttons, TOC) only exists on the
   platform — that's expected; reviewers care about correctness, not pixels.

## Authoring rules

- **Frontmatter contract** — every article starts with:

  ```yaml
  ---
  title: "Persistent Storage (APS)"
  description: "One-sentence summary, ≤160 chars."   # meta description
  section: tools        # must match the folder
  slug: my-article      # must match the filename
  order: 7              # sidebar position within the section
  updated: 2026-08-21   # bump when you materially change the page
  # optional:
  estimated_minutes: 8
  category: "Host capabilities"        # sidebar sub-grouping
  verified_runtime: "1.1.0-beta.135"   # renders a "Verified against" badge
  verified_cli: "0.1.49"
  redirect_to: "tools/new-slug"        # tombstone — body must be empty
  ---
  ```

- **Slugs are public URLs — never rename.** To move a page, create the new
  file and turn the old one into a tombstone (`redirect_to`, empty body).
- **Code samples must be runnable as written.** Include imports/shebang.
  Don't paraphrase wire payloads — paste real ones (redact tokens).
- Second person ("you"), US English, present tense.
- Internal links are absolute (`/developers/tools/executa-intro`); deep-link
  external code only to **published** artifacts (npm/PyPI/public repos).
- Never include credentials, internal hostnames, or private source paths.

## Review & merge

- CI must be green (`validate`, `links`, `build-dry-run`,
  `reference-validate`, `tests`).
- One maintainer approval (CODEOWNERS) merges via **squash**. First response
  within 3 business days.
- After merge, publication to the live site is automatic (no action needed).

## Licensing of contributions

By contributing you agree that your prose contributions are licensed under
**CC BY 4.0** and embedded code samples under **MIT** (see `LICENSE`).
