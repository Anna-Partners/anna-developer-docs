---
title: "Binary Distribution"
description: "Ship one binary per platform — single-file or full multi-file bundle."
section: tools
slug: executa-binary
order: 12
updated: 2026-07-07
estimated_minutes: 10
---

For end users, "install Python first" is a deal-breaker. Ship **one binary per platform** and the install becomes a single download. The Anna Agent has built-in `binary` distribution support that fetches the right asset for the current host — for both *single-file* binaries and *multi-file* bundles (binary + bundled `.so`/`.dylib` + data dirs).

## Single-file vs multi-file at a glance

| Scenario | Use | Archive shape |
|---|---|---|
| One self-contained binary (Go, Rust, PyInstaller `--onefile`, Node `pkg`) | Single-file | Raw binary, **or** `.tar.gz` / `.zip` containing the executable + `manifest.json` (recommended) |
| Binary + bundled libs / data / sub-tools | Multi-file | `.tar.gz` / `.zip` with `bin/` + `lib/` + `data/` + `manifest.json` declaring the entrypoint |

Multi-file is required whenever your binary needs to find its own bundled friends at runtime — PyInstaller `--onedir`, Electron-style apps, anything with native side-by-side `.so` / `.dylib` / DLLs.

> [!TIP]
> Even for single-file binaries we recommend the `.tar.gz` + `manifest.json` form rather than uploading a raw binary. The manifest pins your `name`, declares `permissions`, and travels with the binary so future re-publishes can't drift.

## Build matrix

