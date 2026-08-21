---
title: "Quickstart — Go"
description: "Ship a single-binary Anna Executa plugin in Go."
section: tools
slug: executa-go
order: 4
updated: 2026-04-22
estimated_minutes: 6
---

Go is the language of choice when you want **one statically linked binary per platform**. No interpreter, no runtime — just `chmod +x` and run.

## Prerequisites

- Go 1.21+
- A terminal

## 1. Scaffold

```bash
mkdir sysinfo-tool && cd sysinfo-tool
go mod init sysinfo-tool
touch main.go
```

```go
package main

import (
    "bufio"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "os"
    "runtime"
)

type Request struct {
    Jsonrpc string         `json:"jsonrpc"`
    Method  string         `json:"method"`
    ID      any            `json:"id"`
    Params  map[string]any `json:"params,omitempty"`
}

type Response struct {
    Jsonrpc string `json:"jsonrpc"`
    ID      any    `json:"id"`
    Result  any    `json:"result,omitempty"`
    Error   *Err   `json:"error,omitempty"`
}

type Err struct {
    Code    int    `json:"code"`
    Message string `json:"message"`
}

var manifest = map[string]any{
    "name":         "sysinfo",
    "display_name": "System Info",
    "version":      "0.1.0",
    "description":  "Report OS info or hash a string.",
    "tools": []map[string]any{
        {"name": "os_info", "description": "Return host OS and arch.", "parameters": []map[string]any{}},
        {"name": "sha256", "description": "Hash a string with SHA-256.", "parameters": []map[string]any{
            {"name": "text", "type": "string", "description": "Input", "required": true},
        }},
    },
}

func invoke(tool string, args map[string]any) (any, *Err) {
    switch tool {
    case "os_info":
        return map[string]any{
            "success": true,
            "data":    map[string]string{"os": runtime.GOOS, "arch": runtime.GOARCH},
        }, nil
    case "sha256":
        text, _ := args["text"].(string)
        sum := sha256.Sum256([]byte(text))
        return map[string]any{
            "success": true,
            "data":    map[string]string{"output": hex.EncodeToString(sum[:])},
        }, nil
    }
    return nil, &Err{Code: -32601, Message: fmt.Sprintf("unknown tool: %s", tool)}
}

func main() {
    enc := json.NewEncoder(os.Stdout)
    s := bufio.NewScanner(os.Stdin)
    s.Buffer(make([]byte, 0, 1<<20), 1<<22)
    for s.Scan() {
        line := s.Bytes()
        if len(line) == 0 {
            continue
        }
        var req Request
        if err := json.Unmarshal(line, &req); err != nil {
            _ = enc.Encode(Response{Jsonrpc: "2.0", Error: &Err{Code: -32700, Message: err.Error()}})
            continue
        }
        resp := Response{Jsonrpc: "2.0", ID: req.ID}
        switch req.Method {
        case "describe":
            resp.Result = manifest
        case "health":
            resp.Result = map[string]string{"status": "ready"}
        case "invoke":
            tool, _ := req.Params["tool"].(string)
            args, _ := req.Params["arguments"].(map[string]any)
            result, errOut := invoke(tool, args)
            if errOut != nil {
                resp.Error = errOut
            } else {
                resp.Result = result
            }
        default:
            resp.Error = &Err{Code: -32601, Message: "unknown method: " + req.Method}
        }
        _ = enc.Encode(resp)
    }
}
```

## 2. Smoke-test

```bash
echo '{"jsonrpc":"2.0","method":"describe","id":1}' | go run main.go
echo '{"jsonrpc":"2.0","method":"invoke","id":2,"params":{"tool":"os_info","arguments":{}}}' | go run main.go
```

A successful invoke returns `{"result": {"success": true, "data": {...}}}` — the wrapper the Agent decodes into `InvokeResult`.

## 3. Build native binaries

```bash
GOOS=darwin  GOARCH=arm64 go build -ldflags "-s -w" -o dist/sysinfo-darwin-arm64  main.go
GOOS=darwin  GOARCH=amd64 go build -ldflags "-s -w" -o dist/sysinfo-darwin-x86_64 main.go
GOOS=linux   GOARCH=amd64 go build -ldflags "-s -w" -o dist/sysinfo-linux-x86_64  main.go
GOOS=linux   GOARCH=arm64 go build -ldflags "-s -w" -o dist/sysinfo-linux-aarch64 main.go
GOOS=windows GOARCH=amd64 go build -ldflags "-s -w" -o dist/sysinfo-windows-x86_64.exe main.go
```

File names follow the [platform key convention](/developers/tools/executa-binary#platform-keys) so the Agent's binary distribution can pick the right asset automatically. Full multi-platform Makefile in [`examples/go/Makefile`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/go/Makefile).

> [!TIP]
> `-ldflags "-s -w"` strips the symbol table and DWARF debug info; expect ~30 % smaller binaries.

## 4. Where to next

- **Add credentials** — [Credentials](/developers/tools/executa-credentials).
- **Cross-platform binaries** — [Binary Distribution](/developers/tools/executa-binary).
- **See it in context** — [`examples/go/main.go`](https://github.com/whtcjdtc2007/anna-executa-examples/blob/main/examples/go/main.go).
