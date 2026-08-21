#!/usr/bin/env python3
"""Drift check: reference-data/reference.json ↔ published @anna-ai/app-schema.

Ported from matrix-nexus scripts/check_reference_drift.py (design §5.1 job 4).
Sections carrying ``source: "host_api" | "events" | "app_manifest"`` must list
exactly the items in the matching schema artefact of the **published**
@anna-ai/app-schema npm package (version pinned in ``.schema-version``,
installed by CI via ``npm i``).

The ``platform_tools`` source has no public artefact yet — those sections are
review-gated only (skipped here, unlike the Nexus original which imports the
private registry).

Schema dir resolution order: --schema-dir, $ANNA_APP_SCHEMA_DIR,
./node_modules/@anna-ai/app-schema.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REFERENCE = REPO / "reference-data" / "reference.json"


def _iter_items(section: dict) -> Iterable[dict]:
    if section.get("groups"):
        for g in section["groups"]:
            yield from g.get("items", [])
    else:
        yield from section.get("items", [])


def _collect(reference: dict, source: str) -> set[str]:
    names: set[str] = set()
    for s in reference["sections"]:
        if s.get("source") != source:
            continue
        for item in _iter_items(s):
            names.add(item["name"])
    return names


def _diff(label: str, expected: set[str], actual: set[str]) -> list[str]:
    errs: list[str] = []
    missing = expected - actual
    extra = actual - expected
    if missing:
        errs.append(f"[{label}] missing from reference.json: {sorted(missing)}")
    if extra:
        errs.append(f"[{label}] extra in reference.json (not in schema): {sorted(extra)}")
    return errs


def resolve_schema_dir(arg: str | None) -> Path:
    candidates = [
        arg,
        os.environ.get("ANNA_APP_SCHEMA_DIR"),
        REPO / "node_modules" / "@anna-ai" / "app-schema",
    ]
    for c in candidates:
        if c and Path(c).is_dir():
            return Path(c)
    raise SystemExit(
        "schema package not found — run `npm i @anna-ai/app-schema@$(cat .schema-version)` "
        "or pass --schema-dir / set ANNA_APP_SCHEMA_DIR"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-dir", default=None)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    args = parser.parse_args()
    schema = resolve_schema_dir(args.schema_dir)

    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    methods = json.loads((schema / "host_api" / "methods.json").read_text(encoding="utf-8"))
    events = json.loads((schema / "events" / "AnnaAppEvent.json").read_text(encoding="utf-8"))
    manifest = json.loads((schema / "manifest" / "AppManifest.json").read_text(encoding="utf-8"))

    expected_host = {f"{r['namespace']}.{r['method']}" for r in methods["methods"]}
    expected_events = set(events["properties"]["kind"]["enum"])
    expected_manifest = set(manifest["properties"].keys())

    errors: list[str] = []
    errors += _diff("host_api", expected_host, _collect(reference, "host_api"))
    errors += _diff("events", expected_events, _collect(reference, "events"))
    errors += _diff("app_manifest", expected_manifest, _collect(reference, "app_manifest"))

    if errors:
        print("reference.json drift detected (vs published @anna-ai/app-schema):\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nIf the schema is right: fix reference-data/reference.json.\n"
            "If the docs are right: the published schema is behind — bump "
            ".schema-version once the new package ships.",
            file=sys.stderr,
        )
        return 1

    print(
        "reference.json: in sync with @anna-ai/app-schema "
        f"(host_api={len(expected_host)} events={len(expected_events)} "
        f"app_manifest={len(expected_manifest)}; platform_tools sections are review-gated)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
