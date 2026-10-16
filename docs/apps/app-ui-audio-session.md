---
title: "App UI Audio Session: Realtime Voice"
description: "Open a full-duplex voice session from your bundle — streaming ASR, your App's agent (or no LLM), streaming TTS with barge-in, live context injection and TTS-only say() — relayed by the host so the iframe never holds a token."
section: apps
slug: app-ui-audio-session
order: 17
updated: 2026-10-14
estimated_minutes: 10
category: "App UI"
---

`anna.audio.session()` gives an App the **same realtime voice pipeline as the
main-chat voice mode**: the user talks, the host runs streaming speech
recognition, feeds each finished sentence to an LLM, and streams synthesized
speech back while the user can barge in. Two things are specific to Apps:

- **`setContext(text)`** — inject your App's *live state* (a game digest, the
  current document, sensor readings) into the next turn's prompt. It is
  replaced, not appended, and never enters the conversation history.
- **`say(text)`** — speak any text through the same streaming TTS **without** an
  LLM round-trip (alerts, countdowns, canned phrases), with priority and
  pre-emption.

The LLM behind the session is **your App's agent session** (`llm: "agent"`,
same tool surface as [`anna.agent.session`](/developers/apps/llm-and-agent)) or
nothing at all (`llm: "none"` — ASR events + `say()` only).

> **Choose the right audio surface.** `audio.speak` / `audio.transcribe`
> ([App UI Media](/developers/apps/app-ui-media)) are one-shot and synchronous;
> the session is a long-lived, streaming, billed-while-you-send connection.
>
> | Need | Use |
> |---|---|
> | Read a sentence aloud, no conversation | `audio.speak` (sync, URL or inline) |
> | Transcribe a recording the user already made | `audio.transcribe` (sync, ≤10 min) |
> | Live conversation, partial transcripts, barge-in | **`audio.session`** |
> | Low-latency spoken alerts while the user does something else | **`audio.session`** with `llm: "none"` + `say()` |
> | Push-to-talk question answered by *your* agent with *your* live context | **`audio.session`** with `llm: "agent"` + `setContext()` |

## How it reaches the host

`audio.session.*` is **not** a dispatcher RPC. The iframe posts
`audio.session.{open, send, flush, context, say, interrupt, close}` to the host
page; the **host bridge** (`anna-app-host-bridge.js` on the dashboard, the
anna-mobile shell on phones) handles them locally — it opens
`wss://{host}/api/v1/anna-apps/runtime/voice?window_uuid=…` with the user's
cookie, relays audio and control messages up, and forwards every server event
down as a single `audio.session` bridge event that the SDK routes to your
`VoiceSession` handle.

```
iframe ──postMessage──► host bridge ──WebSocket──► nexus VoiceGateway
  mic PCM16 ───────────► audio_data ─────────────► streaming ASR ─┐
  setContext ──────────► set_context                              ▼
  say ─────────────────► say                     LLM (your agent session | none)
  ◄── asr_* / llm_* / tts_audio / say_* / interrupted ◄── streaming TTS
```

Consequences you can rely on:

- The iframe never sees a token, cookie or socket — the sandbox invariants of
  [App UI Overview](/developers/apps/app-ui-overview) hold unchanged.
- One session per window (the bridge and the server both enforce it;
  `concurrency_limit` otherwise). There is no per-user cap.
- Closing the window or reloading the iframe ends the session automatically.
- Hosts without the relay (older dashboards, SDK < 0.21.0) answer
  `unknown_method` / `not_supported` — feature-detect with
  `typeof anna.audio?.session === "function"` and fall back to `audio.speak`.

## Authorization

Three gates, all checked when the session opens:

1. **Manifest** — `ui.host_api.audio` must contain `"session"`. Declaring it also
   makes the host render your iframe with `allow="microphone"` (and the bundle
   response with `Permissions-Policy: microphone=(self)`); without the
   declaration `getUserMedia` is denied before you can ask.

   ```json
   "ui": {
     "host_api": {
       "audio": ["session"],
       "agent": { "session": { "auto": true } }
     }
   }
   ```

