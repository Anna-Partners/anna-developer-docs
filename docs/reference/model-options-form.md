---
title: "Model options form"
description: "Render any TTS or image model's option schema as a form — the same component the platform uses in /llm and the Developer Console Playground."
section: reference
slug: model-options-form
order: 6
updated: 2026-10-16
estimated_minutes: 6
---

Every TTS and image model on the platform describes its adjustable knobs in
`capabilities.options` (returned by [`llm.catalog`](/developers/apps/app-ui-media#discover-before-you-call)).
`ModelOptionsForm` turns that schema into a form and validates values with
**exactly the rules the API applies** — a value the form accepts is a value
`audio.speak` / `image.generate` accepts. The platform uses it on `/llm`
(Voice Settings) and in the Developer Console Playground; you can use it in
your App for a model-aware settings UI.

## Try it

Pick a model, move the knobs — the snippet updates live. Run it for real in the
Playground (requires a developer account).

<div data-anna-try-it="tts"></div>

<div data-anna-try-it="image_gen"></div>

## Load it

A single dependency-free script (`window.ModelOptionsForm`) plus a stylesheet
that only uses CSS variables (`--text-primary`, `--border-color`, `--accent-color`, …),
so it follows your App's theme:

```html
<link rel="stylesheet" href="https://anna.partners/static/css/model-options-form.css">
<script src="https://anna.partners/static/js/model-options-form.js"></script>
```

Or copy both files into your bundle (MIT, see the file header) — they have no
other dependencies and no network access.

## Render a form

```js
const { models } = await anna.llm.catalog({ serviceType: 'tts' });
const model = models.find(m => m.isUserPreferred) ?? models.find(m => m.isPlatformDefault);

const form = ModelOptionsForm.create(document.querySelector('#voice-settings'), {
  options: model.capabilities.options,  // v2 schema (v1 shapes are normalised)
  values: savedSettings,                 // {speed: 1.2, stability: 0.4, …}
  scope: null,                           // null = every knob; ['preference','both'] = user-level only
  lang: 'en',                            // 'zh' | 'en' — picks label/help translations
  idPrefix: 'voice',                     // DOM id prefix (several forms per page are fine)
  hidden: [],                            // keys your UI renders itself (e.g. ['n', 'size'])
  onChange(key, value, allValues) {      // key === '*' after setOptions()
    savedSettings = allValues;
  },
});

// Switching models: values are kept where the new model declares the same key,
// clamped to its range / snapped to its step, or reset to the default (with a
// small "reset: not supported by this model" note).
form.setOptions(otherModel.capabilities.options, { preserve: true });

form.getValues();   // only keys the current model declares (and that pass `scope`)
form.setValues({ speed: 1.0 });
form.reset();       // back to the schema defaults
form.destroy();
```

Then call the API with `params: form.getValues()`:

```js
const out = await anna.audio.speak({ text, model: model.modelName, voice, params: form.getValues() });
out.params;         // what reached the provider, normalised
out.ignoredParams;  // keys this model does not declare — dropped, never surcharged
```

## Validate without rendering

The pure helpers are exported for server-less validation (e.g. before an
`image.generate` call or when importing a saved preset):

```js
const options = ModelOptionsForm.normalizeOptions(model.capabilities.options);
const { clean, ignored, errors } = ModelOptionsForm.validate(options, {
  resolution: '4K', quality: 'ultra', thinking_level: 'high',
});
// errors → [{ key: 'quality', reason: 'not_allowed', allowed: ['low','medium','high'] }]
// ignored → keys the model does not declare
// clean  → coerced values ('1.5' → 1.5, 'true' → true, '1024*1024' → '1024x1024')
```

`errors[].reason` is one of `out_of_range | not_allowed | too_long | type` — the
same `data.reason` the API returns in `AUDIO_OPTION_INVALID` / `IMAGE_OPTION_INVALID`
/ `IMAGE_SIZE_UNSUPPORTED`, so you can share one error-rendering path.

## Schema reference

| `type` | Fields | Control |
|---|---|---|
| `range` | `min`, `max`, `step`, `default`, `unit?` | slider + number input; integer steps yield integers |
| `select` | `values` (strings or `{value, label}`), `default`, `freeform?` | `<select>`; `freeform: true` renders an input with a datalist (e.g. ElevenLabs `language`) |
| `boolean` | `default` | toggle; also accepts `"true"` / `"false"` strings |
| `text` | `maxLength`, `default`, `placeholder?` | single-line textarea with a counter |
| `size` | `values` (`"WxH"` presets), `default`, `custom?` `{multipleOf, minEdge, maxEdge, minPixels, maxPixels, maxAspectRatio}` | preset picker; with `custom`, a **Custom…** entry opens W × H inputs validated live against the constraints |

Every key may also carry `scope` (`preference` · `request` · `both`),
`label` / `help` / `placeholder` (`{zh, en}`) and `affectsPrice` (rendered as a
small **CU** tag; re-estimate cost when it changes). Keys render in a fixed order
(`size, aspect_ratio, resolution, quality, n, speed, pitch, volume, …`) exposed as
`ModelOptionsForm.KEY_ORDER`; `sortKeys(keys)` applies it to your own lists.

## See also

- [Model capabilities](/developers/reference/model-capabilities) — every model's options at a glance
- [App UI Media](/developers/apps/app-ui-media) — `audio.speak` `params` / `ignoredParams`
- [App UI Host API → image](/developers/apps/app-ui-host-api#image) — `model` / `params` / `fit`
