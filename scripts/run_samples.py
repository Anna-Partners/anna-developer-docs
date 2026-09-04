#!/usr/bin/env python3
"""samples-run: execute tagged doc samples against the pinned CLI (§5.3.2).

Code fences opt in via an info-string attribute:

    ```json sample=app-manifest
    { "schema": 1, "required_executas": [ ... ] }
    ```

Kinds:

* ``app-manifest`` — the block must be valid JSON and pass
  ``anna-app validate --manifest`` under the **published** CLI pinned in
  ``.cli-version`` (bumped by Renovate — a CLI bump that breaks a sample is
  exactly the drift signal we want, caught here instead of by a developer).

The design also names an ``executa dev --smoke`` kind for plugin samples; the
published CLI has no smoke mode yet, so the registry ships ``app-manifest``
only — add the kind here when the CLI grows it.

Environment:
    ANNA_APP_CLI — override the CLI command (space-separated), e.g. a local
    checkout during development. Default: ``npx --yes @anna-ai/cli@<pin>``.

Usage:
    python scripts/run_samples.py [--docs-root docs] [--list]
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
CLI_PIN = (REPO / ".cli-version").read_text(encoding="utf-8").strip()

# Whole-fence matcher: info string (may carry attributes) + body.
FENCE_RE = re.compile(r"^```([^\n`]+)\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)


@dataclass
class Sample:
    doc: Path
    line: int
    lang: str
    kind: str
    body: str

    @property
    def label(self) -> str:
        try:
            doc = self.doc.relative_to(REPO)
        except ValueError:  # fixtures outside the repo (tests)
            doc = self.doc.name
        return f"{doc}:{self.line} [{self.kind}]"


def extract_samples(docs_root: Path) -> tuple[list[Sample], list[str]]:
    samples: list[Sample] = []
    errors: list[str] = []
    for md in sorted(docs_root.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        for match in FENCE_RE.finditer(text):
            info, body = match.group(1).strip(), match.group(2)
            tokens = info.split()
            attrs = dict(t.split("=", 1) for t in tokens[1:] if "=" in t)
            if "sample" not in attrs:
                continue
            line = text[: match.start()].count("\n") + 1
            samples.append(
                Sample(doc=md, line=line, lang=tokens[0], kind=attrs["sample"], body=body)
            )
    return samples, errors


def _cli_command() -> list[str]:
    import os

    override = os.environ.get("ANNA_APP_CLI")
    if override:
        return shlex.split(override)
    return ["npx", "--yes", f"@anna-ai/cli@{CLI_PIN}"]


def run_app_manifest(sample: Sample) -> str | None:
    try:
        json.loads(sample.body)
    except json.JSONDecodeError as exc:
        return f"invalid JSON: {exc}"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write(sample.body)
        manifest_path = tmp.name
    cmd = [*_cli_command(), "validate", "--manifest", manifest_path]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
        return "anna-app validate failed:\n      " + "\n      ".join(tail)
    return None


RUNNERS = {
    "app-manifest": run_app_manifest,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path, default=DOCS)
    parser.add_argument("--list", action="store_true", help="list samples, don't run")
    args = parser.parse_args()

    samples, errors = extract_samples(args.docs_root)

    for sample in samples:
        if sample.kind not in RUNNERS:
            errors.append(
                f"{sample.label}: unknown sample kind (known: {', '.join(sorted(RUNNERS))})"
            )

    if not samples and not errors:
        # A zero count would make the job vacuous forever (e.g. a regex rot
        # silently un-tagging everything) — treat as failure.
        errors.append(f"no `sample=` tagged fences found under {args.docs_root}")

    if args.list:
        for sample in samples:
            print(sample.label)
        return 1 if errors else 0

    for sample in samples:
        runner = RUNNERS.get(sample.kind)
        if runner is None:
            continue
        failure = runner(sample)
        if failure:
            errors.append(f"{sample.label}: {failure}")
        else:
            print(f"  ✓ {sample.label}")

    if errors:
        print("samples-run failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {len(samples)} samples executed against @anna-ai/cli@{CLI_PIN}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
