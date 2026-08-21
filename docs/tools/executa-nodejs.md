---
title: "Quickstart — Node.js"
description: "Ship an Anna Executa plugin in JavaScript in under five minutes."
section: tools
slug: executa-nodejs
order: 3
updated: 2026-04-22
estimated_minutes: 5
---

A Node.js Executa plugin is just a CLI that reads JSON lines and writes JSON lines.

## Prerequisites

- Node.js 18+
- A terminal

## 1. Scaffold the plugin

```bash
mkdir json-tools && cd json-tools
npm init -y
touch plugin.js && chmod +x plugin.js
```

```javascript
#!/usr/bin/env node
"use strict";
const readline = require("readline");

const MANIFEST = {
  name: "json-tools",
  display_name: "JSON Tools",
  version: "0.1.0",
  description: "Format JSON and base64-encode strings.",
  author: "you@example.com",
  tools: [
    {
      name: "format_json",
      description: "Pretty-print a JSON string.",
      parameters: [
        { name: "input", type: "string", description: "Raw JSON", required: true },
        { name: "indent", type: "integer", description: "Indent spaces", required: false, default: 2 },
      ],
    },
    {
      name: "b64",
      description: "Base64-encode a string.",
      parameters: [
        { name: "text", type: "string", description: "Input", required: true },
      ],
    },
  ],
};

function invoke(tool, args) {
  if (tool === "format_json") {
    return { success: true, data: { output: JSON.stringify(JSON.parse(args.input), null, args.indent ?? 2) } };
  }
  if (tool === "b64") {
    return { success: true, data: { output: Buffer.from(args.text, "utf8").toString("base64") } };
  }
  throw Object.assign(new Error(`unknown tool: ${tool}`), { code: -32601 });
}

function send(id, payload) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, ...payload }) + "\n");
}

const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let req;
  try {
    req = JSON.parse(trimmed);
  } catch (e) {
    return send(null, { error: { code: -32700, message: "parse error" } });
  }
  try {
    if (req.method === "describe") return send(req.id, { result: MANIFEST });
    if (req.method === "health") return send(req.id, { result: { status: "ready" } });
    if (req.method === "invoke") {
      const params = req.params || {};
      return send(req.id, { result: invoke(params.tool, params.arguments || {}) });
    }
    return send(req.id, { error: { code: -32601, message: `unknown method: ${req.method}` } });
  } catch (e) {
    send(req.id, { error: { code: e.code ?? -32603, message: e.message } });
  }
});
```

## 2. Smoke-test

```bash
echo '{"jsonrpc":"2.0","method":"describe","id":1}' | node plugin.js
echo '{"jsonrpc":"2.0","method":"invoke","id":2,"params":{"tool":"b64","arguments":{"text":"anna"}}}' | node plugin.js
```

> [!WARNING]
> `console.log` writes to stdout. Anything you `console.log` mixes into protocol output and breaks the plugin. Use `console.error` (stderr) for logs.

## 3. Install on the Agent

Publish the binary entry point with `npm` (`bin` field in `package.json`) and register the plugin with `distribution_type: npm`. For local iteration, build a `.tar.gz` (e.g. `tar czf my-tool.tgz dist/`) and point the Agent at the archive path with `distribution_type: local` — the Agent runs the [full v2 install pipeline](/developers/tools/executa-binary#local-archive-distribution-no-urls-no-upload) and supports multi-file binaries (native addons in `node_modules/`, etc.).

## 4. Build a binary (optional)

Node 20+ ships [single-executable applications](https://nodejs.org/api/single-executable-applications.html) via `--experimental-sea-config`. For multi-platform CI the easiest route remains [`@yao-pkg/pkg`](https://github.com/yao-pkg/pkg):

```bash
npm install -g @yao-pkg/pkg
pkg plugin.js --targets node20-macos-arm64,node20-linux-x64,node20-win-x64 --out-path dist
```

See [Binary Distribution](/developers/tools/executa-binary) for the full matrix and signing guidance.

## 5. Where to next

- **Add credentials** — [Credentials](/developers/tools/executa-credentials).
- **Read the spec** — [Protocol Spec](/developers/tools/executa-protocol).
- **See it in context** — [`examples/nodejs/example_plugin.js`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/nodejs/example_plugin.js).
