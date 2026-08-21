"""Tests for check_links.py and build_bundle.py against fixtures + the real tree."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True
    )


GOOD = """---
title: "A"
description: "A."
section: tools
slug: a
order: 1
updated: 2026-01-01
---

## Section One

See [B](/developers/tools/b) and [self](#section-one).
"""

B = GOOD.replace("slug: a", "slug: b").replace('title: "A"', 'title: "B"').replace(
    "See [B](/developers/tools/b) and [self](#section-one).", "Plain."
)


def make_tree(tmp_path: Path) -> tuple[Path, Path]:
    docs = tmp_path / "docs"
    (docs / "tools").mkdir(parents=True)
    (docs / "tools" / "a.md").write_text(GOOD, encoding="utf-8")
    (docs / "tools" / "b.md").write_text(B, encoding="utf-8")
    ref = tmp_path / "reference.json"
    ref.write_text(json.dumps({"version": "1.0", "groups_order": ["X"], "sections": [
        {"group": "X", "id": "host-api-llm", "kicker": "k", "title": "t", "sub": "s",
         "items": [{"name": "n", "desc": "d"}]}
    ]}), encoding="utf-8")
    return docs, ref


def test_links_pass_on_fixture(tmp_path):
    docs, ref = make_tree(tmp_path)
    r = run("check_links.py", "--docs-root", str(docs), "--reference", str(ref))
    assert r.returncode == 0, r.stderr


def test_links_detect_broken_internal(tmp_path):
    docs, ref = make_tree(tmp_path)
    (docs / "tools" / "a.md").write_text(
        GOOD.replace("/developers/tools/b", "/developers/tools/missing"), encoding="utf-8"
    )
    r = run("check_links.py", "--docs-root", str(docs), "--reference", str(ref))
    assert r.returncode == 1
    assert "broken internal link" in r.stderr


def test_links_detect_broken_anchor(tmp_path):
    docs, ref = make_tree(tmp_path)
    (docs / "tools" / "a.md").write_text(
        GOOD.replace("(#section-one)", "(#nope)"), encoding="utf-8"
    )
    r = run("check_links.py", "--docs-root", str(docs), "--reference", str(ref))
    assert r.returncode == 1
    assert "broken in-page anchor" in r.stderr


def test_links_reference_id_resolves(tmp_path):
    docs, ref = make_tree(tmp_path)
    (docs / "tools" / "a.md").write_text(
        GOOD.replace("/developers/tools/b", "/developers/reference/host-api-llm"),
        encoding="utf-8",
    )
    r = run("check_links.py", "--docs-root", str(docs), "--reference", str(ref))
    assert r.returncode == 0, r.stderr


def test_bundle_dry_run_real_tree():
    r = run("build_bundle.py", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "bundle assembles" in r.stdout


def test_bundle_out_layout(tmp_path):
    out = tmp_path / "build"
    r = run("build_bundle.py", "--out", str(out), "--commit", "deadbeef")
    assert r.returncode == 0, r.stderr
    root = out / "developers-hub"
    pointer = json.loads((root / "manifest.json").read_text())
    assert pointer == {"schema_version": 1, "bundle": "developers-hub/bundles/deadbeef.json"}
    manifest = json.loads((root / "bundles" / "deadbeef.json").read_text())
    assert manifest["commit"] == "deadbeef"
    assert manifest["totals"]["articles"] == len(manifest["articles"])
    # Every manifest entry exists on disk at its declared path.
    for entry in manifest["articles"]:
        assert (out / entry["path"]).is_file()
    assert (out / manifest["reference"]["catalogue"]["path"]).is_file()
    for shard in manifest["reference"]["shards"]:
        assert (out / shard["path"]).is_file()


def test_reference_schema_validates_real_data():
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_reference.py")], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
