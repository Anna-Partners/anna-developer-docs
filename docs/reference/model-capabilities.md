---
title: "Model capabilities"
description: "Every TTS, image, video and music model on the platform with its adjustable options, limits and CU pricing — generated from the live catalogue."
section: reference
slug: model-capabilities
order: 5
updated: 2026-10-21
estimated_minutes: 4
---


> **Generated** from `GET /api/v1/llm-models/public` (the same catalogue that powers
> `anna.llm.catalog`) by `matrix-nexus/scripts/export_model_capabilities.py` on 2026-10-21.
> Do not edit by hand — re-run the exporter. The live, per-App view (with your own grants
> and quota) is the **Compare** tab of the Developer Console Playground:
> [`/developer?view=playground&modality=compare`](https://anna.partners/developer?view=playground&modality=compare).

Every knob below is a key of `capabilities.options` returned by
[`llm.catalog`](/developers/apps/app-ui-media#discover-before-you-call); pass it in
`params` on [`audio.speak`](/developers/apps/app-ui-media#audio-synchronous-tts-and-stt)
or [`image.generate` / `image.edit`](/developers/apps/app-ui-host-api#image) (and their
async twins `image.generateAsync` / `image.editAsync` — the `jobs` column). Values
outside the declared range fail with `AUDIO_OPTION_INVALID` / `IMAGE_OPTION_INVALID`;
keys a model does not declare are dropped and echoed in `ignoredParams`. Prices are in
CU at the platform's current USD→CU ratio and may change.


◆ = platform default for that service type when the user has no preference (`isPlatformDefault`). Users pick their own default under `/llm → Specialized Models`.

## Text-to-speech (`serviceType: 'tts'`)

| Model | speed | pitch | volume | vol | stability | similarity_boost | style | emotion | instruction | apply_text_normalization | english_normalization | language | timestamps | format | maxCharsPerCall | voices | CU / 1k chars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ◆ **Qwen Audio 3.0 TTS Plus**<br>`qwen-audio-3.0-tts-plus` | 0.5–2.0 /0.1 x | 0.5–2.0 /0.1 x | 0–100 /1 | — | — | — | — | — | text ≤200 | — | — | `auto`, `zh`, `en`, `ja`, `ko`, `fr`, `de`, `es` +3 | — | `mp3`, `wav`, `pcm` | 1000 | 2 | 4 |
| **Qwen Audio 3.0 TTS Flash**<br>`qwen-audio-3.0-tts-flash` | 0.5–2.0 /0.1 x | 0.5–2.0 /0.1 x | 0–100 /1 | — | — | — | — | — | text ≤200 | — | — | `auto`, `zh`, `en`, `ja`, `ko`, `fr`, `de`, `es` +3 | — | `mp3`, `wav`, `pcm` | 2000 | 12 | 3 |
| **Qwen3 TTS Flash (Realtime)**<br>`qwen3-tts-flash-realtime` | 0.5–2.0 /0.1 x | 0.5–2.0 /0.1 x | 0–100 /1 | — | — | — | — | — | text ≤500 | — | — | — | — | `mp3`, `wav`, `pcm`, `opus` | 2000 | 49 | 1 |
| **ElevenLabs Eleven v3 (fal)**<br>`fal-ai/elevenlabs/tts/eleven-v3` | — | — | — | — | 0.0–1.0 /0.05 | — | — | — | — | `auto`, `on`, `off` | — | `auto` (free text) | on / off | `mp3` | 1000 | 12 | 20 |
| **ElevenLabs Multilingual v2 (fal)**<br>`fal-ai/elevenlabs/tts/multilingual-v2` | 0.7–1.2 /0.05 x | — | — | — | 0.0–1.0 /0.05 | 0.0–1.0 /0.05 | 0.0–1.0 /0.05 | — | — | `auto`, `on`, `off` | — | `auto` (free text) | on / off | `mp3` | 1000 | 12 | 20 |
| **ElevenLabs Turbo v2.5 (fal)**<br>`fal-ai/elevenlabs/tts/turbo-v2.5` | 0.7–1.2 /0.05 x | — | — | — | 0.0–1.0 /0.05 | 0.0–1.0 /0.05 | 0.0–1.0 /0.05 | — | — | `auto`, `on`, `off` | — | `auto` (free text) | on / off | `mp3` | 1000 | 12 | 10 |
| **MiniMax Speech 02 HD (fal)**<br>`fal-ai/minimax/speech-02-hd` | 0.5–2.0 /0.05 x | -12–12 /1 | — | 0.1–10.0 /0.1 | — | — | — | `happy`, `sad`, `angry`, `fearful`, `disgusted`, `surprised`, `neutral` | — | — | on / off | `auto`, `zh`, `en`, `ja`, `ko` | — | `mp3`, `pcm`, `flac` | 1000 | 14 | 20 |
| **xAI TTS v1 (fal)**<br>`xai/tts/v1` | — | — | — | — | — | — | — | — | — | — | — | `auto`, `en`, `ar-EG`, `ar-SA`, `zh`, `cs`, `nl`, `fi` +13 | — | `mp3`, `wav`, `pcm` | 2000 | 28 | 3 |

<div data-anna-try-it="tts"></div>

Range cells read `min–max /step unit`. `language` on ElevenLabs is free text (ISO 639-1). `eleven-v3` exposes only `stability` on fal — pick `multilingual-v2` / `turbo-v2.5` for `similarity_boost` / `style` / `speed`.

## Image generation & editing (`serviceType: 'image_gen' | 'image_edit'`)

| Model | sizeInput | size | aspect_ratio | resolution | quality | n | output_format | thinking_level | enable_web_search | edit | jobs | CU |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ◆ **Nano Banana 2 (fal)**<br>`fal-ai/nano-banana-2` | `aspect_ratio` | — | `auto`, `21:9`, `16:9`, `3:2`, `4:3`, `5:4`, `1:1`, `4:5` +7 | `0.5K`, `1K`, `2K`, `4K` | — | 1–4 /1 | `png`, `jpeg`, `webp` | `minimal`, `high` | on / off | refs ≤14 | ✓ | 16 / image<br>0.5K: 12 · 1K: 16 · 2K: 24 · 4K: 32<br>+ enable_web_search: 3 · thinking_level=high: 1 |
| **GPT Image 2 (fal)**<br>`openai/gpt-image-2` | `size` | 6 presets + custom (×16, ≤3840px, ≤8.3MP, ratio ≤3.0:1) | — | — | `low`, `medium`, `high` | 1–1 /1 | `png`, `jpeg`, `webp` | — | — | refs ≤8 · mask | ✓ | 42 / image<br>1024x768: low=1 · medium=7 · high=29 |
| **Seedream 5.0 Pro (fal)**<br>`bytedance/seedream/v5/pro/text-to-image` | `both` | custom (×8, ≤2048px, ≤4.2MP) | `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`, `21:9` | — | — | 1–1 /1 | — | — | — | — | ✓ | 14 / image<br>≤2.4MP: 14 · ≤4.2MP: 27 |

<div data-anna-try-it="image_gen"></div>

`sizeInput` tells you which option drives the output: `size` (pick from presets or, where `custom` is listed, any WxH within the constraints), `aspect_ratio` (+ `resolution`), or `both`. Request with `fit: "strict"` to fail instead of being snapped to the nearest same-orientation size — see [Size semantics](/developers/apps/app-ui-host-api#image).

## Video generation (`serviceType: 'video_gen'`)

| Model | durationSec | resolution | aspectRatio | generateAudio | imageToVideo | audio | CU |
|---|---|---|---|---|---|---|---|
| ◆ **MiniMax H3 Max Turbo (fal)**<br>`minimax/h3-max-turbo` | 5–10 /1 s | `480p`, `768p`, `1080p` | `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | — | yes | no | CU / s<br>480p: 5 · 768p: 8 · 1080p: 16<br>min 5s |
| **MiniMax H3 Max (fal)**<br>`minimax/h3-max` | 5–10 /1 s | `480p`, `768p`, `1080p` | `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | — | yes | no | CU / s<br>480p: 10 · 768p: 16 · 1080p: 32<br>min 5s |
| **Kling v3 Pro (fal)**<br>`fal-ai/kling-video/v3/pro` | `3`, `4`, `5`, `6`, `7`, `8`, `9`, `10` +5 | — | `16:9`, `9:16`, `1:1` | on / off | yes | yes | CU / s<br>22 / audio on 34 |
| **Seedance 2.5 (fal)**<br>`bytedance/seedance-2.5` | 4–30 /1 s | `480p`, `720p`, `1080p` | `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | on / off | yes | yes | CU / s<br>480p: 44 · 720p: 95 · 1080p: 233 |

<div data-anna-try-it="video_gen"></div>

`video.generate` is **asynchronous**: it returns a job in ~1 s, CU is held on submit and settled / refunded at the terminal state; option keys are the request fields (`durationSec`, `resolution`, `aspectRatio`, `generateAudio`). See [Video: async jobs](/developers/apps/app-ui-media#video-async-jobs).

## Music generation (`serviceType: 'music_gen'`)

| Model | duration | vocals / lyrics | prompt | referenceImage | format | instrumental | lyrics_optimizer | durationSec | seed | CU |
|---|---|---|---|---|---|---|---|---|---|---|
| ◆ **MiniMax Music 2.6 (fal)**<br>`fal-ai/minimax-music/v2.6` | model-decided (≤240 s) | field<br>≤3500 chars | ≤2000 chars | — | `mp3`, `wav` | on / off | on / off | — | — | CU / song<br>30 |
| **Lyria 3 Pro (fal)**<br>`fal-ai/lyria3/pro` | model-decided (≤180 s) | prompt_embedded<br>≤2000 chars<br>`en`, `de`, `es`, `fr`, `hi`, `ja`, `ko`, `pt` | ≤5000 chars | yes | `mp3` | on / off | — | — | — | CU / song<br>16 |
| **Lyria 3 (fal)**<br>`fal-ai/lyria3` | model-decided (≤30 s) | prompt_embedded<br>≤2000 chars<br>`en`, `de`, `es`, `fr`, `hi`, `ja`, `ko`, `pt` | ≤5000 chars | yes | `mp3` | on / off | — | — | — | CU / song<br>8 |
| **ElevenLabs Music (fal)**<br>`fal-ai/elevenlabs/music` | 3–600 s (default 60) | prompt_embedded<br>≤2000 chars | ≤4000 chars | — | `mp3` | on / off | — | 3–600 /1 s | — | CU / min<br>120 (rounded up to whole minutes) |
| **Stable Audio 2.5 (fal)**<br>`fal-ai/stable-audio-25/text-to-audio` | 1–190 s (default 190) | instrumental only | ≤10000 chars | — | `wav` | — | — | 1–190 /1 s | 0–2147483647 /1 | CU / song<br>40 |
| **ACE-Step (fal)**<br>`fal-ai/ace-step` | 5–240 s (default 60) | field<br>≤4000 chars<br>`en`, `zh`, `ru`, `es`, `ja`, `de`, `fr`, `pt`, `it`, `ko` | ≤1000 chars | — | `wav` | on / off | — | 5–240 /1 s | 0–2147483647 /1 | CU / s<br>1 |

<div data-anna-try-it="music_gen"></div>

`music.generate` is **asynchronous** like video (same `media_job` events, same pre-charge → settle / refund). Prices are per song, per audio second or per started minute depending on the provider's billing unit (`pricing.cuPerSong` / `cuPerSecond` / `cuPerMinute`). A feature the chosen model cannot deliver (lyrics, stems, continuation, a reference image, an unsupported duration or format) is **rejected** with `MUSIC_FEATURE_UNSUPPORTED` and `data.alternatives` — the host never downgrades silently. See [Music: async jobs](/developers/apps/app-ui-media#music-async-jobs).

## See also

- [App UI Media](/developers/apps/app-ui-media) — `audio.speak` `params` / `ignoredParams`
- [App UI Host API → image](/developers/apps/app-ui-host-api#image) — `model` / `params` / `fit`
- [Model options form](/developers/reference/model-options-form) — render these schemas in your own App
- Developer Console Playground — `/developer?view=playground`
