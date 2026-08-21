---
title: "What is an Anna App"
description: "Apps bundle a curated set of Executas plus prompt instructions into a one-click install for end users."
section: apps
slug: app-intro
order: 1
updated: 2026-04-29
estimated_minutes: 4
---

An **Anna App** is the highest-level packaging unit in the Anna App Store. It bundles:

- A curated set of **Executas** (Anna's tool/skill plugins) the app depends on.
- Prompt instructions (`system_prompt_addendum`, `user_message_prefix_template`) that steer the assistant when the user `#`mentions the app in a chat.
- **Listing metadata** (name, slug, category, tagline, description, logo, screenshots, homepage, pricing model) that powers the App Store entry.
- *(Optional, manifest `schema: 2`)* an **App UI bundle** — a static SPA (HTML/JS/CSS/wasm/fonts) that is uploaded to Anna and rendered inside a sandboxed `<iframe>` window on the dashboard. See [App UI Overview](/developers/apps/app-ui-overview).

When a user installs an app from the **Anna App Store**, every `required_executas` entry that the user does not yet have is auto-installed for them. From that point on, the user can `#`mention the app in any conversation to apply its bundled tools and prompt directives for that turn. If the app ships a UI, the assistant can also summon the app window via the built-in `open_app_view` tool.

<figure class="dh-figure">
<svg viewBox="0 0 720 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="An Anna App bundles Executas, prompt directives, listing metadata, and an optional UI bundle into a single install referenced from chat by hash-mention.">
<defs>
<linearGradient id="aiAppGrad" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#FF9E6C"/>
<stop offset="1" stop-color="#B388FF"/>
</linearGradient>
<linearGradient id="aiChip" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#1B1D27"/>
<stop offset="1" stop-color="#12141C"/>
</linearGradient>
</defs>
<g font-family="Inter, sans-serif" font-size="12" fill="#E6E7EE">
<g transform="translate(34 46)">
<rect width="170" height="36" rx="18" fill="url(#aiChip)" stroke="#FF9E6C" stroke-opacity="0.55"/>
<circle cx="20" cy="18" r="4" fill="#FF9E6C"/>
<text x="34" y="22">Executas</text>
</g>
<g transform="translate(34 102)">
<rect width="170" height="36" rx="18" fill="url(#aiChip)" stroke="#B388FF" stroke-opacity="0.55"/>
<circle cx="20" cy="18" r="4" fill="#B388FF"/>
<text x="34" y="22">Prompt directives</text>
</g>
<g transform="translate(34 158)">
<rect width="170" height="36" rx="18" fill="url(#aiChip)" stroke="#82B1FF" stroke-opacity="0.55"/>
<circle cx="20" cy="18" r="4" fill="#82B1FF"/>
<text x="34" y="22">Listing metadata</text>
</g>
<g transform="translate(34 214)">
<rect width="170" height="36" rx="18" fill="url(#aiChip)" stroke="#FFC8A2" stroke-opacity="0.6" stroke-dasharray="3 3"/>
<circle cx="20" cy="18" r="4" fill="#FFC8A2"/>
<text x="34" y="22">UI bundle (optional)</text>
</g>
</g>
<g stroke="url(#aiAppGrad)" stroke-opacity="0.55" fill="none" stroke-width="1.2">
<path d="M204 64 C 270 64 270 145 330 145"/>
<path d="M204 120 C 270 120 270 145 330 145"/>
<path d="M204 176 C 270 176 270 145 330 145"/>
<path d="M204 232 C 270 232 270 145 330 145"/>
</g>
<g transform="translate(310 90)">
<rect x="4" y="6" width="110" height="110" rx="26" fill="#000" opacity="0.18" filter="blur(4px)"/>
<rect width="110" height="110" rx="26" fill="url(#aiAppGrad)"/>
<rect x="0.5" y="0.5" width="109" height="109" rx="25.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.28"/>
<rect x="3" y="3" width="104" height="40" rx="23" fill="#FFFFFF" opacity="0.10"/>
<g transform="translate(55 55)" fill="#FFFFFF">
<path d="M0 -30 Q 6 -6 30 0 Q 6 6 0 30 Q -6 6 -30 0 Q -6 -6 0 -30 Z" opacity="0.96"/>
<path d="M24 -22 Q 25 -14 32 -12 Q 25 -10 24 -2 Q 23 -10 16 -12 Q 23 -14 24 -22 Z" opacity="0.85"/>
<circle cx="-22" cy="22" r="2" opacity="0.7"/>
</g>
<text x="55" y="138" text-anchor="middle" font-family="Space Grotesk, sans-serif" font-size="11" fill="#E6E7EE" letter-spacing="0.22em" font-weight="700">ANNA APP</text>
<text x="55" y="154" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="9" fill="#A6A8B5">single install · v1.0.0</text>
</g>
<g stroke="#FFC8A2" stroke-opacity="0.75" fill="none" stroke-width="1.5">
<path d="M440 145 L 540 145" stroke-dasharray="4 4"/>
<polyline points="534,139 544,145 534,151" stroke-linejoin="round" stroke-linecap="round"/>
</g>
<g transform="translate(540 95)">
<rect width="150" height="100" rx="14" fill="#12141C" stroke="#FFC8A2" stroke-opacity="0.35"/>
<text x="14" y="28" font-family="JetBrains Mono, monospace" font-size="11" fill="#82B1FF">#research-buddy</text>
<line x1="14" y1="40" x2="136" y2="40" stroke="#FFC8A2" stroke-opacity="0.18"/>
<text x="14" y="58" font-family="Inter, sans-serif" font-size="11" fill="#A6A8B5">summarise the</text>
<text x="14" y="74" font-family="Inter, sans-serif" font-size="11" fill="#A6A8B5">latest paper on...</text>
<circle cx="136" cy="86" r="3" fill="#FF9E6C"/>
</g>
</svg>
<figcaption>One install · one hash-mention · the assistant gains a curated capability set</figcaption>
</figure>

> [!TIP]
> In a hurry? Skip the theory and follow the [60-second quickstart](/developers/apps/app-quickstart) — `anna-app init` → `anna-app dev` → `anna-app validate`.

## Why ship an App instead of standalone Executas?

- **Discovery** — the App Store is where most non-technical users browse.
- **Composition** — a single Executa is rarely the full UX; an App glues a few of them together with a `system_prompt_addendum` that tells the assistant how to combine them.
- **Branding** — your app name, logo, and tagline appear on the user's App Store listings.
- **One-click install** — the user accepts a single install instead of authorising each Executa one by one.

<figure class="dh-figure">
<svg viewBox="0 0 720 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Four quadrants illustrate the four reasons to ship an App: Discovery, Composition, Branding, and One-click install.">
<defs>
<linearGradient id="wsBrand" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#FF9E6C"/>
<stop offset="1" stop-color="#B388FF"/>
</linearGradient>
<linearGradient id="wsTool" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#1B1D27"/>
<stop offset="1" stop-color="#12141C"/>
</linearGradient>
<radialGradient id="wsCardBg" cx="0.5" cy="0" r="1">
<stop offset="0" stop-color="#FFFFFF" stop-opacity="0.04"/>
<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
</radialGradient>
</defs>

<g fill="url(#wsCardBg)" stroke="#FFC8A2" stroke-opacity="0.18">
<rect x="20"  y="20"  width="335" height="155" rx="14"/>
<rect x="365" y="20"  width="335" height="155" rx="14"/>
<rect x="20"  y="185" width="335" height="155" rx="14"/>
<rect x="365" y="185" width="335" height="155" rx="14"/>
</g>

<g transform="translate(20 20)">
<text x="18" y="28" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.22em" fill="#FF9E6C">01 · DISCOVERY</text>
<text x="18" y="48" font-family="Inter, sans-serif" font-size="13" font-weight="700" fill="#E6E7EE">Found in the App Store</text>
<g transform="translate(18 64)">
<rect width="200" height="26" rx="13" fill="url(#wsTool)" stroke="#FFC8A2" stroke-opacity="0.22"/>
<g transform="translate(13 13)" stroke="#FFC8A2" stroke-opacity="0.7" stroke-width="1.3" fill="none" stroke-linecap="round">
<circle cx="0" cy="0" r="4"/><line x1="3" y1="3" x2="6" y2="6"/>
</g>
<text x="28" y="17" font-family="JetBrains Mono, monospace" font-size="10" fill="#A6A8B5">research</text>
<rect x="84" y="9" width="2" height="9" fill="#FF9E6C"/>
</g>
<g transform="translate(18 100)">
<rect width="44" height="44" rx="10" fill="url(#wsBrand)"/>
<rect x="0.5" y="0.5" width="43" height="43" rx="9.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.28"/>
<g transform="translate(22 22)" fill="#FFFFFF">
<path d="M0 -10 Q 2 -2 10 0 Q 2 2 0 10 Q -2 2 -10 0 Q -2 -2 0 -10 Z"/>
</g>
</g>
<g transform="translate(72 100)" fill="url(#wsTool)" stroke="#FFC8A2" stroke-opacity="0.22">
<rect width="44" height="44" rx="10"/>
</g>
<g transform="translate(126 100)" fill="url(#wsTool)" stroke="#FFC8A2" stroke-opacity="0.22">
<rect width="44" height="44" rx="10"/>
</g>
<g transform="translate(180 100)" fill="url(#wsTool)" stroke="#FFC8A2" stroke-opacity="0.22">
<rect width="44" height="44" rx="10"/>
</g>
<text x="244" y="120" font-family="Inter, sans-serif" font-size="10" fill="#A6A8B5">non-technical</text>
<text x="244" y="134" font-family="Inter, sans-serif" font-size="10" fill="#A6A8B5">users browse</text>
</g>


<g transform="translate(365 20)">
<text x="18" y="28" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.22em" fill="#B388FF">02 · COMPOSITION</text>
<text x="18" y="48" font-family="Inter, sans-serif" font-size="13" font-weight="700" fill="#E6E7EE">Executas + prompt = UX</text>
<g font-family="JetBrains Mono, monospace" font-size="9" fill="#A6A8B5">
<g transform="translate(18 70)"><rect width="80" height="22" rx="11" fill="url(#wsTool)" stroke="#FF9E6C" stroke-opacity="0.5"/><circle cx="11" cy="11" r="3" fill="#FF9E6C"/><text x="22" y="14">web_search</text></g>
<g transform="translate(18 96)"><rect width="80" height="22" rx="11" fill="url(#wsTool)" stroke="#B388FF" stroke-opacity="0.5"/><circle cx="11" cy="11" r="3" fill="#B388FF"/><text x="22" y="14">img_gen</text></g>
<g transform="translate(18 122)"><rect width="80" height="22" rx="11" fill="url(#wsTool)" stroke="#82B1FF" stroke-opacity="0.5"/><circle cx="11" cy="11" r="3" fill="#82B1FF"/><text x="22" y="14">pdf_reader</text></g>
<g transform="translate(106 96)">
<rect width="100" height="22" rx="11" fill="url(#wsTool)" stroke="#FFC8A2" stroke-opacity="0.45" stroke-dasharray="3 3"/>
<text x="50" y="14" text-anchor="middle" font-family="Space Grotesk, sans-serif" font-size="8" letter-spacing="0.18em" fill="#FFC8A2">+ PROMPT</text>
</g>
</g>
<g fill="none" stroke="url(#wsBrand)" stroke-opacity="0.7" stroke-width="1.4" stroke-linecap="round">
<path d="M210 81 C 240 90 250 100 260 110"/>
<path d="M210 107 L 260 110"/>
<path d="M210 133 C 240 124 250 115 260 110"/>
</g>
<polyline points="254,103 264,110 254,117" fill="none" stroke="#B388FF" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
<g transform="translate(265 88)">
<rect width="50" height="44" rx="11" fill="url(#wsBrand)"/>
<rect x="0.5" y="0.5" width="49" height="43" rx="10.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.28"/>
<g transform="translate(25 22)" fill="#FFFFFF">
<path d="M0 -11 Q 2 -2 11 0 Q 2 2 0 11 Q -2 2 -11 0 Q -2 -2 0 -11 Z"/>
</g>
</g>
</g>
<g transform="translate(20 185)">
<text x="18" y="28" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.22em" fill="#82B1FF">03 · BRANDING</text>
<text x="18" y="48" font-family="Inter, sans-serif" font-size="13" font-weight="700" fill="#E6E7EE">Your name on the listing</text>
<g transform="translate(18 64)">
<rect width="300" height="80" rx="14" fill="url(#wsTool)" stroke="#FFC8A2" stroke-opacity="0.28"/>
<g transform="translate(14 14)">
<rect width="52" height="52" rx="13" fill="url(#wsBrand)"/>
<rect x="0.5" y="0.5" width="51" height="51" rx="12.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.28"/>
<rect x="2" y="2" width="48" height="20" rx="11" fill="#FFFFFF" opacity="0.12"/>
<g transform="translate(26 26)" fill="#FFFFFF">
<path d="M0 -14 Q 3 -3 14 0 Q 3 3 0 14 Q -3 3 -14 0 Q -3 -3 0 -14 Z"/>
</g>
</g>
<text x="80" y="30" font-family="Inter, sans-serif" font-size="13" font-weight="700" fill="#E6E7EE">Research Buddy</text>
<text x="80" y="48" font-family="Inter, sans-serif" font-size="10" fill="#A6A8B5">Cite-first research with PDFs &amp; web</text>
<g transform="translate(80 56)" font-family="JetBrains Mono, monospace" font-size="8" fill="#FFC8A2" fill-opacity="0.85">
<rect width="44" height="14" rx="7" fill="none" stroke="#FFC8A2" stroke-opacity="0.3"/>
<text x="22" y="10" text-anchor="middle" letter-spacing="0.14em">RESEARCH</text>
</g>
<g transform="translate(130 56)" font-family="JetBrains Mono, monospace" font-size="8" fill="#FFC8A2" fill-opacity="0.85">
<rect width="58" height="14" rx="7" fill="none" stroke="#FFC8A2" stroke-opacity="0.3"/>
<text x="29" y="10" text-anchor="middle" letter-spacing="0.14em">PRODUCTIVITY</text>
</g>
<text x="284" y="22" text-anchor="end" font-family="JetBrains Mono, monospace" font-size="9" fill="#A6A8B5">v1.0.0</text>
</g>
</g>
<g transform="translate(365 185)">
<text x="18" y="28" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.22em" fill="#FF9E6C">04 · ONE-CLICK INSTALL</text>
<text x="18" y="48" font-family="Inter, sans-serif" font-size="13" font-weight="700" fill="#E6E7EE">One consent · all Executas</text>
<g transform="translate(18 64)" font-family="JetBrains Mono, monospace" font-size="9">
<g><rect width="115" height="18" rx="9" fill="url(#wsTool)" stroke="#A6A8B5" stroke-opacity="0.25"/><text x="9" y="12" fill="#A6A8B5">authorise web_search</text></g>
<g transform="translate(0 22)"><rect width="115" height="18" rx="9" fill="url(#wsTool)" stroke="#A6A8B5" stroke-opacity="0.25"/><text x="9" y="12" fill="#A6A8B5">authorise img_gen</text></g>
<g transform="translate(0 44)"><rect width="115" height="18" rx="9" fill="url(#wsTool)" stroke="#A6A8B5" stroke-opacity="0.25"/><text x="9" y="12" fill="#A6A8B5">authorise pdf_reader</text></g>
<line x1="20" y1="68" x2="115" y2="-4" stroke="#FF6B6B" stroke-opacity="0.55" stroke-width="1.2"/>
<line x1="115" y1="68" x2="20" y2="-4" stroke="#FF6B6B" stroke-opacity="0.55" stroke-width="1.2"/>
</g>
<g fill="none" stroke="url(#wsBrand)" stroke-opacity="0.85" stroke-width="1.6" stroke-linecap="round">
<line x1="148" y1="100" x2="178" y2="100" stroke-dasharray="3 3"/>
<polyline points="172,94 182,100 172,106" stroke-linejoin="round"/>
</g>
<g transform="translate(184 78)">
<rect width="130" height="44" rx="22" fill="url(#wsBrand)"/>
<rect x="0.5" y="0.5" width="129" height="43" rx="21.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.32"/>
<g transform="translate(28 22)" stroke="#FFFFFF" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round">
<path d="M0 -7 V 5"/><polyline points="-5,0 0,5 5,0"/>
<line x1="-7" y1="9" x2="7" y2="9"/>
</g>
<text x="78" y="27" text-anchor="middle" font-family="Space Grotesk, sans-serif" font-size="11" font-weight="700" fill="#0A0B11" letter-spacing="0.18em">INSTALL</text>
</g>
<text x="184" y="138" font-family="Inter, sans-serif" font-size="10" fill="#A6A8B5">single accept</text>
<text x="244" y="138" font-family="Inter, sans-serif" font-size="10" fill="#FF9E6C">·</text>
<text x="252" y="138" font-family="Inter, sans-serif" font-size="10" fill="#A6A8B5">all bundled</text>
</g>
</svg>
<figcaption>Discovery · Composition · Branding · One-click install</figcaption>
</figure>

## Anatomy

Most of an Anna App is filled in via the [Developer Console](/developer); there is no zip or tarball to assemble for the *manifest* part. UI apps additionally upload a static asset bundle alongside the manifest.

| Where | What you provide |
|---|---|
| **Listing tab** | `slug`, `name`, `category`, `tagline`, `description`, `logo` (uploaded; cropped to 256×256 WebP), optional `screenshots[]` (URLs), `homepage_url`, `support_url`, `privacy_url`, `cover_url` |
| **Versions tab** | A SemVer `version` string, a `changelog`, and a JSON **manifest** that declares `required_executas`, optional Executas, prompt directives, and (for `schema: 2`) the `ui` section |
| **Versions tab → Bundle** *(UI apps only)* | A static SPA bundle (HTML/JS/CSS/...) uploaded with `bundle/init` → per-file PUT → `bundle/finalize`. See [App UI Bundle Pipeline](/developers/apps/app-ui-bundle) |
| **Settings tab** | Submit for review; archive the app |

Each version is an immutable snapshot. To change the bundled Executas, the prompt, or the UI assets, you create a new version (with a strictly greater SemVer), upload its bundle if applicable, and publish it.

<figure class="dh-figure">
<svg viewBox="0 0 720 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The Developer Console organises an app across four tabs — Listing, Versions, Bundle, Settings — each contributing different artefacts to an immutable version snapshot.">
<defs>
<linearGradient id="anFrame" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#1B1D27"/>
<stop offset="1" stop-color="#12141C"/>
</linearGradient>
<linearGradient id="anActive" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#FF9E6C"/>
<stop offset="1" stop-color="#B388FF"/>
</linearGradient>
</defs>
<rect x="20" y="20" width="680" height="250" rx="14" fill="url(#anFrame)" stroke="#FFC8A2" stroke-opacity="0.22"/>
<g>
<circle cx="42" cy="42" r="5" fill="#FF6B6B" opacity="0.7"/>
<circle cx="60" cy="42" r="5" fill="#FFD166" opacity="0.7"/>
<circle cx="78" cy="42" r="5" fill="#7FD49C" opacity="0.7"/>
<text x="100" y="46" font-family="JetBrains Mono, monospace" font-size="11" fill="#A6A8B5">anna.partners / developers / apps / research-buddy</text>
</g>
<line x1="20" y1="64" x2="700" y2="64" stroke="#FFC8A2" stroke-opacity="0.18"/>
<g font-family="Space Grotesk, sans-serif" font-size="11" letter-spacing="0.16em">
<g transform="translate(40 84)">
<rect width="120" height="30" rx="8" fill="#0A0B11" stroke="url(#anActive)" stroke-width="1.4"/>
<text x="60" y="20" text-anchor="middle" fill="#FFC8A2">LISTING</text>
</g>
<g transform="translate(170 84)">
<rect width="120" height="30" rx="8" fill="transparent" stroke="#FFC8A2" stroke-opacity="0.18"/>
<text x="60" y="20" text-anchor="middle" fill="#A6A8B5">VERSIONS</text>
</g>
<g transform="translate(300 84)">
<rect width="120" height="30" rx="8" fill="transparent" stroke="#FFC8A2" stroke-opacity="0.18"/>
<text x="60" y="20" text-anchor="middle" fill="#A6A8B5">BUNDLE</text>
</g>
<g transform="translate(430 84)">
<rect width="120" height="30" rx="8" fill="transparent" stroke="#FFC8A2" stroke-opacity="0.18"/>
<text x="60" y="20" text-anchor="middle" fill="#A6A8B5">SETTINGS</text>
</g>
</g>
<g transform="translate(40 134)" font-family="Inter, sans-serif">
<rect width="200" height="120" rx="10" fill="#0A0B11" stroke="#FF9E6C" stroke-opacity="0.4"/>
<text x="14" y="22" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.2em" fill="#FF9E6C">LISTING</text>
<rect x="14" y="32" width="64" height="64" rx="8" fill="url(#anActive)" opacity="0.7"/>
<text x="86" y="46" font-size="11" fill="#E6E7EE">name · slug</text>
<text x="86" y="64" font-size="11" fill="#A6A8B5">tagline</text>
<text x="86" y="82" font-size="11" fill="#A6A8B5">screenshots</text>
</g>
<g transform="translate(255 134)" font-family="Inter, sans-serif">
<rect width="200" height="120" rx="10" fill="#0A0B11" stroke="#B388FF" stroke-opacity="0.4"/>
<text x="14" y="22" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.2em" fill="#B388FF">VERSIONS</text>
<text x="14" y="44" font-family="JetBrains Mono, monospace" font-size="10" fill="#E6E7EE">v1.0.0  ·  manifest.json</text>
<rect x="14" y="54" width="172" height="6" rx="3" fill="#FFC8A2" fill-opacity="0.18"/>
<rect x="14" y="54" width="64" height="6" rx="3" fill="#B388FF"/>
<text x="14" y="78" font-family="JetBrains Mono, monospace" font-size="10" fill="#A6A8B5">required_executas []</text>
<text x="14" y="92" font-family="JetBrains Mono, monospace" font-size="10" fill="#A6A8B5">system_prompt_addendum</text>
<text x="14" y="106" font-family="JetBrains Mono, monospace" font-size="10" fill="#A6A8B5">ui { schema: 2 }</text>
</g>
<g transform="translate(470 134)" font-family="Inter, sans-serif">
<rect width="100" height="120" rx="10" fill="#0A0B11" stroke="#82B1FF" stroke-opacity="0.4"/>
<text x="12" y="22" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.2em" fill="#82B1FF">BUNDLE</text>
<g font-family="JetBrains Mono, monospace" font-size="10" fill="#A6A8B5">
<text x="12" y="46">index.html</text>
<text x="12" y="62">app.js</text>
<text x="12" y="78">styles.css</text>
<text x="12" y="94">assets/</text>
</g>
</g>
<g transform="translate(585 134)" font-family="Inter, sans-serif">
<rect width="95" height="120" rx="10" fill="#0A0B11" stroke="#FFC8A2" stroke-opacity="0.4"/>
<text x="12" y="22" font-family="Space Grotesk, sans-serif" font-size="9" letter-spacing="0.2em" fill="#FFC8A2">SETTINGS</text>
<g font-family="Inter, sans-serif" font-size="10" fill="#A6A8B5">
<text x="12" y="50">Submit</text>
<text x="12" y="66">Archive</text>
<text x="12" y="82">Transfer</text>
</g>
</g>
</svg>
<figcaption>Four console tabs · one immutable version snapshot</figcaption>
</figure>

## Lifecycle

<figure class="dh-figure">
<svg viewBox="0 0 720 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="App lifecycle: DRAFT submits to PENDING_REVIEW, which is either rejected back to DRAFT or approved; APPROVED publishes a version into PUBLISHED, and PUBLISHED can be archived.">
<defs>
<linearGradient id="lcDraft" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#1B1D27"/>
<stop offset="1" stop-color="#12141C"/>
</linearGradient>
<linearGradient id="lcLive" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#FF9E6C"/>
<stop offset="1" stop-color="#B388FF"/>
</linearGradient>
<marker id="lcArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0 0 L 10 5 L 0 10 z" fill="#FFC8A2" fill-opacity="0.85"/>
</marker>
<marker id="lcArrowAccent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0 0 L 10 5 L 0 10 z" fill="#FF9E6C"/>
</marker>
<marker id="lcArrowDim" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0 0 L 10 5 L 0 10 z" fill="#A6A8B5" fill-opacity="0.7"/>
</marker>
</defs>
<g font-family="Space Grotesk, sans-serif" font-size="11" letter-spacing="0.16em">
<g transform="translate(20 80)">
<rect width="120" height="44" rx="22" fill="url(#lcDraft)" stroke="#FFC8A2" stroke-opacity="0.45"/>
<text x="60" y="27" text-anchor="middle" fill="#E6E7EE">DRAFT</text>
</g>
<g transform="translate(180 80)">
<rect width="160" height="44" rx="22" fill="url(#lcDraft)" stroke="#B388FF" stroke-opacity="0.6"/>
<text x="80" y="27" text-anchor="middle" fill="#B388FF">PENDING_REVIEW</text>
</g>
<g transform="translate(380 80)">
<rect width="130" height="44" rx="22" fill="url(#lcDraft)" stroke="#82B1FF" stroke-opacity="0.6"/>
<text x="65" y="27" text-anchor="middle" fill="#82B1FF">APPROVED</text>
</g>
<g transform="translate(550 80)">
<rect width="140" height="44" rx="22" fill="url(#lcLive)"/>
<text x="70" y="27" text-anchor="middle" fill="#0A0B11" font-weight="700">PUBLISHED</text>
</g>
<g transform="translate(180 200)">
<rect width="120" height="44" rx="22" fill="url(#lcDraft)" stroke="#FF6B6B" stroke-opacity="0.7" stroke-dasharray="4 3"/>
<text x="60" y="27" text-anchor="middle" fill="#FF6B6B">REJECTED</text>
</g>
<g transform="translate(560 200)">
<rect width="120" height="44" rx="22" fill="url(#lcDraft)" stroke="#A6A8B5" stroke-opacity="0.55" stroke-dasharray="4 3"/>
<text x="60" y="27" text-anchor="middle" fill="#A6A8B5">ARCHIVED</text>
</g>
</g>
<g fill="none" stroke-width="1.4">
<line x1="140" y1="102" x2="172" y2="102" stroke="#FFC8A2" stroke-opacity="0.85" marker-end="url(#lcArrow)"/>
<line x1="340" y1="102" x2="372" y2="102" stroke="#FFC8A2" stroke-opacity="0.85" marker-end="url(#lcArrow)"/>
<line x1="510" y1="102" x2="542" y2="102" stroke="#FF9E6C" marker-end="url(#lcArrowAccent)"/>
<path d="M260 124 L 260 200" stroke="#FF6B6B" stroke-opacity="0.7" marker-end="url(#lcArrow)"/>
<path d="M180 222 C 110 222 70 180 70 130" stroke="#A6A8B5" stroke-opacity="0.55" marker-end="url(#lcArrowDim)" stroke-dasharray="4 3"/>
<path d="M620 124 L 620 200" stroke="#A6A8B5" stroke-opacity="0.55" marker-end="url(#lcArrowDim)" stroke-dasharray="4 3"/>
</g>
<g font-family="JetBrains Mono, monospace" font-size="9" fill="#A6A8B5" letter-spacing="0.04em">
<text x="156" y="96" text-anchor="middle">submit</text>
<text x="356" y="96" text-anchor="middle">approve</text>
<text x="526" y="96" text-anchor="middle" fill="#FF9E6C">publish</text>
<text x="276" y="170">reject</text>
<text x="92" y="180" text-anchor="middle">revise</text>
<text x="636" y="170">archive</text>
</g>
</svg>
<figcaption>DRAFT · PENDING_REVIEW · APPROVED · PUBLISHED · REJECTED ↺ · ARCHIVED</figcaption>
</figure>

Only `PUBLISHED` apps are visible in the App Store and installable by new users. Existing installations remain usable after `ARCHIVED`.

## Where to next

- **Quickstart** — [Scaffold + run + validate](/developers/apps/app-quickstart) with the `anna-app` CLI.
- **Manifest** — [App manifest spec](/developers/apps/app-manifest).
- **Bundling** — [Bundling components](/developers/apps/app-bundling).
- **Listing** — [Listing assets](/developers/apps/app-listing).
- **Submitting** — [Publishing an app](/developers/apps/app-publish).
- **Updates** — [Versioning & updates](/developers/apps/app-versioning).
- **App UI** — [Overview](/developers/apps/app-ui-overview), [Manifest `ui` section](/developers/apps/app-ui-manifest), [Bundle pipeline](/developers/apps/app-ui-bundle), [Window lifecycle](/developers/apps/app-ui-windows), [SDK](/developers/apps/app-ui-sdk), [Host API](/developers/apps/app-ui-host-api), [LLM integration](/developers/apps/app-ui-llm).
