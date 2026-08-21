#!/usr/bin/env python3
"""Frontmatter + tree validation for anna-developer-docs.

Canonical copy of the article contract. matrix-nexus's
``src/api/developers.py::parse_article`` must stay behavior-compatible with
this script (cross-referenced there). Design:
matrix-nexus docs/design/developer-docs-open-contribution.md §4.2 / §5.1.

Usage:
    python scripts/validate.py [--docs-root docs]

Exit code 0 = tree valid; 1 = violations (all listed on stderr).
Requires: PyYAML.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent

# Normative section set — mirrors SECTION_ORDER in matrix-nexus. Adding a
# section requires a coordinated Nexus change (design §4.1).
SECTIONS = ("overview", "tools", "skills", "apps", "reference")

SLUG_RE = re.compile(r"^[a-z0-9-]+$")
FM_DELIM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
REQUIRED_FIELDS = {"title", "description", "section", "slug", "order", "updated"}
KNOWN_OPTIONAL = {"estimated_minutes", "category", "verified_runtime", "verified_cli", "redirect_to"}

# Caps mirror the Nexus loader caps (design §7.4) so CI fails before prod would.
MAX_BODY_BYTES = 512 * 1024
MAX_ARTICLES = 500
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_VERSION_LEN = 40


@dataclass
class Article:
    section: str
    slug: str
    title: str
    description: str
    order: int
    updated: str
    body: str
    path: Path
    estimated_minutes: int | None = None
    category: str | None = None
    verified_runtime: str | None = None
    verified_cli: str | None = None
    redirect_to: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_tombstone(self) -> bool:
        return self.redirect_to is not None


def parse_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    match = FM_DELIM_RE.match(text)
    if not match:
        raise ValueError(f"{path}: missing YAML frontmatter")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return meta, text[match.end():]


def parse_article(section: str, path: Path, text: str) -> Article:
    """Validate one article. Raises ValueError with every problem found."""
    meta, body = parse_frontmatter(text, path)
    errors: list[str] = []

    missing = REQUIRED_FIELDS - meta.keys()
    if missing:
        errors.append(f"missing frontmatter fields: {sorted(missing)}")

    slug = str(meta.get("slug", ""))
    if slug and slug != path.stem:
        errors.append(f"frontmatter slug '{slug}' must match filename '{path.stem}'")
    if slug and not SLUG_RE.match(slug):
        errors.append(f"slug must match {SLUG_RE.pattern}")
    if meta.get("section") != section:
        errors.append(f"frontmatter section '{meta.get('section')}' must match folder '{section}'")

    order = meta.get("order")
    if "order" in meta and not isinstance(order, int):
        errors.append("'order' must be an integer")

    updated_raw = meta.get("updated")
    updated = str(updated_raw) if updated_raw is not None else ""
    if updated_raw is not None:
        try:
            updated_date = (
                updated_raw
                if isinstance(updated_raw, _dt.date)
                else _dt.date.fromisoformat(str(updated_raw))
            )
            if updated_date > _dt.date.today():
                errors.append(f"'updated' ({updated_date}) must not be in the future")
        except ValueError:
            errors.append(f"'updated' is not an ISO date: {updated_raw!r}")

    est = meta.get("estimated_minutes")
    if est is not None and not isinstance(est, int):
        errors.append("'estimated_minutes' must be an integer")

    for key in ("verified_runtime", "verified_cli"):
        val = meta.get(key)
        if val is not None:
            if not isinstance(val, str) or not val.strip():
                errors.append(f"'{key}' must be a non-empty string")
            elif len(val) > MAX_VERSION_LEN:
                errors.append(f"'{key}' exceeds {MAX_VERSION_LEN} chars")

    redirect_to = meta.get("redirect_to")
    if redirect_to is not None:
        if not isinstance(redirect_to, str) or not re.match(
            rf"^({'|'.join(SECTIONS)})/[a-z0-9-]+$", redirect_to
        ):
            errors.append("'redirect_to' must be '<section>/<slug>'")
        if body.strip():
            errors.append("tombstone (redirect_to) must have an empty body")

    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        errors.append(f"body exceeds {MAX_BODY_BYTES} bytes")

    if errors:
        raise ValueError(f"{path}: " + "; ".join(errors))

    category = meta.get("category")
    return Article(
        section=section,
        slug=slug,
        title=str(meta["title"]),
        description=str(meta["description"]),
        order=order,  # type: ignore[arg-type]
        updated=updated,
        body=body,
        path=path,
        estimated_minutes=est,
        category=str(category).strip() or None if category is not None else None,
        verified_runtime=meta.get("verified_runtime"),
        verified_cli=meta.get("verified_cli"),
        redirect_to=redirect_to,
        extra={k: v for k, v in meta.items() if k not in REQUIRED_FIELDS | KNOWN_OPTIONAL},
    )


def load_tree(docs_root: Path) -> tuple[list[Article], list[str]]:
    """Load + validate every article. Returns (articles, errors)."""
    articles: list[Article] = []
    errors: list[str] = []
    seen: dict[tuple[str, str], Path] = {}

    if not docs_root.is_dir():
        return [], [f"docs root missing: {docs_root}"]

    for entry in sorted(docs_root.iterdir()):
        if entry.is_dir() and entry.name not in SECTIONS:
            errors.append(f"unknown section directory: {entry}")

    for section in SECTIONS:
        section_dir = docs_root / section
        if not section_dir.is_dir():
            continue
        for md in sorted(section_dir.glob("*.md")):
            try:
                article = parse_article(section, md, md.read_text(encoding="utf-8"))
            except ValueError as exc:
                errors.append(str(exc))
                continue
            key = (article.section, article.slug)
            if key in seen:
                errors.append(f"{md}: duplicate slug '{article.slug}' in section '{section}' (also {seen[key]})")
                continue
            seen[key] = md
            articles.append(article)

    # Cross-article checks.
    keys = {(a.section, a.slug) for a in articles}
    tombstones = {(a.section, a.slug) for a in articles if a.is_tombstone}
    for a in articles:
        if a.redirect_to:
            target = tuple(a.redirect_to.split("/", 1))
            if target not in keys:
                errors.append(f"{a.path}: redirect_to target '{a.redirect_to}' does not exist")
            elif target in tombstones:
                errors.append(f"{a.path}: redirect_to target '{a.redirect_to}' is itself a tombstone")

    if len(articles) > MAX_ARTICLES:
        errors.append(f"article count {len(articles)} exceeds cap {MAX_ARTICLES}")
    total = sum(len(a.body.encode("utf-8")) for a in articles)
    if total > MAX_TOTAL_BYTES:
        errors.append(f"total body bytes {total} exceed cap {MAX_TOTAL_BYTES}")

    return articles, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path, default=REPO / "docs")
    args = parser.parse_args()

    articles, errors = load_tree(args.docs_root)
    if errors:
        print("validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    tombstones = sum(1 for a in articles if a.is_tombstone)
    print(f"OK: {len(articles)} articles ({tombstones} tombstones) across {len(SECTIONS)} sections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
