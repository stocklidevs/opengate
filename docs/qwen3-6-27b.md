# Qwen3.6-27B Compatibility

This note records the OpenGate validation status for `Qwen/Qwen3.6-27B`: setup, baseline commands, completed results, partial OpenGate repair data, and the reason live optimization is currently parked.

## Status

- Model repository: `Qwen/Qwen3.6-27B`
- Served model name: `Qwen3.6-27B`
- Server: vLLM at `http://127.0.0.1:8001/v1`
- OpenGate target version: `0.6.18`
- OpenGate mode: `repair`
- Upstream input mode: `auto`
- Context policy: `spoon` for live Codex work; `full` and `spoon` both useful for synthetic comparison.
- Validation status: direct basic smoke complete; direct serious exposed a protocol incompatibility; OpenGate repair/spoon partial validation completed before the external command timeout; live optimization is parked because the remaining failures are task-progress/runtime behavior rather than clean proxy repair.
- Validation date: `2026-05-11` UTC, `2026-05-10` America/New_York.

## vLLM Setup

```bash
source ~/qwen3next-venv/bin/activate

vllm serve "Qwen/Qwen3.6-27B" \
  --host 0.0.0.0 \
  --port 8001 \
  --served-model-name "Qwen3.6-27B" \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85 \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
```

The two tool-related flags are the important part for Codex-style use: `--enable-auto-tool-choice` and `--tool-call-parser qwen3_coder`. The reasoning parser should remain `qwen3` so vLLM separates reasoning text from normal assistant output where the model supports it.

## OpenGate Setup

Use a local ignored `opengate.toml`:

```toml
[server]
host = "127.0.0.1"
port = 8765
capture_dir = "captures"

[upstream]
scheme = "http"
host = "127.0.0.1"
port = 8001
path = "/v1"
api_key = "sk-no-key-required"
timeout = 420
model = "auto"
capability_probe = "auto"
capability_probe_timeout = 8

[proxy]
normalization_mode = "repair"
upstream_input_mode = "auto"
context_policy = "spoon"
context_max_chars = 60000
context_recent_items = 12
instruction_policy = "auto"
tool_schema_policy = "auto"
stream_heartbeat_seconds = 2
upstream_max_output_tokens = 4096
```

Then launch:

```powershell
opengate
```

Expected startup behavior:

- The banner reports the current OpenGate version.
- The listener is `http://127.0.0.1:8765/v1`.
- The upstream base URL is `http://127.0.0.1:8001/v1`.
- The model source is upstream autodetection.
- The capability summary reports whether `developer`, `system`, and native tool-history inputs are accepted by the upstream server.
- The upstream output-token cap is `4096` unless overridden; use `0` only for controlled benchmarks where timeouts are acceptable.
- `/health` reports `model` as `Qwen3.6-27B` once vLLM is live.

Codex can keep a stable model name in its OpenGate profile because OpenGate rewrites the upstream `model` field to the detected vLLM model. For example:

```toml
[model_providers.open_gate]
name = "OpenGate"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"

[profiles.open_gate]
model_provider = "open_gate"
model = "open-gate-auto"
model_context_window = 65536
model_supports_reasoning_summaries = false
```

## Benchmark Plan

First confirm the endpoint identity. The first live check reported:

- `id`: `Qwen3.6-27B`
- `root`: `Qwen/Qwen3.6-27B`
- `max_model_len`: `65536`

```powershell
Invoke-RestMethod http://127.0.0.1:8001/v1/models
Invoke-RestMethod http://127.0.0.1:8765/health
```

Run a direct raw smoke baseline against vLLM:

```powershell
python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Qwen3.6-27B --suite fixtures\benchmarks\codex_shell_smoke.json --runs 3 --label qwen36_27b_direct_smoke_r3 --output runs\qwen36_27b_direct_smoke_r3.json --summary-only
```

Run the direct serious baseline:

```powershell
python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Qwen3.6-27B --suite fixtures\benchmarks\qwen_serious_tool_stress.json --runs 3 --label qwen36_27b_direct_serious_r3 --output runs\qwen36_27b_direct_serious_r3.json --summary-only
```

Run the same serious suite through OpenGate repair mode with full context:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model Qwen3.6-27B -Runs 3 -Label qwen36_27b_open_gate_repair_full_r3 -Output runs\qwen36_27b_open_gate_repair_full_r3.json -Mode repair -ContextPolicy full
```

Run the serious suite through OpenGate repair mode with spoon context:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_proxy_benchmark.ps1 -Model Qwen3.6-27B -Runs 3 -Label qwen36_27b_open_gate_repair_spoon_r3 -Output runs\qwen36_27b_open_gate_repair_spoon_r3.json -Mode repair -ContextPolicy spoon
```

