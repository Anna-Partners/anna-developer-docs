#!/usr/bin/env python3
"""schema-drift check: article claims vs. published packages (design §5.3.1).

Articles that state machine-checkable facts carry a **claims sidecar**
``docs/<section>/<slug>.claims.yaml`` listing the exact literals they claim:

    # docs/apps/app-manifest.claims.yaml
    manifest_fields: [schema, required_executas, host_capabilities]
    capabilities: [aps.kv, llm.sample]
    permissions: [storage.read]
    host_api_methods: [storage.get]
    event_kinds: [...]
    ui_manifest_fields: [...]

Two assertions per claimed literal:

1. **Truth** — the literal exists in the published schema bundle
   (@anna-ai/app-schema, version pinned in ``.schema-version``). This is the
   check that catches forum #99/#248-class errors: dead capability strings,
   wrong manifest field names, phantom methods.
2. **Honesty** — the literal appears verbatim in the article body, so a doc
   edit that drops or renames a fact also fails until the sidecar follows.

Sidecars are optional per article; CI requires every *existing* sidecar to be
valid. Claims are extracted from sidecars, never parsed from prose (§5.3).

Usage:
    python scripts/check_claims.py [--schema-dir DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from schema_sources import CLAIM_TYPES, load_truth, resolve_schema_dir

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"


def check_claims_file(path: Path, truth) -> list[str]:
    errors: list[str] = []
    try:
        rel = path.relative_to(REPO)
    except ValueError:  # fixtures outside the repo (tests)
        rel = path.name

    article = path.with_name(path.name.replace(".claims.yaml", ".md"))
    if not article.is_file():
        return [f"{rel}: no matching article {article.name}"]
    body = article.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{rel}: invalid YAML: {exc}"]
    if not isinstance(data, dict) or not data:
        return [f"{rel}: must be a non-empty mapping of claim types"]

    for claim_type, values in data.items():
        if claim_type not in CLAIM_TYPES:
            errors.append(
                f"{rel}: unknown claim type '{claim_type}' (allowed: {', '.join(CLAIM_TYPES)})"
            )
            continue
        if not isinstance(values, list) or not values:
            errors.append(f"{rel}: '{claim_type}' must be a non-empty list")
            continue
        vocabulary = truth.vocabulary(claim_type)
        for value in values:
            if not isinstance(value, str):
                errors.append(f"{rel}: {claim_type}: non-string entry {value!r}")
                continue
            if value not in vocabulary:
                errors.append(
                    f"{rel}: {claim_type}: '{value}' is not in the published schema "
                    f"— the doc claims something the platform does not ship"
                )
            if value not in body:
                errors.append(
                    f"{rel}: {claim_type}: '{value}' does not appear in {article.name} "
                    f"— stale sidecar, update or remove the claim"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-dir", default=None)
    parser.add_argument("--docs-root", type=Path, default=DOCS)
    args = parser.parse_args()

    truth = load_truth(resolve_schema_dir(args.schema_dir))
    claims_files = sorted(args.docs_root.rglob("*.claims.yaml"))

    errors: list[str] = []
    total_claims = 0
    for path in claims_files:
        errors += check_claims_file(path, truth)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            total_claims += sum(len(v) for v in data.values() if isinstance(v, list))
        except yaml.YAMLError:
            pass

    if errors:
        print("claims check failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        f"OK: {total_claims} claims across {len(claims_files)} sidecars verified "
        "against the published schema bundle."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
