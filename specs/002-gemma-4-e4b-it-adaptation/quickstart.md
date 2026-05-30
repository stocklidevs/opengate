# Quickstart: Gemma-4-E4B-IT Adaptation

## 1. Start vLLM

```bash
export HF_HOME="$HOME/.cache/huggingface-vllm-optimizer"

$HOME/qwen3next-venv/bin/vllm serve "google/gemma-4-E4B-it" \
  --host 0.0.0.0 \
  --port 8001 \
  --served-model-name "Gemma-4-E4B-IT" \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.84 \
  --enable-auto-tool-choice \
  --tool-call-parser gemma4 \
  --chat-template "$HOME/vllm-templates/tool_chat_template_gemma4.jinja" \
  --performance-mode interactivity
```

## 2. Confirm Endpoint Identity

```powershell
Invoke-RestMethod http://127.0.0.1:8001/v1/models
```

Start OpenGate with local ignored config using `model = "auto"`, then check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expected:

- `/v1/models` includes `Gemma-4-E4B-IT`.
- `/health` reports `model = Gemma-4-E4B-IT`.
- Capability probing records whether the upstream accepts developer/system roles and native tool-history input.

## 3. Run Direct Baselines

```powershell
uv run python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Gemma-4-E4B-IT --suite fixtures\benchmarks\codex_shell_smoke.json --runs 3 --label gemma4_e4b_it_direct_smoke_r3 --output runs\gemma4_e4b_it_direct_smoke_r3.json --summary-only

uv run python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Gemma-4-E4B-IT --suite fixtures\benchmarks\codex_tool_leak_stress.json --runs 3 --label gemma4_e4b_it_direct_leak_stress_r3 --output runs\gemma4_e4b_it_direct_leak_stress_r3.json --summary-only

uv run python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Gemma-4-E4B-IT --suite fixtures\benchmarks\qwen_serious_tool_stress.json --runs 3 --label gemma4_e4b_it_direct_serious_r3 --output runs\gemma4_e4b_it_direct_serious_r3.json --summary-only
```

If the serious suite times out, rerun once with `--runs 1` and record that as a partial baseline.

## 4. Run OpenGate Comparisons

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model Gemma-4-E4B-IT -Runs 1 -Label gemma4_e4b_it_open_gate_observe_full_r1 -Output runs\gemma4_e4b_it_open_gate_observe_full_r1.json -Mode observe -ContextPolicy full

powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model Gemma-4-E4B-IT -Runs 3 -Label gemma4_e4b_it_open_gate_repair_full_r3 -Output runs\gemma4_e4b_it_open_gate_repair_full_r3.json -Mode repair -ContextPolicy full

powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model Gemma-4-E4B-IT -Runs 1 -Label gemma4_e4b_it_open_gate_repair_spoon_r1 -Output runs\gemma4_e4b_it_open_gate_repair_spoon_r1.json -Mode repair -ContextPolicy spoon
```

## 5. Summarize Reports

```powershell
uv run python -m open_gate.summarize_report runs\gemma4_e4b_it_direct_smoke_r3.json --pretty
uv run python -m open_gate.summarize_report runs\gemma4_e4b_it_direct_leak_stress_r3.json --pretty
uv run python -m open_gate.summarize_report runs\gemma4_e4b_it_direct_serious_r3.json --pretty
uv run python -m open_gate.summarize_report runs\gemma4_e4b_it_open_gate_repair_full_r3.json --pretty
```

Record:

- Strict success count and rate.
- Returned text and reasoning leaks.
- Invalid structured calls.
- Command-quality issues.
- Missed expected tools.
- HTTP/protocol incompatibilities.

## 6. Inspect Captures Before Repairs

For each failed or repaired case selected for follow-up, record:

- Suite and case id.
- Capture path.
- Upstream shape.
- Codex-visible impact.
- Failure class: protocol, parser, schema, command-quality, or behavior.
- Whether a model-agnostic repair exists.
- Whether a regression fixture is needed.

## 7. Run Live Smoke After Synthetic Triage

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Model Gemma-4-E4B-IT -Suite fixtures\codex_live\smoke.json -Mode repair -ContextPolicy spoon -Sandbox workspace-write -FailOnPromptSandboxMismatch -Runs 1 -Label gemma4_e4b_it_live_smoke_workspace
```

Summarize the live run:

```powershell
uv run python -m open_gate.codex_report runs\codex-live\<run-id>\captures --codex-dir runs\codex-live\<run-id> --pretty --summary-only
```

Known-good status requires live smoke to reach meaningful model generation without upstream schema errors, Codex-visible leaks, invalid calls, command-quality issues, or policy blocks. A protocol-clean run with poor no-tool/documentation answer text is behavior-limited, not known-good.
