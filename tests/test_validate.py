"""Tests for scripts/validate.py — the canonical article contract."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate import load_tree, parse_article  # noqa: E402

GOOD = """---
title: "Test Article"
description: "A test."
section: tools
slug: test-article
order: 1
updated: 2026-01-01
---

Body text.
"""


def write(root: Path, section: str, slug: str, text: str) -> Path:
    d = root / section
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_good_article_parses(tmp_path):
    p = write(tmp_path, "tools", "test-article", GOOD)
    a = parse_article("tools", p, p.read_text())
    assert a.slug == "test-article" and not a.is_tombstone


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (lambda t: t.replace('title: "Test Article"\n', ""), "missing frontmatter fields"),
        (lambda t: t.replace("slug: test-article", "slug: other"), "must match filename"),
        (lambda t: t.replace("section: tools", "section: apps"), "must match folder"),
        (lambda t: t.replace("order: 1", 'order: "one"'), "'order' must be an integer"),
        (lambda t: t.replace("updated: 2026-01-01", "updated: 2099-01-01"), "must not be in the future"),
        (lambda t: t.replace("updated: 2026-01-01", "updated: not-a-date"), "not an ISO date"),
        (lambda t: t.replace("---\n\nBody", "verified_cli: \"" + "x" * 41 + "\"\n---\n\nBody"), "exceeds 40 chars"),
    ],
)
def test_violations_rejected(tmp_path, mutation, fragment):
    p = write(tmp_path, "tools", "test-article", mutation(GOOD))
    with pytest.raises(ValueError, match=fragment.replace("(", "\\(").replace(")", "\\)")):
        parse_article("tools", p, p.read_text())


def test_tombstone_requires_empty_body(tmp_path):
    text = GOOD.replace("---\n\nBody text.\n", 'redirect_to: "tools/target"\n---\n\nBody text.\n')
    p = write(tmp_path, "tools", "test-article", text)
    with pytest.raises(ValueError, match="empty body"):
        parse_article("tools", p, p.read_text())


def test_oversize_body_rejected(tmp_path):
    p = write(tmp_path, "tools", "test-article", GOOD + "x" * (512 * 1024))
    with pytest.raises(ValueError, match="body exceeds"):
        parse_article("tools", p, p.read_text())


def test_tree_redirect_target_must_exist(tmp_path):
    tomb = GOOD.replace("---\n\nBody text.\n", 'redirect_to: "tools/nowhere"\n---\n')
    write(tmp_path, "tools", "test-article", tomb)
    _, errors = load_tree(tmp_path)
    assert any("does not exist" in e for e in errors)


def test_tree_redirect_chain_rejected(tmp_path):
    t1 = GOOD.replace("---\n\nBody text.\n", 'redirect_to: "tools/b"\n---\n')
    t2 = (
        GOOD.replace("slug: test-article", "slug: b")
        .replace('title: "Test Article"', 'title: "B"')
        .replace("---\n\nBody text.\n", 'redirect_to: "tools/test-article"\n---\n')
    )
    write(tmp_path, "tools", "test-article", t1)
    write(tmp_path, "tools", "b", t2)
    _, errors = load_tree(tmp_path)
    assert any("itself a tombstone" in e for e in errors)


def test_tree_unknown_section_flagged(tmp_path):
    write(tmp_path, "tools", "test-article", GOOD)
    (tmp_path / "secrets").mkdir()
    _, errors = load_tree(tmp_path)
    assert any("unknown section directory" in e for e in errors)


def test_real_tree_is_valid():
    """The shipped docs/ tree must always pass its own contract."""
    root = Path(__file__).resolve().parent.parent / "docs"
    articles, errors = load_tree(root)
    assert errors == []
    assert len(articles) >= 40
