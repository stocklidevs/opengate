# Interactive Codex Through Open Gate

Start Open Gate as a local proxy:

```powershell
opengate
```

`opengate` loads `opengate.toml` from the current directory when present, autodetects the upstream model from `GET /v1/models` when `model = "auto"`, and prints the active settings banner at launch.

Use observe mode for raw-baseline runs:

```powershell
opengate --normalization-mode observe --capture-dir C:\Users\example\source\repos\open-gate\runs\manual-glm47-observe
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

[model_providers.open_gate_glm]
name = "Open Gate GLM"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"

[profiles.open_gate_glm]
model_provider = "open_gate_glm"
model = "GLM-4.7-Flash"
model_context_window = 131072
model_reasoning_effort = "medium"
model_verbosity = "low"
model_supports_reasoning_summaries = false

[profiles.open_gate_glm.windows]
sandbox = "elevated"
```

Run Codex:

```powershell
codex --profile open_gate_qwen -C "C:\Users\example\source\repos\glm-test"
```

For GLM:

```powershell
codex --profile open_gate_glm -C "C:\Users\example\source\repos\glm-test"
```

For non-interactive write-heavy tests, first verify what Codex will show the model:

```powershell
codex -C C:\Users\example\source\repos\glm-test -s workspace-write -a never debug prompt-input "test"
```

If that prompt says `sandbox_mode` is `read-only`, the run is not a valid file-generation benchmark. Use an interactive session with approvals, or run a disposable-folder test with a prompt-visible writable sandbox after making an explicit risk decision.

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
- Open Gate sends SSE headers immediately, emits Responses `response.in_progress` heartbeat events while Qwen/GLM/vLLM is generating, then emits valid Responses SSE events to Codex.
- Open Gate still buffers the upstream Qwen response with `stream: false` so normalization can inspect the full response before Codex sees it.
- Tool-call streaming includes `response.function_call_arguments.delta` and `response.function_call_arguments.done`.
- Text streaming includes `response.output_text.delta` and `response.output_text.done`.

This is safer than pass-through streaming for now because normalization can inspect the full upstream response before Codex sees it.