2. **User grant** — `media_grant.audio.enabled` **and both** `speak` and
   `transcribe` sub-flags, because the session synthesizes and recognises.
   Missing any → `not_granted`.
3. **Agent submode** (only for `llm: "agent"`) — `host_api.agent.session.auto`
   (or `.fixed` with `fixed_client_id`) must be on, exactly as for
   `anna.agent.session`. Otherwise `permission_denied`. (The validator does
   not require it — declaring `session` alone is fine if you only ever open
   `llm: "none"`.)

## A complete push-to-talk loop

```js
let vs, mic, player, talking = false;

async function start() {
  // 1. Microphone first: a denied permission must not leave a session open.
  mic = anna.audio.mic({
    sampleRate: 16000,
    onChunk: (pcm16) => { if (talking && vs) vs.sendAudio(pcm16); },
  });
  await mic.start();        // permission prompt (needs a secure context)
  mic.setMuted(true);       // push-to-talk gate — emit nothing until pressed

  // 2. Open the session. Resolves when the host's ASR/TTS are ready.
  vs = await anna.audio.session({
    llm: "agent",
    language: "zh",
    system: "You are a concise in-game coach. One or two short sentences.",
    context: JSON.stringify(gameState),     // ≤ 4 KB
    maxDurationSec: 1800,                   // ≤ 3 h, clamped by the host
  });

  // 3. Player at the host's output format (24 kHz mono PCM16 today).
  player = anna.audio.player({ sampleRate: vs.audioConfig.sample_rate });

  vs.on("asr_partial", ({ text }) => live.textContent = text);
  vs.on("asr_final",   ({ text }) => transcript.add("user", text));
  vs.on("llm_partial", ({ text }) => reply.textContent += text);
  vs.on("llm_done",    ({ text }) => transcript.add("anna", text));
  vs.on("tts_audio",   ({ audio }) => player.enqueue(audio));   // base64 PCM
  vs.on("tts_done",    () => player.flush());
  vs.on("interrupted", () => player.stop());                    // barge-in / high-priority say
  vs.on("quota_warning", ({ message }) => toast(message));
  vs.on("error",       ({ code, message }) => console.warn(code, message));
  vs.on("ended",       (usage) => { cleanup(); console.log(usage); });
}

ptt.onpointerdown = () => { talking = true;  mic.setMuted(false); };
ptt.onpointerup   = () => { talking = false; mic.setMuted(true); vs.flushAudio(); };

// Live context: replace whenever your state changes (cheap — no LLM call).
setInterval(() => vs && vs.setContext(JSON.stringify(gameState)), 1000);

// TTS-only alert that pre-empts whatever is playing.
function alert(text) { return vs.say(text, { priority: "high" }); }

async function stop() {
  const usage = await vs.end();   // { duration, total_asr_seconds, total_tts_characters, reason }
  mic.stop(); player.destroy();
}
```

Three details that are easy to get wrong:

- **Call `flushAudio()` when the button is released.** Streaming ASR only
  finalizes a sentence after it hears trailing *silence*; once you stop sending
  frames the pending half-sentence would never become `asr_final`. `flushAudio()`
  finalizes it immediately (the demo measures ~0.5 s).
- **Expect `asr_paused` / `asr_resumed`.** After `vs.asrIdleTimeoutSec` (15 s)
  without audio the host parks the recogniser; your next `sendAudio` rebuilds it
  transparently (~0.3–0.6 s added to the first word). Nothing to handle — show a
  status if you like.
- **`interrupted` fires for barge-in and for a pre-empting `say`, not for your
  own `interrupt()`** — stop your player yourself after calling it.

## Configuration