| Language | Tool | Default output |
|---|---|---|
| Python | [PyInstaller](https://pyinstaller.org) `--onefile` or `--onedir` | Single executable, or directory of executable + libs |
| Node.js | [`@yao-pkg/pkg`](https://github.com/yao-pkg/pkg) (or Node 20+ SEA) | Single executable per platform |
| Go | `go build` | Native binary, no extras |
| Rust | `cargo build --release` | Native binary, no extras |

## Platform keys

The Agent auto-detects the host as `"{os}-{arch}"` (lowercase, normalized). Use these keys for your asset names and `binary_urls` map:

| Host | Platform key |
|---|---|
| macOS Apple Silicon | `darwin-arm64` |
| macOS Intel | `darwin-x86_64` |
| Linux x86_64 | `linux-x86_64` |
| Linux ARM64 | `linux-aarch64` |
| Linux ARMv7 | `linux-armv7l` |
| Windows x86_64 | `windows-x86_64` |
| Windows ARM64 | `windows-arm64` |

The Agent applies aliases so `amd64`/`x64` are folded into `x86_64` automatically. Resolution falls back from exact match → OS prefix (`darwin-*`) → wildcard (`*` / `any` / `universal`) → single-entry maps.

## `binary_urls` — value can be a string OR an asset dict

The simplest form is one URL per platform:

```json
{
  "binary_urls": {
    "darwin-arm64":  "https://example.com/v1/my-tool-darwin-arm64.tar.gz",
    "linux-x86_64":  "https://example.com/v1/my-tool-linux-x86_64.tar.gz",
    "windows-x86_64":"https://example.com/v1/my-tool-windows-x86_64.zip"
  }
}
```

For multi-file bundles or when you want sha256 verification, swap any value to an **asset dict**:

```json
{
  "binary_urls": {
    "darwin-arm64": {
      "url":        "https://example.com/v1/my-tool-darwin-arm64.tar.gz",
      "sha256":     "9b1f...c2",
      "size":       18_345_678,
      "entrypoint": "bin/my-tool",
      "format":     "tar.gz"
    },
    "linux-x86_64": "https://example.com/v1/my-tool-linux-x86_64.tar.gz"
  }
}
```

| Field | Required | What it does |
|---|---|---|
| `url` | yes | Where the Agent downloads from |
| `sha256` | optional but recommended | Agent rejects the install on mismatch |
| `size` | optional | Belt-and-braces size check |
| `entrypoint` | optional | Path inside the archive that becomes the launcher (multi-file only) |
| `format` | optional | `tar.gz` / `tgz` / `zip` / `raw`. Auto-inferred from URL suffix when omitted |

The Nexus UI exposes these fields under each platform row's **▾ Advanced** toggle.

## Getting the bytes to your users — two tracks

| Track | You declare | Where the bytes come from | Best for |
|---|---|---|---|
| **Direct upload (recommended)** | `distribution.binary_artifacts` — LOCAL archive paths | `anna-app executa upload-binaries` (or `apps cut`, automatically) pushes them straight to Anna storage | Private repos, CI without public releases, local build machines |
| Pull-mirror | `distribution.binary_urls` — public GET-able URLs | The platform downloads from your URL at `apps cut` / release and mirrors it | Existing public GitHub Releases |

Declare **exactly one** of the two for `type: "binary"`. Either way the end state is identical: the bytes live content-addressed in Anna storage, `binary_sha256` is pinned, and the Agent installs from the platform CDN with hash verification.

### `binary_artifacts` — direct upload (push model)

```json
{
  "distribution": {
    "type": "binary",
    "binary_artifacts": {
      "darwin-arm64":  { "path": "dist/my-tool-{version}-darwin-arm64.tar.gz",  "entrypoint": "my-tool" },
      "linux-x86_64":  { "path": "dist/my-tool-{version}-linux-x86_64.tar.gz",  "entrypoint": "my-tool" },
      "windows-x86_64": { "path": "dist/my-tool-{version}-windows-x86_64.zip", "entrypoint": "my-tool", "format": "zip" }
    }
  }
}
```

| Field | Required | What it does |
|---|---|---|
| `path` | yes | Archive path relative to the executa project root. Placeholders `{version}` / `{platform}` / `{tool_id}` expand at upload time |
| `entrypoint` | recommended | Launcher inside the archive (same semantics as the asset-dict field) |
| `format` | optional | `tar.gz` / `tgz` / `zip`; inferred from the path suffix when omitted. Bare executables are rejected — always archive |

Then:

```bash
anna-app executa upload-binaries            # standalone: hash → upload → pin
anna-app executa upload-binaries --dry-run  # plan only (what would upload / what's cached)
```

Or just publish — the upload is built into the lifecycle:

- `anna-app executa publish` uploads the artifacts **before** freezing the version, so the snapshot pins CDN URLs + sha256.
- `anna-app apps cut` auto-uploads every bundled executa that declares `binary_artifacts` before the freeze. `apps push` never uploads (push stays light).

Uploads are **content-addressed**: re-running with unchanged artifacts transfers zero bytes (`exists (skip)`), and interrupted uploads resume from the parts already received. The server independently re-hashes every uploaded archive and rejects a sha256 mismatch, and your source repo never needs a public URL — private repos and laptops publish the same way. Authentication uses your regular `anna-app login` PAT (scope `executas:publish`), exchanged internally for a 15-minute single-tool upload token.

### Zero-secret CI: OIDC Trusted Publishing

Publishing binaries from GitHub Actions does not need a PAT at all. Register the workflow once (this mirrors PyPI's Trusted Publishers):

```bash
anna-app executa trusted-publisher add \
  --repository your-org/your-repo \
  --workflow publish.yml \
  --environment production   # optional GitHub Environment gate
```

Then in the workflow the runner's own OIDC id-token is exchanged for the upload token:

```yaml
permissions:
  id-token: write   # lets the job mint a GitHub OIDC id-token
  contents: read

steps:
  - uses: actions/checkout@v4
  # ...build dist/ artifacts matching binary_artifacts paths...
  - run: |
      pnpm exec anna-app executa upload-binaries \
        --oidc --host "$ANNA_APP_HOST" --tool-id "$TOOL_ID"
```

No `ANNA_APP_PAT` secret is involved: the platform verifies the id-token against GitHub's public keys (issuer + pinned audience + expiry) and matches the token's `repository` / `workflow_ref` / `environment` claims against your registration. Any branch or tag of the registered workflow file may publish (PyPI semantics); pin an `--environment` to also require the run to pass that GitHub Environment's protection rules. Manage registrations with `trusted-publisher list` / `trusted-publisher remove <id>` — or in the hub: the tool edit dialog's Binary section shows an **OIDC Trusted Publishers** panel (owners only) where you can add/remove registrations and see when each one was last used by CI.

> [!NOTE]
> OIDC covers the **binary upload** only. Lifecycle verbs (`apps push` / `cut` / `release`) still authenticate with a PAT.

### `binary_urls` — pull-mirror (public sources)

Keep using `binary_urls` when your binaries are already on a public GitHub Release (or any public HTTPS URL): the platform pulls and mirrors them at `apps cut` / release. **Private source URLs are deprecated** and will be rejected in a future release — the platform cannot reliably fetch them; switch those projects to `binary_artifacts`.

## Multi-file binary layout

When the Agent installs a multi-file archive it lays it out like this:

```
~/.anna/executa/
  bin/my-tool                          → tools/{tool_id}/current/bin/my-tool
  tools/{tool_id}/
    v1.0.0/
      bin/my-tool                       ← entrypoint
      lib/                              ← .so / .dylib live here
      data/                              ← bundled data
      manifest.json
      INSTALL.json                      ← install metadata (auto-written)
    current  → v1.0.0                  ← atomic blue-green upgrade pointer
```

`bin/my-tool` in the user's PATH-style shim is a stable entry point that survives upgrades — `current` is rewritten atomically, so an in-flight invocation keeps reading the old version. Older versions are GC'd according to `EXECUTA_KEEP_VERSIONS` (default 2).

## Manifest `runtime.binary`

> [!IMPORTANT]
> **Always ship a `manifest.json` at the archive root** — even for single-file binaries. It pins the install identity and prevents three classes of silent breakage:
>
> 1. **`name` collisions in `bin/`.** The Agent creates `~/.anna/executa/bin/{name}` as the launcher shim, where `{name}` is the `executable_name` (or, when omitted, a slug derived from the package / URL — e.g. `https://.../my-tool-darwin-arm64.tar.gz` becomes `my`, which collides with every other tool whose URL stem starts the same way). Pass an explicit `executable_name` / `tool_id` to avoid the URL-derived fallback.
> 2. **Wrong entrypoint chosen.** Without an explicit entrypoint the Agent picks the only-or-first executable it finds in the archive, which is unpredictable for PyInstaller `--onedir`, Electron-style apps, and anything shipping helper binaries.
> 3. **Missing executable bit.** ZIP archives don't carry Unix permissions; without `permissions` the Agent only chmods the entrypoint to `0o755`, leaving auxiliary scripts (post-install hooks, sub-CLIs) at `0o644` and Permission-denied at runtime.

> [!IMPORTANT]
> **Identity is the server-minted `tool_id`.** The Agent UI joins user-installed tools to running plugins via the `tool_id` the platform passes at install time — it no longer reads a self-reported manifest `name` (neither the one your binary returns from `describe` nor the `name` in this `manifest.json`). Mismatches between those self-reported names and the `tool_id` no longer matter. See [Publishing → Stabilise the manifest](/developers/tools/executa-publish#1-stabilise-the-manifest).

Drop a `manifest.json` at the archive root:

```json
{
  "name": "tool-acme-my-tool-abcd1234",
  "version": "1.0.0",
  "runtime": {
    "binary": {
      "entrypoint": {
        "default":         "bin/my-tool",
        "windows-x86_64":  "bin/my-tool.exe",
        "windows-arm64":   "bin/my-tool.exe"
      },
      "lib_dirs":  ["lib"],
      "data_dirs": ["data"],
      "permissions": {
        "bin/my-tool":         "0o755",
        "bin/post-install.sh": "0o755"
      }
    }
  }
}
```

| Field | What it does |
|---|---|
| `name` | Human-facing label; conventionally the `tool_id` you minted on `/executa`. **Not** an identity check — the Agent joins installs to running plugins by the server-minted `tool_id` (see the note above), so a mismatch with the `name` your binary returns from `describe` is harmless. Still used as the `~/.anna/executa/bin/{name}` shim stem unless you pass `executable_name`. |
| `version` | Optional but recommended; written into `INSTALL.json` and used as the version-dir name when caller omits it |
| `runtime.binary.entrypoint` | Required for multi-file. String, or a `{ "default": "…", "darwin-arm64": "…", "windows-x86_64": "…" }` per-platform map (lookup order: full key → OS prefix → `default`) |
| `runtime.binary.lib_dirs` | Documentation only; the Agent already prepends `lib/` and `lib64/` automatically |
| `runtime.binary.data_dirs` | Documentation only; the Agent already exposes `EXECUTA_DATA` for the `data/` dir |
| `runtime.binary.permissions` | Map of relative path → octal mode. The entrypoint is `0o755` by default |

### Resolution fallback (when `manifest.json` is absent)

If you skip `manifest.json` (not recommended), the Agent walks five fallback levels in order:

1. `runtime.binary.entrypoint` from the archive `manifest.json` — *skipped, no manifest*
2. `entrypoint` from the asset dict in `binary_urls`
3. Standard locations in this order: `bin/{name}` → `bin/{name}.exe` → `{name}` → `{name}.exe` (where `{name}` is derived from the package or URL)
4. The **only** executable file in the archive
5. The **first** executable file (alphabetical), with a `WARN` log

Levels 4–5 are deliberately fuzzy because they're a last-resort. If your archive has more than one executable (very common for `--onedir`), level 5 is almost certainly going to pick the wrong one. **Provide a manifest.**

## Runtime environment your binary will see

Before launching the entrypoint the Agent injects:

| Variable | Value |
|---|---|
| `EXECUTA_HOME` | absolute path to `tools/{tool_id}/current/` |
| `EXECUTA_DATA` | `${EXECUTA_HOME}/data` (when it exists) |
| `LD_LIBRARY_PATH` | prepended `${EXECUTA_HOME}/lib` and `lib64` (Linux) |
| `DYLD_LIBRARY_PATH` | prepended `${EXECUTA_HOME}/lib` and `lib64` (macOS) |
| `PATH` | prepended `${EXECUTA_HOME}/share/bin` (when it exists; on Windows `lib/` is added too) |
| working directory | `EXECUTA_HOME` |

This means your binary can `dlopen("libfoo.so", ...)`, your Python launcher can `Path(os.environ["EXECUTA_DATA"]) / "config.toml"`, etc.

## Language guides

### Python — single file

```bash
pip install pyinstaller
pyinstaller --onefile --name my-tool plugin.py
# → dist/my-tool   (or my-tool.exe on Windows)
```

Smoke-test:

```bash
echo '{"jsonrpc":"2.0","method":"describe","id":1}' | ./dist/my-tool
```

> [!WARNING]
> PyInstaller bundles imports it can detect statically. If you use dynamic imports (`importlib`), declare them with `--hidden-import` or PyInstaller will silently skip them.

### Python — with native dependencies

When your plugin imports something with C extensions (`numpy`, `playwright`, `cryptography` with hardware backends, etc.), PyInstaller `--onefile` may fail to bundle them or bloat to hundreds of MBs. Use `--onedir` and ship as a multi-file archive — see the [multi-file Python example](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/multifile-binary/python-pyinstaller-onedir).

### Node.js

```bash
npm install -g @yao-pkg/pkg
pkg plugin.js \
  --targets node20-macos-arm64,node20-macos-x64,node20-linux-x64,node20-win-x64 \
  --out-path dist
```

Native addons (`better-sqlite3`, `sharp`…) need extra prebuild config or a multi-file archive — see the `pkg` docs.

### Go

```bash
GOOS=darwin  GOARCH=arm64 go build -ldflags "-s -w" -o dist/my-tool-darwin-arm64  .
GOOS=darwin  GOARCH=amd64 go build -ldflags "-s -w" -o dist/my-tool-darwin-x86_64 .
GOOS=linux   GOARCH=amd64 go build -ldflags "-s -w" -o dist/my-tool-linux-x86_64  .
GOOS=linux   GOARCH=arm64 go build -ldflags "-s -w" -o dist/my-tool-linux-aarch64 .
GOOS=windows GOARCH=amd64 go build -ldflags "-s -w" -o dist/my-tool-windows-x86_64.exe .
```

`-s -w` strips the symbol table and DWARF debug info; expect ~30 % smaller binaries.

## CI: build-release.yml

The examples repo ships a [`build-release.yml`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/.github/workflows/build-release.yml) GitHub Actions workflow that builds all targets in a matrix and attaches them to the release. Copy it as a starting point and update the asset names to match the platform keys above.

## Code-signing (recommended)

| Platform | Recommendation |
|---|---|
| macOS | Apple Developer ID + `codesign` + `notarytool` for notarisation |
| Windows | Authenticode signing certificate (Sectigo, DigiCert, Azure Trusted Signing) |
| Linux | GPG-sign release archives; users verify with the published public key |

Unsigned binaries still run but trigger Gatekeeper / SmartScreen warnings on first launch. The Agent automatically clears `com.apple.quarantine` on macOS after extraction, so notarisation is the right long-term fix.

## Compatibility & rollback

- The new layout is on by default. Set the env var `EXECUTA_INSTALL_V2=0` on the Agent to fall back to the legacy "single executable in `bin/`" install path — the same archive will be re-extracted into the old shape.
- Existing legacy installs keep working: when a v2 install needs to write `bin/{name}` and finds a non-symlink there, it backs the old binary up to `~/.anna/executa/legacy-backup/` first.
- Keep the same `tool_id` across releases so `tools/{tool_id}/current` updates atomically; changing `tool_id` triggers a fresh install dir.

## Local archive distribution (no URLs, no upload)

`distribution_type: local` runs the **same v2 install pipeline** described above — extract → `tools/{tool_id}/v{version}/` → atomic `current` symlink → `bin/{name}` shim — but reads the archive from a **path on the Agent machine** instead of downloading from a URL. This is the recommended way to:

- Iterate locally on a multi-file binary (`build.sh` → `dist/plugin.tar.gz` → install) without first pushing to GitHub Releases.
- Distribute internally via NFS / shared filesystem when you can't (or won't) host an HTTPS URL.
- Install in air-gapped environments.

Form fields (Create Tool modal):

| Field | Local value |
|---|---|
| Distribution Type | `local` |
| Local Archive Path | Absolute path on the Agent host, e.g. `/Users/me/build/dist/my-tool.tar.gz` |
| Executable Name | Optional; defaults to the archive base name |
| Version | Optional; defaults to `dev` |

Same archive layout & entrypoint resolution rules as binary (see [Multi-file binary layout](#multi-file-binary-layout) and [Manifest `runtime.binary`](#manifest-runtimebinary)). All security checks (zip-slip, 5GB extract limit, `..` traversal) apply identically.

> [!NOTE]
> Sha-256 / size verification is **skipped** for local installs (the archive is on your own machine). If you need integrity checks for shared-filesystem distribution, host the file over HTTPS and use `binary` instead.

## Reference

- [Multi-file binary example (Python --onedir)](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/multifile-binary/python-pyinstaller-onedir)
- [`docs/binary-distribution.md`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/docs/binary-distribution.md) in the examples repo has per-language `build_binary.sh` scripts that emit the platform-key asset layout.

