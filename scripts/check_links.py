#!/usr/bin/env python3
"""Link checker for anna-developer-docs.

Blocking checks (exit 1):
- ``/developers/<section>/<slug>`` links must resolve to an article, a
  tombstone, or a reference catalogue section id from
  ``reference-data/reference.json`` (v1.2: reference lives in this repo, so
  ids are read directly — no fetched allowlist needed).
- In-article anchors (``#heading`` and ``/developers/...#heading``) must match
  a generated heading id in the target article (same slugify rules as the
  platform renderer).

Warn-only (never fails CI):
- External http(s) links, checked with HEAD (5s timeout) only when
  ``--external`` is passed; other absolute site paths outside /developers.

Usage: python scripts/check_links.py [--docs-root docs] [--external]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import SECTIONS, load_tree  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
LINK_RE = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# Nexus-owned routes that are valid link targets but not articles.
SITE_ROUTES = {
    "/developers",
    "/developers/reference",
    "/llms.txt",
    "/llms-full.txt",
}


def slugify_heading(text: str) -> str:
    """GitHub-style heading id — mirrors the platform renderer's TOC slugify."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[\s]+", "-", text)


def heading_ids(body: str) -> set[str]:
    ids: set[str] = set()
    for line in CODE_FENCE_RE.sub("", body).splitlines():
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            ids.add(slugify_heading(m.group(1)))
    return ids


def reference_ids(reference_path: Path) -> set[str]:
    try:
        data = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {s.get("id") for s in data.get("sections", []) if s.get("id")}


def check_external(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "anna-docs-linkcheck"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 400:
                return f"HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001 - warn-only path
        return str(exc)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path, default=REPO / "docs")
    parser.add_argument("--reference", type=Path, default=REPO / "reference-data" / "reference.json")
    parser.add_argument("--external", action="store_true", help="also HEAD-check external links (warn-only)")
    args = parser.parse_args()

    articles, tree_errors = load_tree(args.docs_root)
    if tree_errors:
        print("tree invalid — run scripts/validate.py first", file=sys.stderr)
        return 1

    by_key = {(a.section, a.slug): a for a in articles}
    ref_ids = reference_ids(args.reference)
    errors: list[str] = []
    warnings: list[str] = []

    for article in articles:
        own_anchors = heading_ids(article.body)
        for m in LINK_RE.finditer(CODE_FENCE_RE.sub("", article.body)):
            target = m.group(1)
            if target.startswith(("http://", "https://")):
                if args.external:
                    problem = check_external(target)
                    if problem:
                        warnings.append(f"{article.path}: external {target} -> {problem}")
                continue
            if target.startswith("mailto:"):
                continue
            if target.startswith("#"):
                if target[1:] not in own_anchors:
                    errors.append(f"{article.path}: broken in-page anchor '{target}'")
                continue
            if not target.startswith("/"):
                warnings.append(f"{article.path}: relative link '{target}' (prefer absolute /developers/... paths)")
                continue

            path, _, anchor = target.partition("#")
            path = path[:-3] if path.endswith(".md") else path
            path = path.rstrip("/")

            if path in SITE_ROUTES:
                continue
            m_ref = re.match(r"^/developers/reference/([a-z0-9-]+)(?:/[a-z0-9-]+)?$", path)
            m_art = re.match(rf"^/developers/({'|'.join(SECTIONS)})/([a-z0-9-]+)$", path)
            if m_art and (m_art.group(1), m_art.group(2)) in by_key:
                if anchor:
                    target_article = by_key[(m_art.group(1), m_art.group(2))]
                    if anchor not in heading_ids(target_article.body):
                        errors.append(f"{article.path}: broken anchor '{target}'")
                continue
            if m_ref and (m_ref.group(1) in ref_ids or ("reference", m_ref.group(1)) in by_key):
                continue
            if path.startswith("/developers/"):
                errors.append(f"{article.path}: broken internal link '{target}'")
            else:
                warnings.append(f"{article.path}: unverifiable site link '{target}'")

    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        print("link check failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: links valid across {len(articles)} articles ({len(warnings)} warnings).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