Run a live Codex software-build benchmark in a disposable writable folder:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Model Qwen3.6-27B -Suite fixtures\codex_live\software_build.json -CodexCwd C:\Users\example\source\repos\qwen36-live-software -Mode repair -ContextPolicy spoon -Sandbox workspace-write -FailOnPromptSandboxMismatch -Runs 1 -Label qwen36_27b_software_build
```

## Result Log

| Check | Expected | Result |
| --- | --- | --- |
| `/v1/models` | `id = Qwen3.6-27B` | pass; `root = Qwen/Qwen3.6-27B`, `max_model_len = 65536` |
| OpenGate `/health` | `model = Qwen3.6-27B`, autodetected | pending |
| Direct smoke baseline | record strict success and leakage rates | pass; `9/9` strict successes, zero leaks, zero invalid calls, zero HTTP errors |
| Direct serious baseline | record raw failure/leakage behavior | protocol incompatibility; `20/20` HTTP 400 errors with `Unexpected message role` before generation |
| OpenGate repair/full | zero returned text/reasoning leaks | pending |
| OpenGate repair/spoon | zero returned leaks, no Codex-visible command-quality issues | partial; `17/20` captures completed before external timeout, `14/17` derived strict successes, zero returned leaks/invalid calls/command-quality issues |
| Live Codex software build | artifact created, no leaked tool syntax in console | pending |

Direct smoke report:

- `runs\qwen36_27b_direct_smoke_r3.json`
- Suite: `fixtures\benchmarks\codex_shell_smoke.json`
- Runs: `3`
- Total cases: `9`

Direct serious report:

- `runs\qwen36_27b_direct_serious_r1.json`
- Suite: `fixtures\benchmarks\qwen_serious_tool_stress.json`
- Runs: `1`
- Result: `0/20` strict successes due to `20/20` protocol HTTP errors.
- Error: `HTTP 400: Unexpected message role.`

OpenGate partial spoon captures:

- `runs\qwen36_27b_open_gate_repair_spoon_r1\captures`
- Captures completed: `17`
- Upstream input mode: `flattened`
- Upstream HTTP errors: `0`
- Returned text leaks: `0`
- Returned invalid tool calls: `0`
- Returned command-quality issues: `0`
- Derived strict successes on completed captures: `14/17`

Interpretation: the direct serious failure is not yet evidence that Qwen3.6 cannot call tools. It is evidence that this vLLM Responses endpoint rejects Codex-like `developer` messages. OpenGate `0.6.9` addresses this class architecturally by probing protocol support, flattening unsupported roles independently of spoon compression, and retrying flattened input after native role/history validation errors.

## 2026-05-11 Live Reference-Site Fetch

A live Codex run against Qwen3.6 generated a structured shell call to inspect `https://styles.refero.design/` by fetching page content with `Invoke-WebRequest`. OpenGate repaired the shell argument shape, then blocked the call as `unbounded_web_fetch`. Before `0.6.10`, that suppression could leave Codex with only assistant prose when the model also emitted a visible message. OpenGate `0.6.10` changes this into a diagnostic shell quarantine so Codex receives explicit tool feedback and can continue from the prompt instead of appearing stuck.

## 2026-05-11 Hosted Web Search Routing

Codex advertises live web search as a hosted Responses tool (`{"type":"web_search"}`), but Codex CLI does not execute a returned local `function_call` named `web_search`. A live smoke run reproduced that as `unsupported call: web_search`. OpenGate `0.6.11` now treats model-returned `web_search` as a hosted-tool alias and converts URL lookups into bounded `shell` metadata fetches. If the shell cannot reach the site, repeated non-artifact URL attempts end with a terminal assistant message instead of looping through diagnostic shell calls.

## 2026-05-11 Executable-Only Shell Calls

A later live run showed Qwen3.6 emitting a `shell` call whose `command` was only `powershell.exe`, while useful-looking content leaked into approval metadata such as `prefix_rule`, `sandbox_permissions`, and `justification`. OpenGate `0.6.12` treats that as `executable_only_command`, quarantines it into a safe generic diagnostic shell result, and strips approval metadata from the diagnostic.

## 2026-05-11 Plan Detour And Timeout

Another live run got valid Refero metadata, blocked repeated web inspection correctly, then Qwen3.6 spent a full turn on `update_plan` and timed out on the following artifact-generation turn. OpenGate temporarily experimented with blocking those plan detours, but that behavior is task supervision rather than proxy repair and is no longer part of the default path.

## 2026-05-12 Requested-File Artifact Pressure

The initial artifact-pressure fix was intentionally validated on the Refero `index.html` task, then generalized to other files such as `main.cpp`. That generalization still crossed the architectural line: it inferred task progress from prompts and tool outputs. OpenGate `0.6.17` removes that default behavior.

## 2026-05-12 Failed Write State

The latest Qwen3.6 Refero run exposed a malformed file-write shape: `Set-Content ... -Value @```ENDOFHTML``@`, which PowerShell rejected with `ParserError: Unrecognized token`. OpenGate keeps the generic part of that fix, quarantining malformed here-string placeholders before Codex executes them. It no longer tracks whether the artifact is pending or completed.

## 2026-05-12 Scope Reset

The Qwen3.6 live Refero runs proved that the remaining problems are broader than malformed tool calls: long stalls, planning loops, wrong tool choice, and task-progress drift. OpenGate `0.6.17` removes the default artifact-pressure/task-steering path added while chasing those runs. The proxy keeps generic protocol adaptation, tool-call repair, command-quality quarantine, bounded web metadata routing, captures, and benchmarks. Qwen3.6 should remain a benchmark target rather than an optimization target until a failure clearly belongs to the proxy layer.

## Acceptance Criteria

- Direct vLLM baselines are recorded before OpenGate claims are made.
- OpenGate `repair` returns zero assistant-text or reasoning tool-call leaks.
- OpenGate returns zero invalid tool calls and zero error-level command-quality issues to Codex.
- Live Codex run creates the requested artifact in the target working directory.
- Any architecture changes come from a captured repeatable failure shape, not a one-off patch.

## Notes

- Page or app quality is primarily model-and-prompt dependent. OpenGate's responsibility is transport, context shaping, tool discipline, repair, and measurable failure reduction.
- If direct vLLM fails with `model does not exist`, check the exact `--served-model-name` and `/v1/models` output first.
- If Codex displays leaked `<tool_call>` or `recipient_name=functions.*` text, save the matching OpenGate capture and add it as a regression fixture before changing repair behavior.
