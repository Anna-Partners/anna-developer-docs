#!/usr/bin/env python3
"""Validate reference-data/ against the render-contract JSON Schemas.

Part of the CI ``reference-validate`` job (design §5.1 job 4), alongside
``check_reference_drift.py``. Also cross-checks that every ``detail_source``
declared in the catalogue has a matching shard file (and vice versa) and that
shard ``section_id``s exist in the catalogue.

Requires: jsonschema.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "reference-data"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []
    catalogue = _load(DATA / "reference.json")
    catalogue_schema = _load(DATA / "schema" / "catalogue.schema.json")
    shard_schema = _load(DATA / "schema" / "shard.schema.json")

    validator = jsonschema.Draft202012Validator(catalogue_schema)
    for err in validator.iter_errors(catalogue):
        errors.append(f"reference.json: {'/'.join(map(str, err.path))}: {err.message}")

    section_ids = {s["id"] for s in catalogue.get("sections", []) if "id" in s}
    declared = {
        Path(s["detail_source"]).name: s["id"]
        for s in catalogue.get("sections", [])
        if s.get("detail_source")
    }

    shard_validator = jsonschema.Draft202012Validator(shard_schema)
    shard_files = sorted((DATA / "shards").glob("*.json"))
    for shard_path in shard_files:
        shard = _load(shard_path)
        for err in shard_validator.iter_errors(shard):
            errors.append(f"{shard_path.name}: {'/'.join(map(str, err.path))}: {err.message}")
        sid = shard.get("section_id")
        if sid and sid not in section_ids:
            errors.append(f"{shard_path.name}: section_id '{sid}' not in catalogue")

    shard_names = {p.name for p in shard_files}
    for fname, sid in declared.items():
        if fname not in shard_names:
            errors.append(f"reference.json: section '{sid}' declares detail_source '{fname}' but shard file is missing")

    if errors:
        print("reference-data schema validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: catalogue + {len(shard_files)} shards conform to the render contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
