#!/usr/bin/env python3
"""Publish a built bundle layout to R2 (design §5.2).

Upload order is the atomicity mechanism:
  1. immutable content/reference objects (commit-addressed keys, long cache)
  2. immutable bundle manifest bundles/<commit>.json
  3. the tiny pointer manifest.json (Cache-Control: no-store) — LAST

Nexus converges by polling the pointer (uniform delayed convergence —
no webhook; see design §7.3).

Environment:
  R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY   (required)
  R2_BUCKET                       (default: anna-docs)

Usage:
    python scripts/build_bundle.py --out build/
    python scripts/publish_bundle.py --bundle-dir build/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig

PREFIX = "developers-hub"
POINTER_KEY = f"{PREFIX}/manifest.json"

IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
POINTER_CACHE = "no-store"

_CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def _client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=BotoConfig(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "adaptive"},
            connect_timeout=15,
            read_timeout=60,
        ),
    )


def _upload(client, bucket: str, key: str, path: Path, cache_control: str) -> None:
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=path.read_bytes(),
        ContentType=_CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
        CacheControl=cache_control,
    )
    print(f"  uploaded {key} ({path.stat().st_size} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True,
                        help="output directory of build_bundle.py --out")
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET", "anna-docs"))
    args = parser.parse_args()

    root = args.bundle_dir / PREFIX
    pointer_path = root / "manifest.json"
    if not pointer_path.is_file():
        print(f"no bundle layout at {root}", file=sys.stderr)
        return 1
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    bundle_key = pointer["bundle"]
    bundle_path = args.bundle_dir / bundle_key
    manifest = json.loads(bundle_path.read_text(encoding="utf-8"))
    commit = manifest["commit"]

    client = _client()

    # 1. Immutable article + reference objects.
    immutable_dirs = [root / "content" / commit, root / "reference" / commit]
    for base in immutable_dirs:
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            key = path.relative_to(args.bundle_dir).as_posix()
            _upload(client, args.bucket, key, path, IMMUTABLE_CACHE)

    # 2. Immutable bundle manifest.
    _upload(client, args.bucket, bundle_key, bundle_path, IMMUTABLE_CACHE)

    # 3. Pointer flip — last, no-store (atomic-swap discipline).
    _upload(client, args.bucket, POINTER_KEY, pointer_path, POINTER_CACHE)

    print(f"published bundle {commit[:12]} ({manifest['totals']['articles']} articles)")
    print("Nexus workers converge within one poll interval (default 300s ±20%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
