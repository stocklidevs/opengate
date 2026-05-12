# Upstream Capabilities

OpenGate `0.6.9` adds a protocol-adaptation layer between Codex and local OpenAI-compatible servers such as vLLM.

This is deliberately model-agnostic. OpenGate does not need to know whether the upstream is Qwen, GLM, Gemma, or another model. It probes the server behavior and adapts the request shape that Codex sends.

## What OpenGate Probes

When `capability_probe = "auto"` and an upstream is configured, startup sends small `/v1/responses` requests to check:

- user-only Responses input
- `developer` role messages
- `system` role messages
- native Responses tool-call history, such as `function_call` and `function_call_output`

The result is cached in `/health` under `upstream_capabilities` and shown in the startup banner.

## How The Proxy Uses It

`--upstream-input-mode auto` now has three model-agnostic reasons to flatten input before forwarding to vLLM:

- Codex history contains native item types that vLLM commonly rejects.
- The capability probe shows the upstream rejects a role in the current input, such as `developer`.
- The user selected `--context-policy spoon`, which intentionally compacts long histories.

If a native request still reaches the upstream and fails with a role/history validation error, OpenGate retries once with flattened input. This catches servers whose behavior differs from the startup probe or whose validation error only appears on a specific request shape.

## Why This Matters

Qwen3.6-27B exposed this with `HTTP 400: Unexpected message role` on the serious benchmark. That is not a tool-call leak and not evidence by itself that the model cannot use tools. It is a protocol mismatch between Codex-style Responses input and the vLLM endpoint.

OpenGate treats that as transport adaptation:

- direct raw benchmarks record it as a protocol incompatibility;
- proxy mode adapts the input before Codex sees a failed turn;
- spoon remains a context-compression policy, not the only way to make vLLM accept the request.

OpenGate still treats command-quality failures separately from protocol adaptation. If a model returns a structured shell call that is syntactically valid but operationally bad, such as an unbounded web fetch, OpenGate `0.6.10` quarantines it into a safe diagnostic shell call. That keeps Codex in the tool-output loop and gives the model a concrete reason to continue with a smaller direct action.

## Config

```toml
[upstream]
model = "auto"
capability_probe = "auto"
capability_probe_timeout = 8
```

Use `capability_probe = "off"` when startup must avoid any generation request, for example when the upstream is warming up or you are testing only capture mode.
