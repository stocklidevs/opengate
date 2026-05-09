# Interactive Codex Through Open Gate

Start Open Gate as a local proxy:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\start_proxy.ps1
```

Use observe mode for raw-baseline runs:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\start_proxy.ps1 -Mode observe
```

Then point Codex at `http://127.0.0.1:8765/v1`.

Suggested config profile:

```toml
[model_providers.open_gate_qwen]
name = "Open Gate Qwen"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"

[profiles.open_gate_qwen]
model_provider = "open_gate_qwen"
model = "Qwen3-Coder-Next"
model_context_window = 32768
model_reasoning_effort = "medium"
model_verbosity = "low"
model_supports_reasoning_summaries = false
```

Run Codex:

```powershell
codex --profile open_gate_qwen -C "C:\Users\example\source\repos\glm-test"
```

Smoke test without editing your config:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_codex_proxy_smoke.ps1
```

Tool-call smoke:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_codex_proxy_smoke.ps1 -Prompt 'Inspect the current directory with shell, then reply with the number of entries you saw.'
```

Live benchmark:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_codex_live_benchmark.ps1 -Mode repair -Runs 3
```

Verified on 2026-05-09:

- Plain assistant-message streaming worked.
- Function-call streaming worked.
- Codex executed a streamed `shell` call, returned tool output through Open Gate, and received a final assistant answer.
- In the tool smoke, Qwen first produced a nested PowerShell command that Codex policy rejected, then recovered with a valid command.
- That nested PowerShell case is now captured as `fixtures\regressions\qwen_nested_powershell_20260509.json` and repaired by the proxy before Codex sees it.

Current proxy behavior:

- Codex can send `stream: true`.
- Open Gate buffers the upstream Qwen response with `stream: false`, normalizes it, then emits valid Responses SSE events to Codex.
- Tool-call streaming includes `response.function_call_arguments.delta` and `response.function_call_arguments.done`.
- Text streaming includes `response.output_text.delta` and `response.output_text.done`.

This is safer than pass-through streaming for now because normalization can inspect the full upstream response before Codex sees it.
