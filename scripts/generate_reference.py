#!/usr/bin/env python3
"""Reference generation: machine-derived skeleton + prose overrides (§9.2).

The sections of ``reference-data/reference.json`` that carry
``source: host_api | events | app_manifest`` are **generated**:

* the *item name sets* come from the published @anna-ai/app-schema bundle
  (the skeleton — field tables, method tables, event kinds);
* the *prose* (``desc``, ``tags``, per-section item order and the
  section-to-item assignment) comes from the override file
  ``reference-data/overrides/reference-prose.json``.

Hand edits inside generated sections of reference.json are rejected by the
``--check`` CI job (regenerate-diff — the Kubernetes rule, §9.2): contributors
edit the override file (prose) or bump ``.schema-version`` (facts), then run
this script. Hand-authored sections (Executa/Skill/CLI/Lifecycle and the
review-gated ``platform_tools``) are passed through untouched.

Failure modes are the drift signals working as intended:

* schema ships a new method/field/kind → generation fails until an override
  entry (with prose) is added;
* an override names something the schema no longer ships → generation fails;
* reference.json was hand-edited in a generated section → ``--check`` fails.

Usage:
    python scripts/generate_reference.py                # regenerate in place
    python scripts/generate_reference.py --check        # CI gate
    python scripts/generate_reference.py --extract-overrides  # bootstrap
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from schema_sources import Truth, load_truth, resolve_schema_dir

REPO = Path(__file__).resolve().parent.parent
REFERENCE = REPO / "reference-data" / "reference.json"
OVERRIDES = REPO / "reference-data" / "overrides" / "reference-prose.json"

# Sources with a published machine artefact (platform_tools has none — that
# source stays review-gated and hand-authored, mirroring check_reference_drift).
GENERATED_SOURCES = {
    "host_api": "host_api_methods",
    "events": "event_kinds",
    "app_manifest": "manifest_fields",
}


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def extract_overrides(reference: dict) -> dict:
    """Bootstrap the override file from the current reference.json prose."""
    out: dict = {
        "$comment": (
            "Prose overrides for the GENERATED sections of reference.json "
            "(design §9.2). Item names must exactly cover the published "
            "schema artefacts; desc/tags/order are editorial. Edit THIS file "
            "(not reference.json) and run scripts/generate_reference.py."
        )
    }
    for section in reference["sections"]:
        if section.get("source") not in GENERATED_SOURCES:
            continue
        out[section["id"]] = {
            "source": section["source"],
            "items": [dict(item) for item in section.get("items", [])],
        }
    return out


def generate(reference: dict, overrides: dict, truth: Truth) -> tuple[dict, list[str]]:
    errors: list[str] = []
    override_ids = {k for k in overrides if not k.startswith("$")}
    section_ids = {
        s["id"] for s in reference["sections"] if s.get("source") in GENERATED_SOURCES
    }

    for missing in sorted(section_ids - override_ids):
        errors.append(f"generated section '{missing}' has no override entry")
    for orphan in sorted(override_ids - section_ids):
        errors.append(f"override entry '{orphan}' matches no generated section")

    # Global per-source coverage: union of override names == schema truth.
    claimed: dict[str, dict[str, str]] = {src: {} for src in GENERATED_SOURCES}
    for sid in sorted(override_ids & section_ids):
        entry = overrides[sid]
        source = entry.get("source")
        if source not in GENERATED_SOURCES:
            errors.append(f"override '{sid}': unknown source {source!r}")
            continue
        for item in entry.get("items", []):
            name = item.get("name")
            if not isinstance(name, str) or not name:
                errors.append(f"override '{sid}': item without a name")
                continue
            if name in claimed[source]:
                errors.append(
                    f"override '{sid}': '{name}' already assigned to section "
                    f"'{claimed[source][name]}'"
                )
                continue
            claimed[source][name] = sid
            if not str(item.get("desc", "")).strip():
                errors.append(
                    f"override '{sid}': '{name}' needs prose (`desc`) — new schema "
                    "items require a human sentence before they publish"
                )

    for source, truth_key in GENERATED_SOURCES.items():
        expected = truth.vocabulary(truth_key)
        actual = set(claimed[source])
        for name in sorted(expected - actual):
            errors.append(
                f"[{source}] '{name}' shipped in the schema but no override claims "
                "it — add it (with prose) to the matching section in "
                "reference-data/overrides/reference-prose.json"
            )
        for name in sorted(actual - expected):
            errors.append(
                f"[{source}] '{name}' is in the overrides but not in the published "
                f"schema — remove it (section '{claimed[source][name]}')"
            )

    if errors:
        return reference, errors

    # Rebuild the generated sections' items from the overrides (canonical
    # item shape: name/desc[/tags]); everything else passes through verbatim.
    for section in reference["sections"]:
        if section.get("source") not in GENERATED_SOURCES:
            continue
        rebuilt = []
        for item in overrides[section["id"]]["items"]:
            new_item = {"name": item["name"], "desc": item["desc"]}
            if item.get("tags"):
                new_item["tags"] = item["tags"]
            rebuilt.append(new_item)
        section["items"] = rebuilt
        section.pop("groups", None)
    return reference, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-dir", default=None)
    parser.add_argument("--check", action="store_true", help="diff mode (CI)")
    parser.add_argument("--extract-overrides", action="store_true")
    args = parser.parse_args()

    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))

    if args.extract_overrides:
        OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDES.write_text(_dump(extract_overrides(reference)), encoding="utf-8")
        print(f"OK: overrides extracted → {OVERRIDES.relative_to(REPO)}")
        return 0

    truth = load_truth(resolve_schema_dir(args.schema_dir))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))

    generated, errors = generate(reference, overrides, truth)
    if errors:
        print("reference generation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    output = _dump(generated)
    if args.check:
        committed = REFERENCE.read_text(encoding="utf-8")
        if committed != output:
            print(
                "reference.json is out of sync with its generated form.\n"
                "Hand edits in generated sections are rejected (§9.2): edit\n"
                "reference-data/overrides/reference-prose.json instead, then run\n"
                "`python scripts/generate_reference.py` and commit both files.",
                file=sys.stderr,
            )
            return 1
        print("OK: reference.json matches its generated form.")
        return 0

    REFERENCE.write_text(output, encoding="utf-8")
    n = sum(len(v.get("items", [])) for k, v in overrides.items() if not k.startswith("$"))
    print(f"OK: regenerated {len(GENERATED_SOURCES)} sources ({n} items) → reference.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