| Field | Default | Notes |
|---|---|---|
| `llm` | `"agent"` | `"agent"` = your App's agent session (server-minted, 2 h token auto-refreshed; 30 min idle TTL — after a long silence the next turn transparently starts a fresh history). `"none"` = ASR + `say()` only. |
| `submode`, `fixed_client_id` | `"auto"` | Same as `anna.agent.session`. |
| `system` | — | System prompt for `llm: "agent"`, ≤ 8 KB. The live context is appended inside a `<live_context>` fence on every run. |
| `context` | — | Initial live context, ≤ 4 KB; same semantics as `setContext()`. |
| `voice`, `language`, `speed` | model default / `zh` / `1.0` | Voice must exist on the resolved TTS model (`llm.catalog({serviceType:'tts'})`); unknown voices fall back to the default and the effective one is echoed in `vs.models.voice`. Apps **cannot** choose ASR/TTS models — the user's realtime-model preferences apply. |
| `maxDurationSec` | host cap (3 h) | Clamped; effective value in `vs.maxDurationSec`. On expiry: `error{code:"session_timeout"}` then `ended` — reopen if you need more. |

`VoiceSession` exposes `sessionId`, `audioConfig`, `models`, `maxDurationSec`,
`asrIdleTimeoutSec`, `ended`, `usage`, and `on("*", (event, payload) => …)` for
a catch-all. Full field-level detail: [`audio.session` in the Reference](/developers/reference/host-api-audio).

## Events

| Event | Payload | When |
|---|---|---|
| `asr_partial` / `asr_final` | `{text}` | Live transcript; `asr_final` is one sentence and triggers the LLM (if any). |
| `llm_start` / `llm_partial` / `llm_done` | `{user_text}` / `{text}` / `{text}` | Reply streaming (`llm: "agent"` only). |
| `tts_audio` / `tts_done` | `{audio: base64 PCM16}` / `{}` | Feed `player.enqueue` / `player.flush`. |
| `interrupted` | `{source: "barge_in" \| "say"}` | Current reply + TTS were cut; `player.stop()`. |
| `say_start` / `say_done` | `{say_id, chars}` / `{say_id, status: done \| interrupted \| replaced \| error}` | Lifecycle of `say()`. |
| `context_updated` | `{chars}` | `setContext` accepted. |
| `asr_paused` / `asr_resumed` | `{idle_sec \| reason}` / `{reconnect_ms}` | Idle management (see above). |
| `quota_warning` | `{message}` | CU pool low (checked every 60 s). |
| `error` | `{code, message}` | Non-fatal unless followed by `ended` — see codes below. |
| `ended` | `{duration, total_asr_seconds, total_tts_characters, reason}` | Terminal; also resolves `end()`. |

## `say()` semantics

`vs.say(text, { priority, interrupt })` → `{sayId}`; text ≤ 1000 characters.

- `priority: "high"` or `interrupt: true` → the current reply/TTS is cut
  (`interrupted{source:"say"}`) and the text plays immediately.
- `priority: "normal"` → plays now if idle, otherwise waits in the server's
  **single** pending slot; a newer normal `say` replaces an older waiting one
  (`say_done{status:"replaced"}`). Any interruption (barge-in, `interrupt()`,
  a high-priority say) drops the pending say (`status:"interrupted"`).
- Need ordered multi-item playback? Keep the queue in your App and issue the
  next `say` on `say_done` — the host guarantees only *no overlap*.

`say` is billed like any TTS (`APP_TTS` per character); first audio typically
arrives well under a second because no LLM is involved.

## Live context: what to put in, what to keep out

`setContext` is the right place for *facts the model needs to answer the next
question*: a compact JSON digest of the current state, the selected item, the
last few events. Keep it small (≤ 4 KB; a few hundred bytes is typical) and
replace it whenever it changes — it costs nothing until the next utterance.

The host wraps it in a `<live_context>…</live_context>` fence appended to your
`system` prompt, prefixed with a comment telling the model to treat the block
as data for this turn only, and it never enters the conversation history. The
composed prompt then goes through the same guard as every App system prompt:
boundary-forging tokens (`<system>`, `</system>`, `<safety`,
`<app_system_prompt>`, `system:`) make the turn fail with
`error{code:"processing_error"}`, and the agent builder html-escapes the
whole block before the model sees it, so markup inside your context is inert.
Two rules:

- **Do not put instructions the user cannot see in `context`.** It is data,
  not a hidden prompt; using it to steer the model behind the user's back
  fails review.
- **Do not put the user's own speech in it.** The transcript already is the
  conversation; duplicating it confuses the model.

