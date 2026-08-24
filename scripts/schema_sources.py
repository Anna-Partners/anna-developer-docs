#!/usr/bin/env python3
"""Shared loaders for the published machine-truth artefacts (design §5.3).

Every P3 verification script (check_claims / generate_reference /
check_reference_drift) resolves the @anna-ai/app-schema package the same way
and reads the same truth sets from it. One loader, one resolution order:

    --schema-dir → $ANNA_APP_SCHEMA_DIR → ./node_modules/@anna-ai/app-schema

Capabilities/permissions come from ``acl/capabilities.json`` inside the
package (bundle ≥ 0.20); until that ships, the byte-identical snapshot in
``scripts/data/acl-capabilities-snapshot.json`` is the fallback.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_ACL_SNAPSHOT = Path(__file__).resolve().parent / "data" / "acl-capabilities-snapshot.json"


def resolve_schema_dir(arg: str | None = None) -> Path:
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


@dataclass(frozen=True)
class Truth:
    """Machine-truth vocabularies derived from the published schema bundle."""

    host_api_methods: frozenset[str]
    event_kinds: frozenset[str]
    manifest_fields: frozenset[str]
    ui_manifest_fields: frozenset[str]
    capabilities: frozenset[str]
    permissions: frozenset[str]

    def vocabulary(self, claim_type: str) -> frozenset[str]:
        return getattr(self, claim_type)


CLAIM_TYPES = (
    "host_api_methods",
    "event_kinds",
    "manifest_fields",
    "ui_manifest_fields",
    "capabilities",
    "permissions",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_truth(schema_dir: Path) -> Truth:
    methods = _load_json(schema_dir / "host_api" / "methods.json")
    events = _load_json(schema_dir / "events" / "AnnaAppEvent.json")
    manifest = _load_json(schema_dir / "manifest" / "AppManifest.json")
    ui = _load_json(schema_dir / "manifest" / "UiManifestSection.json")

    acl_path = schema_dir / "acl" / "capabilities.json"
    if not acl_path.is_file():
        acl_path = _ACL_SNAPSHOT
    acl = _load_json(acl_path)

    return Truth(
        host_api_methods=frozenset(
            f"{r['namespace']}.{r['method']}" for r in methods["methods"]
        ),
        event_kinds=frozenset(events["properties"]["kind"]["enum"]),
        manifest_fields=frozenset(manifest["properties"].keys()),
        ui_manifest_fields=frozenset(ui["properties"].keys()),
        capabilities=frozenset(acl["host_capabilities"]),
        permissions=frozenset(acl["permissions"]),
    )
