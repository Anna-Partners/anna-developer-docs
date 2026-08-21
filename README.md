# Anna Developer Docs

Source of truth for the **content** of [anna.partners/developers](https://anna.partners/developers) —
the Anna platform developer documentation: Tools (Executa), Skills, Anna Apps,
and the structured capability Reference.

**Found an error? Open a PR.** Every page on the live site has an
*Edit this page* link that lands here.

## What this repo is (and is not)

| ✅ In this repo | ❌ Not in this repo |
| --- | --- |
| `docs/` — all developer-hub articles (Markdown + frontmatter) | Rendering pipeline (templates, JS, CSS) — platform-private |
| `reference-data/` — the structured Reference catalogue + detail shards | Sidebar section set/ordering (normative in the platform) |
| `scripts/` — validation, link check, bundle build, schema drift check | End-user docs (`/docs`) — separate CMS |
| CI that gates every PR | Runtime behavior — that's the [forum](https://forum.anna.partners/) |

## How content reaches production

```
PR → review (CODEOWNERS) → merge to main → CI builds an immutable bundle
   → published to CDN → the platform picks it up within minutes
```

No platform deploy is involved. Merged content is typically live in **under
10 minutes**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Quick start:

```bash
pip install -r requirements.txt
python scripts/validate.py          # frontmatter + tree contract
python scripts/check_links.py      # internal links + anchors
python scripts/build_bundle.py --dry-run
```

- **Docs error** (docs say X, platform does Y) → PR, or a
  [doc-error issue](../../issues/new?template=doc-error.yml)
- **Missing/unclear docs** → [doc-request issue](../../issues/new?template=doc-request.yml)
- **Platform bug** (behavior wrong, docs right) → [forum](https://forum.anna.partners/)

First maintainer response within **3 business days**.

## Reference data notes

`reference-data/reference.json` sections tagged with `source` are
machine-checked in CI against the published
[`@anna-ai/app-schema`](https://www.npmjs.com/package/@anna-ai/app-schema)
package (version pinned in `.schema-version`). If your correction conflicts
with the schema, the schema wins — unless the schema itself is behind, in
which case note that in the PR and we'll coordinate the bump.

## License

Prose: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ·
Embedded code samples: [MIT](LICENSE). See [LICENSE](LICENSE).
