---
title: "Recording and Replay"
description: "Record `anna-app dev` sessions to JSONL and verify, summarize, or replay them against the current manifest."
section: apps
slug: recording-replay
order: 19
updated: 2026-04-29
estimated_minutes: 4
category: "Local Development & Testing"
---

# Recording and Replaying Sessions

Every `anna-app dev` session records its RPC envelopes to a JSONL file.
You can verify recordings, summarise them, or dry-run a replay against a
manifest — useful for regression suites and bug reports.

## Where recordings live

By default the harness writes one JSONL per session under your project's
`./fixtures/` directory (or wherever `manifest.dev.fixtures` points the
harness to look). Each line is a single envelope:

```jsonl
{"t": 0,    "dir": "out", "ns": "window",  "method": "hello",  "args": {}, "result": {...}}
{"t": 12,   "dir": "out", "ns": "tools",   "method": "invoke", "args": {"tool_id": "..."}, "result": {...}}
{"t": 1500, "dir": "in",  "name": "auth.refresh", "payload": {...}}
```

`dir`:

- `out` — bundle → host (`call`)
- `in`  — host → bundle (server-pushed `event`)

## CLI

### `anna-app fixture verify <file>`

Schema + invariant checks. Confirms each line parses, every `out` call
maps to a known `(ns, method)`, and the timeline is monotonic.

```bash
anna-app fixture verify fixtures/happy-path.jsonl
# ✓ 84 envelopes, 0 issues
```

Pass `--json` for machine-readable output (CI integrations).

### `anna-app fixture summarize <file>`

Human-readable digest: per-namespace call counts, error breakdown, top
tools by invocation count, total duration.

```bash
anna-app fixture summarize fixtures/happy-path.jsonl
# Session: fixtures/happy-path.jsonl
# Duration: 4.2s   Calls: 84   Errors: 0
# By namespace:  window 12   storage 31   tools 18   chat 23
# Top tools: tool-dev-focus-flow.start (8), tool-dev-focus-flow.tick (10)
```

`--json` available.

### `anna-app fixture replay <file>`

Dry-run replay of a recording against the current manifest. Useful when
you've changed `host_api` ACL or renamed a tool — the replay surfaces
every call the new manifest would now reject.

```bash
anna-app fixture replay fixtures/happy-path.jsonl --manifest manifest.json
```

The MVP replay does **not** boot the bundle; it just walks the timeline
and reports each call's projected outcome under the supplied manifest.

## Wiring into vitest

You can hand a recording to `mountBundle` to exercise event delivery
deterministically:

```ts
import { mountBundle } from "@anna-ai/cli/test";
import { readFileSync } from "node:fs";
import manifest from "../manifest.json" assert { type: "json" };

const lines = readFileSync("fixtures/happy-path.jsonl", "utf8")
  .trim()
  .split("\n")
  .map((l) => JSON.parse(l));

const harness = await mountBundle({ manifest });

for (const env of lines) {
  if (env.dir === "in") {
    harness.events.emit(env.name, env.payload);
  }
  // `out` envelopes will be replayed by your test's normal call path
}
```

## CI usage

Drop one or two short, hand-curated recordings into `fixtures/` and
gate every PR with:

```yaml
- run: pnpm anna-app fixture verify fixtures/*.jsonl
- run: pnpm anna-app fixture replay fixtures/happy-path.jsonl
```

The replay step catches manifest regressions; the verify step catches
recording corruption.

## Related

- [Local Development](/developers/apps/local-dev)
- [Testing the bundle](/developers/apps/testing-bundle)
- Design doc:
  [`docs/design/anna-app-local-dev-and-test.md`](/developers/apps/app-ui-overview)
  §6 (recording format) and §10 (CI matrix)
