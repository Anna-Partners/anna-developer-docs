---
title: "Testing the Bundle"
description: "Drive the bundle from vitest with `mountBundle` — same access decisions and call recording as the dev harness."
section: apps
slug: testing-bundle
order: 17
updated: 2026-11-02
estimated_minutes: 4
category: "Local Development & Testing"
---

# Testing the App Bundle

Use `@anna-ai/cli/test` (the `mountBundle` helper) to drive your bundle
modules directly from `vitest` — no iframe, no harness server, no
`uvx`. The same access decisions, mock-runtime, and call-recording layer that
backs `anna-app dev` runs in-process.

## Install

The helper ships inside `@anna-ai/cli` (re-exported as `@anna-ai/cli/test`).
Add it as a dev dep:

```bash
pnpm add -D @anna-ai/cli vitest
```

A standalone `@anna-ai/app-test` package will be carved out in a later
phase; until then `import { mountBundle } from "@anna-ai/cli/test"` is the
canonical entry.

## Minimal example

```ts
// tests/bundle/timer.spec.ts
import { describe, it, expect } from "vitest";
import { mountBundle } from "@anna-ai/cli/test";
import manifest from "../../manifest.json" assert { type: "json" };
import { startTimer } from "../../bundle/timer.js";

describe("timer", () => {
  it("invokes the executa tool", async () => {
    const harness = await mountBundle({
      manifest,
      mocks: {
        "tools.invoke": ({ tool_id, method, args }) => ({
          success: true,
          data: { state: "running", remaining_seconds: 1500 },
        }),
      },
    });

    await startTimer(harness.runtime, { duration_minutes: 25 });

    expect(harness.calls.byNs("tools.invoke")).toHaveLength(1);
    const call = harness.calls.lastOf("tools.invoke")!;
    expect(call.args).toMatchObject({ method: "start" });
  });
});
```

## What `mountBundle` gives you

| Property | Use |
| --- | --- |
| `harness.runtime` | Drop-in for the production SDK (`AnnaAppRuntime`). Same `tools.invoke` / `storage.set` / `chat.write_message` / event API. |
| `harness.calls` | `CallLog` with `all()`, `byNs(prefix)`, `last()`, `lastOf(prefix)`, `clear()`. |
| `harness.events` | `EventBus` with `emit(name, payload)` (simulate server events) and `on(name, fn)`. |
| `harness.mock(key, handler)` | Replace / add a mock at any time. |
| `harness.wait(ms)` | Microtask helper. |

## Denied calls

The harness makes the same decisions as the production dispatcher: every
Host API method is available, and only the three
[capability declarations](/developers/apps/app-manifest#capability-declarations)
can deny a call — `tools.invoke` on a `tool_id` outside
`required_executas` / `optional_executas`, an undeclared `credentials`
provider, or an undeclared cross-app storage scope. Those resolve to
`outcome: "denied"` and the promise rejects with `HostApiError`:

```ts
await expect(
  harness.runtime.tools.invoke({ tool_id: "not-in-manifest", args: {} }),
).rejects.toThrow(HostApiError);
expect(harness.calls.last()?.outcome).toBe("denied");
```

## Pushing simulated events

```ts
harness.events.emit("entry_payload", { mode: "deep_focus" });
harness.events.emit("auth.refresh", { token: "xyz" });
```

Anything your bundle subscribes to via `runtime.on(name, ...)` will fire.

## Default mock behaviour

If you don't supply a mock for a method:

- `window.*` returns `{ ok: true }` (or the documented shape) and
  records the call.
- `storage.*` operates on an in-memory `Map` so set/get/delete behaves
  exactly like production (sans size limit).
- everything else returns a `denied` outcome and rejects.

## What this does **not** test

- The static manifest schema — use `anna-app validate`.
- The plugin side (`executas/`) — use
  [`anna-executa-test`](/developers/apps/testing-plugin).
- The full iframe + postMessage transport — use `anna-app dev` and the
  recordings it produces.

## Related

- [Local Development](/developers/apps/local-dev)
- [Recording & replaying](/developers/apps/recording-replay)
- [Host API reference](/developers/apps/app-ui-host-api)
