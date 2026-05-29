# Quickstart: DeepSeek-Coder-V2-Lite Adaptation

## 1. Start vLLM

Run on the model host:

```bash
export HF_HOME="$HOME/.cache/huggingface-vllm-optimizer"

$HOME/qwen3next-venv/bin/vllm serve "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct" \
  --host 0.0.0.0 \
  --port 8001 \
  --served-model-name "DeepSeek-Coder-V2-Lite-Instruct" \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.86 \
  --trust-remote-code \
  --moe-backend triton \
  --enable-auto-tool-choice \
  --tool-call-parser deepseek_v3 \
  --chat-template "$HOME/vllm-templates/tool_chat_template_deepseekv3.jinja" \
  --performance-mode interactivity
```

## 2. Verify Identity

```powershell
Invoke-RestMethod http://127.0.0.1:8001/v1/models
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expected:

- `/v1/models` includes `DeepSeek-Coder-V2-Lite-Instruct`.
- OpenGate `/health` reports the same detected model when local `opengate.toml` uses `model = "auto"`.

## 3. Run Direct Baselines

```powershell
uv run python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model DeepSeek-Coder-V2-Lite-Instruct --suite fixtures\benchmarks\codex_shell_smoke.json --runs 3 --label deepseek_v2_lite_direct_smoke_r3 --output runs\deepseek_v2_lite_direct_smoke_r3.json --summary-only

uv run python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model DeepSeek-Coder-V2-Lite-Instruct --suite fixtures\benchmarks\codex_tool_leak_stress.json --runs 3 --label deepseek_v2_lite_direct_leak_stress_r3 --output runs\deepseek_v2_lite_direct_leak_stress_r3.json --summary-only

uv run python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model DeepSeek-Coder-V2-Lite-Instruct --suite fixtures\benchmarks\qwen_serious_tool_stress.json --runs 3 --label deepseek_v2_lite_direct_serious_r3 --output runs\deepseek_v2_lite_direct_serious_r3.json --summary-only
```

If the serious suite times out, rerun once with `--runs 1` and record that as a partial baseline.

## 4. Run OpenGate Proxy Comparisons

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model DeepSeek-Coder-V2-Lite-Instruct -Runs 1 -Label deepseek_v2_lite_open_gate_observe_full_r1 -Output runs\deepseek_v2_lite_open_gate_observe_full_r1.json -Mode observe -ContextPolicy full

powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model DeepSeek-Coder-V2-Lite-Instruct -Runs 3 -Label deepseek_v2_lite_open_gate_repair_full_r3 -Output runs\deepseek_v2_lite_open_gate_repair_full_r3.json -Mode repair -ContextPolicy full

powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model DeepSeek-Coder-V2-Lite-Instruct -Runs 1 -Label deepseek_v2_lite_open_gate_repair_spoon_r1 -Output runs\deepseek_v2_lite_open_gate_repair_spoon_r1.json -Mode repair -ContextPolicy spoon
```

## 5. Summarize Reports

```powershell
uv run python -m open_gate.summarize_report runs\deepseek_v2_lite_direct_smoke_r3.json --pretty
uv run python -m open_gate.summarize_report runs\deepseek_v2_lite_direct_leak_stress_r3.json --pretty
uv run python -m open_gate.summarize_report runs\deepseek_v2_lite_direct_serious_r3.json --pretty
uv run python -m open_gate.summarize_report runs\deepseek_v2_lite_open_gate_repair_full_r3.json --pretty
```

## 6. Classify Failures

For each failure selected for follow-up, record:

- Report path and case ID.
- Capture path, if proxied.
- Failure class: protocol, parser, schema, command-quality, or behavior.
- Whether a model-agnostic repair exists.
- Whether a regression fixture is needed.

## 7. Run Live Smoke After Synthetic Triage

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Model DeepSeek-Coder-V2-Lite-Instruct -Suite fixtures\codex_live\smoke.json -Mode repair -ContextPolicy spoon -Runs 1 -Label deepseek_v2_lite_live_smoke
```

For workspace-write command execution checks, pass the Codex sandbox explicitly:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Model DeepSeek-Coder-V2-Lite-Instruct -Suite fixtures\codex_live\smoke.json -Mode repair -ContextPolicy spoon -Sandbox workspace-write -FailOnPromptSandboxMismatch -Runs 1 -Label deepseek_v2_lite_live_smoke_workspace
```

Summarize the live run:

```powershell
uv run python -m open_gate.codex_report runs\codex-live\<run-id>\captures --codex-dir runs\codex-live\<run-id> --pretty --summary-only
```

Known-good status requires live smoke to reach meaningful model generation without upstream schema errors, Codex-visible leaks, invalid calls, command-quality issues, or policy blocks. A Codex `turn.completed` that only wraps clean upstream-error messages is protocol-blocked, not known-good; a protocol-clean run with poor no-tool/documentation answer text is behavior-limited.
