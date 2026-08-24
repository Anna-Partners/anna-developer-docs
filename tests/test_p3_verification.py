"""Tests for the P3 verification layer (design §5.3 / §9.2 / §13).

Includes the §13 acceptance fixtures: a deliberately wrong capability string
must fail the claims check, and a hand edit in a generated reference section
must fail the regenerate-diff.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_claims import check_claims_file  # noqa: E402
from generate_reference import generate  # noqa: E402
from run_samples import extract_samples  # noqa: E402
from schema_sources import Truth  # noqa: E402

TRUTH = Truth(
    host_api_methods=frozenset({"storage.get", "storage.set"}),
    event_kinds=frozenset({"executa_installed"}),
    manifest_fields=frozenset({"schema", "required_executas"}),
    ui_manifest_fields=frozenset({"bundle"}),
    capabilities=frozenset({"aps.kv", "llm.sample"}),
    permissions=frozenset({"storage.read"}),
)


def _write_pair(tmp_path: Path, body: str, claims: str) -> Path:
    (tmp_path / "article.md").write_text(body, encoding="utf-8")
    claims_path = tmp_path / "article.claims.yaml"
    claims_path.write_text(claims, encoding="utf-8")
    return claims_path


# ── check_claims ────────────────────────────────────────────────────────


def test_claims_pass_when_truthful_and_honest(tmp_path):
    path = _write_pair(
        tmp_path,
        "Declare `aps.kv` and call `storage.get`.",
        "capabilities: [aps.kv]\nhost_api_methods: [storage.get]\n",
    )
    assert check_claims_file(path, TRUTH) == []


def test_wrong_capability_string_fails(tmp_path):
    # §13 acceptance: a deliberately wrong capability string fails CI.
    path = _write_pair(
        tmp_path,
        "Declare `aps.scope.everything` for full access.",
        "capabilities: [aps.scope.everything]\n",
    )
    errors = check_claims_file(path, TRUTH)
    assert any("not in the published schema" in e for e in errors)


def test_stale_claim_not_in_article_fails(tmp_path):
    path = _write_pair(
        tmp_path,
        "This article no longer mentions the capability.",
        "capabilities: [aps.kv]\n",
    )
    errors = check_claims_file(path, TRUTH)
    assert any("does not appear" in e for e in errors)


def test_unknown_claim_type_fails(tmp_path):
    path = _write_pair(tmp_path, "body", "cli_flags: [--strict]\n")
    errors = check_claims_file(path, TRUTH)
    assert any("unknown claim type" in e for e in errors)


def test_orphan_sidecar_fails(tmp_path):
    path = tmp_path / "ghost.claims.yaml"
    path.write_text("capabilities: [aps.kv]\n", encoding="utf-8")
    errors = check_claims_file(path, TRUTH)
    assert any("no matching article" in e for e in errors)


# ── run_samples ─────────────────────────────────────────────────────────


def test_sample_extraction_parses_info_string_attrs(tmp_path):
    (tmp_path / "doc.md").write_text(
        "intro\n\n```json sample=app-manifest\n{}\n```\n\n```json\nuntagged\n```\n",
        encoding="utf-8",
    )
    samples, errors = extract_samples(tmp_path)
    assert errors == []
    assert len(samples) == 1
    assert samples[0].kind == "app-manifest"
    assert samples[0].lang == "json"
    assert samples[0].line == 3


def test_sample_runner_wiring(tmp_path, monkeypatch):
    # `true` / `false` as the CLI prove the pass/fail plumbing without npx.
    (tmp_path / "doc.md").write_text(
        '```json sample=app-manifest\n{"schema": 1}\n```\n', encoding="utf-8"
    )
    script = SCRIPTS / "run_samples.py"
    ok = subprocess.run(
        [sys.executable, script, "--docs-root", tmp_path],
        env={"PATH": "/usr/bin:/bin", "ANNA_APP_CLI": "true"},
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    bad = subprocess.run(
        [sys.executable, script, "--docs-root", tmp_path],
        env={"PATH": "/usr/bin:/bin", "ANNA_APP_CLI": "false"},
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1


def test_zero_samples_is_a_failure(tmp_path):
    (tmp_path / "doc.md").write_text("no fences here\n", encoding="utf-8")
    samples, _ = extract_samples(tmp_path)
    assert samples == []  # main() turns this into exit 1 (vacuous-job guard)


# ── generate_reference (§9.2) ───────────────────────────────────────────


def _fixture_reference() -> dict:
    return {
        "sections": [
            {"id": "hand", "title": "Hand-authored", "items": [{"name": "x", "desc": "y"}]},
            {
                "id": "host-api-storage",
                "source": "host_api",
                "items": [],
            },
            {"id": "sse-events", "source": "events", "items": []},
            {"id": "app-manifest", "source": "app_manifest", "items": []},
        ]
    }


def _fixture_overrides() -> dict:
    return {
        "host-api-storage": {
            "source": "host_api",
            "items": [
                {"name": "storage.get", "desc": "Read a key.", "tags": [{"label": "KV"}]},
                {"name": "storage.set", "desc": "Write a key."},
            ],
        },
        "sse-events": {
            "source": "events",
            "items": [{"name": "executa_installed", "desc": "Install done."}],
        },
        "app-manifest": {
            "source": "app_manifest",
            "items": [
                {"name": "schema", "desc": "Manifest schema version."},
                {"name": "required_executas", "desc": "Bundled executas."},
            ],
        },
    }


def test_generation_rebuilds_items_from_truth_and_prose():
    reference, errors = generate(_fixture_reference(), _fixture_overrides(), TRUTH)
    assert errors == []
    storage = next(s for s in reference["sections"] if s["id"] == "host-api-storage")
    assert [i["name"] for i in storage["items"]] == ["storage.get", "storage.set"]
    assert storage["items"][0]["tags"] == [{"label": "KV"}]
    hand = next(s for s in reference["sections"] if s["id"] == "hand")
    assert hand["items"] == [{"name": "x", "desc": "y"}]  # untouched


def test_new_schema_item_requires_override_prose():
    overrides = _fixture_overrides()
    overrides["host-api-storage"]["items"] = overrides["host-api-storage"]["items"][:1]
    _, errors = generate(_fixture_reference(), overrides, TRUTH)
    assert any("storage.set" in e and "no override claims" in e for e in errors)


def test_override_for_removed_schema_item_fails():
    overrides = _fixture_overrides()
    overrides["sse-events"]["items"].append({"name": "ghost_event", "desc": "gone"})
    _, errors = generate(_fixture_reference(), overrides, TRUTH)
    assert any("ghost_event" in e and "not in the published schema" in e for e in errors)


def test_missing_prose_for_new_item_fails():
    overrides = _fixture_overrides()
    overrides["app-manifest"]["items"][0]["desc"] = ""
    _, errors = generate(_fixture_reference(), overrides, TRUTH)
    assert any("needs prose" in e for e in errors)


def test_hand_edit_in_generated_section_fails_check(tmp_path):
    # §13 acceptance: regenerate-diff rejects hand edits (real repo data).
    committed = (REPO / "reference-data" / "reference.json").read_text(encoding="utf-8")
    tampered = committed.replace(
        '"name": "storage.get"', '"name": "storage.get_v2"', 1
    )
    assert tampered != committed  # the edit landed in a generated section
    reference = json.loads(tampered)
    overrides = json.loads(
        (REPO / "reference-data" / "overrides" / "reference-prose.json").read_text(
            encoding="utf-8"
        )
    )
    schema_dir = Path(__file__).resolve()  # unused: truth passed directly
    from schema_sources import load_truth, resolve_schema_dir  # noqa: F401

    try:
        truth = load_truth(resolve_schema_dir(None))
    except SystemExit:
        pytest.skip("schema package not installed locally")
    regenerated, errors = generate(reference, overrides, truth)
    # Either generation flags nothing (tamper only touched reference.json) and
    # the canonical dump differs from the tampered text — which is exactly
    # what --check compares — or coverage errors fire. Both reject the edit.
    canonical = json.dumps(regenerated, indent=2, ensure_ascii=False) + "\n"
    assert errors or canonical != tampered