## Cost model — only what you send is billed

ASR is billed per *recognised* second (`APP_STT`), TTS per synthesised
character (`APP_TTS`); LLM turns are billed by the agent session as usual. An
open-but-silent session costs **nothing**, so:

- Gate `sendAudio` behind push-to-talk or your own wake-word / VAD
  (`mic.onLevel(rms)` is a cheap input). Streaming an open mic for an hour is
  the single most expensive thing an App can do.
- Use `llm: "none"` when you only need `say()` or raw transcripts.
- `end()` returns `{total_asr_seconds, total_tts_characters}` — show it to users
  in long sessions, and watch `quota_warning`.

## Errors

Open-time failures reject the `anna.audio.session()` promise with `error.code`;
runtime failures arrive as `error` events.

| Code | Meaning |
|---|---|
| `permission_denied` | Window not yours / inactive, `host_api.audio` lacks `session`, or `llm:"agent"` without a matching `agent.session` submode |
| `not_granted` | `media_grant.audio` off, or `speak` / `transcribe` sub-flag off |
| `concurrency_limit` | A session is already open for this window |
| `not_supported` | Host feature flag off, or no WebSocket in this page |
| `quota_exhausted` | CU pool empty (at open or during the periodic check) |
| `asr_not_available` / `tts_not_available` | No realtime ASR / TTS model routable for this user |
| `invalid_request` | Bad `llm`, empty `say` text, message before start |
| `context_too_large` / `system_too_large` / `say_too_long` | 4 KB / 8 KB / 1000-char caps (`setContext` / `say` are rejected client-side by the SDK; `system` is checked by the host at open) |
| `session_timeout` | `maxDurationSec` reached; `ended` follows |
| `asr_error` / `tts_error` / `tts_peer_closed` / `tts_upstream_error` / `llm_timeout` / `processing_error` | Provider failure during a turn; the session normally survives |
| `internal_error` | Unexpected host failure; socket closes (1011) and `ended` fires |
| `timeout` / `network` / `closed` | Bridge-level: no start within 15 s, socket error, window torn down |

## Mobile

Inside the Anna mobile app the same code runs, with two differences:

- **Foreground only.** iOS WKWebView suspends `getUserMedia` and timers when
  the app leaves the foreground; the shell forwards React-Native `AppState`
  as the host event `host.app_state {state: "active" | "inactive" | "background"}`.
  Release push-to-talk and `end()` (or at least stop sending) on anything but
  `active`:

  ```js
  anna.on("host.app_state", ({ state }) => { if (state !== "active" && vs) vs.end(); });
  ```

- **Permissions are pre-warmed.** When your session opens, the shell requests
  the OS microphone permission and switches the audio session to
  record-and-play; your in-iframe `getUserMedia` then resolves without a second
  prompt on iOS 15+. Android needs a development build of the Anna app (Expo Go
  cannot grant WebView microphone access).

See [Mobile Support](/developers/apps/app-mobile) for the rest of the mobile
checklist.

## Local development

`anna-app dev` (CLI ≥ 0.1.59) mocks the relay in the harness: browser
`SpeechRecognition` stands in for ASR, your local `agent.session` for the LLM,
`speechSynthesis` for TTS. Event names and payload shapes match production, so
the loop above runs unchanged; latency, voices and `tts_audio` PCM are **not**
representative — verify those on staging.

The reference App is
[`anna-app-voice-demo`](https://github.com/whtcjdtc2007/anna-executa-examples/tree/main/examples/anna-app-voice-demo)
(push-to-talk, auto-updating context, `say` normal/high, barge-in, first-audio
timing and the usage summary).

## See also

- [App UI Media](/developers/apps/app-ui-media) — the synchronous `audio.speak` / `audio.transcribe` surface and `media_grant`
- [LLM & Agent](/developers/apps/llm-and-agent) — agent sessions, submodes, tool surface
- [App UI Host API](/developers/apps/app-ui-host-api) — envelope, ACL model, generic errors
- [Reference · `audio.*`](/developers/reference/host-api-audio) — every field, event and limit
