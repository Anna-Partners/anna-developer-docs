#!/usr/bin/env python3
"""Bundle assembly for anna-developer-docs.

Produces the immutable bundle layout consumed by Nexus (design §5.2):

    out/
    ├── manifest.json                    ← pointer {"schema_version": 1, "bundle": ...}
    ├── bundles/<commit>.json            ← full manifest (articles + reference)
    ├── content/<commit>/<section>/<slug>.md
    └── reference/<commit>/{reference.json,shards/*.json}

Usage:
    python scripts/build_bundle.py --dry-run          # CI: validate assembly
    python scripts/build_bundle.py --out build/       # local dev / publish step

Upload to R2 + pointer flip live in publish.yml (P2), not here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import MAX_TOTAL_BYTES, load_tree  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PREFIX = "developers-hub"
MAX_MANIFEST_BYTES = 256 * 1024
REPO_URL = "https://github.com/whtcjdtc2007/anna-developer-docs"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - non-git contexts (CI tarballs, tests)
        return "workingtree"


def build_manifest(docs_root: Path, reference_dir: Path, commit: str) -> tuple[dict, list[str]]:
    articles, errors = load_tree(docs_root)
    if errors:
        return {}, errors

    entries = []
    total = 0
    for a in articles:
        raw = a.path.read_bytes()
        total += len(raw)
        entries.append(
            {
                "section": a.section,
                "slug": a.slug,
                "path": f"{PREFIX}/content/{commit}/{a.section}/{a.slug}.md",
                "sha256": _sha256(raw),
                "bytes": len(raw),
            }
        )
    if total > MAX_TOTAL_BYTES:
        errors.append(f"bundle content {total} bytes exceeds cap {MAX_TOTAL_BYTES}")

    catalogue = reference_dir / "reference.json"
    if not catalogue.is_file():
        errors.append(f"missing reference catalogue: {catalogue}")
        return {}, errors
    try:
        ref_version = str(json.loads(catalogue.read_text(encoding="utf-8")).get("version", "1.0"))
    except json.JSONDecodeError as exc:
        errors.append(f"{catalogue}: invalid JSON: {exc}")
        return {}, errors

    shards = []
    for shard in sorted((reference_dir / "shards").glob("*.json")):
        shards.append(
            {
                "path": f"{PREFIX}/reference/{commit}/shards/{shard.name}",
                "sha256": _sha256(shard.read_bytes()),
            }
        )

    manifest = {
        "schema_version": 1,
        "repo": REPO_URL,
        "commit": commit,
        "built_at": None,  # stamped at publish time
        "articles": entries,
        "reference": {
            "schema_version": ref_version,
            "catalogue": {
                "path": f"{PREFIX}/reference/{commit}/reference.json",
                "sha256": _sha256(catalogue.read_bytes()),
            },
            "shards": shards,
        },
        "totals": {"articles": len(entries), "bytes": total},
    }
    raw_manifest = json.dumps(manifest).encode("utf-8")
    if len(raw_manifest) > MAX_MANIFEST_BYTES:
        errors.append(f"manifest {len(raw_manifest)} bytes exceeds cap {MAX_MANIFEST_BYTES}")
    return manifest, errors


def write_layout(manifest: dict, docs_root: Path, reference_dir: Path, out: Path) -> None:
    commit = manifest["commit"]
    root = out / PREFIX
    if root.exists():
        shutil.rmtree(root)
    for entry in manifest["articles"]:
        src = docs_root / entry["section"] / f"{entry['slug']}.md"
        dst = out / entry["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    ref_dst = root / "reference" / commit
    (ref_dst / "shards").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(reference_dir / "reference.json", ref_dst / "reference.json")
    for shard in sorted((reference_dir / "shards").glob("*.json")):
        shutil.copyfile(shard, ref_dst / "shards" / shard.name)
    bundles = root / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    (bundles / f"{commit}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "bundle": f"{PREFIX}/bundles/{commit}.json"}),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path, default=REPO / "docs")
    parser.add_argument("--reference-dir", type=Path, default=REPO / "reference-data")
    parser.add_argument("--commit", default=None)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--out", type=Path)
    args = parser.parse_args()

    commit = args.commit or _git_commit()
    manifest, errors = build_manifest(args.docs_root, args.reference_dir, commit)
    if errors:
        print("bundle assembly failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        t = manifest["totals"]
        print(
            f"OK: bundle assembles — {t['articles']} articles, {t['bytes']} bytes, "
            f"{len(manifest['reference']['shards'])} reference shards, commit {commit[:12]}."
        )
        return 0

    write_layout(manifest, args.docs_root, args.reference_dir, args.out)
    print(f"OK: bundle written to {args.out / PREFIX} (commit {commit[:12]}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
