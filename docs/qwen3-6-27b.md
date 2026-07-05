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
- Validation status: direct basic smoke complete; direct serious exposed a protocol incompatibility; OpenGate repair/spoon partial validation completed before the external command timeout; live optimization on the vLLM/OpenGate path is parked because the remaining failures are task-progress/runtime behavior rather than clean proxy repair.
- Additional CSVQL status: `Qwen3.6-27B-Q8_0` through llama.cpp and Qwen Code `0.19.5` passed the full CSVQL challenge on 2026-07-05.
- Validation dates: vLLM/OpenGate path `2026-05-11` UTC, `2026-05-10` America/New_York; Q8_0/Qwen Code CSVQL path `2026-07-05`.

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

## llama.cpp Q8_0 Qwen Code Setup

The first successful local CSVQL run for this model used ggml-org's Q8_0 GGUF with llama.cpp rather than vLLM/OpenGate:

```bash
/home/altsens/llama.cpp/build/bin/llama-server \
  -m /home/altsens/models/ggml-org/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q8_0.gguf \
  --host 0.0.0.0 \
  --port 8002 \
  --alias Qwen3.6-27B-Q8_0 \
  -c 262144 \
  -ngl all \
  -fa on \
  --fit off \
  --reasoning auto \
  --reasoning-format deepseek \
  --jinja \
  --no-webui
```

Observed serving facts:

- Model root: `ggml-org/Qwen3.6-27B-GGUF`
- File: `Qwen3.6-27B-Q8_0.gguf`
- Quantization: Q8_0
- File size: about 28.6 GB
- Context: `262144`
- Served alias: `Qwen3.6-27B-Q8_0`
- Endpoint: `http://<gx10-host>:8002/v1`
- GPU placement: all 65 layers on GPU

Qwen Code CLI version:

```text
0.19.5
```

Workspace Qwen Code model settings:

```json
{
  "env": {
    "OPENAI_API_KEY": "sk-local-qwen-q8",
    "OPENAI_BASE_URL": "http://<gx10-host>:8002/v1",
    "OPENAI_MODEL": "Qwen3.6-27B-Q8_0"
  },
  "modelProviders": {
    "openai": {
      "protocol": "openai",
      "models": [
        {
          "id": "Qwen3.6-27B-Q8_0",
          "name": "Qwen3.6-27B Q8_0 GGUF (GX10 llama.cpp 262k)",
          "envKey": "OPENAI_API_KEY",
          "baseUrl": "http://<gx10-host>:8002/v1",
          "generationConfig": {
            "timeout": 1800000,
            "maxRetries": 0,
            "contextWindowSize": 262144,
            "samplingParams": {
              "temperature": 0.2,
              "max_tokens": 8192
            }
          }
        }
      ]
    }
  }
}
```

Run the CSVQL prompt from an isolated workspace. The important harness detail is that the prompt is piped through stdin and `--prompt ""` is still provided, so Qwen Code consumes the full multi-line prompt rather than just the first line:

```powershell
$Prompt = (Get-Content -LiteralPath fixtures\codex_live\csvql_only.json -Raw | ConvertFrom-Json).cases[0].prompt
$Prompt | qwen `
  --auth-type openai `
  --model Qwen3.6-27B-Q8_0 `
  --openai-base-url http://<gx10-host>:8002/v1 `
  --openai-api-key sk-local-qwen-q8 `
  --approval-mode yolo `
  --max-wall-time 8h `
  --max-session-turns 300 `
  --openai-logging `
  --chat-recording true `
  --input-format text `
  --prompt ""
```

Do not use a 120-minute wall-clock guard for this cell. The recorded run hit that guard while still making progress, then completed after resuming the same Qwen Code chat with an 8-hour guard.

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

## 2026-07-05 Q8_0 Qwen Code CSVQL Result

Run folder:

```text
runs\qwen-code-live\20260705-1002-qwen36_27b_q8_0_262k_qwencode_csvql_fullprompt_r3
```

This was the valid full-prompt run. Earlier local attempts were discarded as harness-invalid because one delivered only the first prompt line and another stalled after a partial stdin launch. The `r3` run used the exact prompt from `fixtures\codex_live\csvql_only.json`.

Summary:

| Metric | Value |
| --- | ---: |
| Harness | Qwen Code CLI `0.19.5` |
| Server | llama.cpp GGUF Q8_0 |
| Context window | `262144` |
| Initial wall guard | `120m`, hit before completion |
| Resume wall guard | `8h` |
| Total observed run span | about 2h41m |
| Qwen Code tool calls | 79 |
| Files landed | 12 source/test/fixture files |
| Final verifier | pass |

Independent verification after Qwen Code exited:

```text
python -m compileall -q csvql run_csvql.py
python -m pytest -q
43 passed in 0.24s
```

Manual CLI outputs matched the challenge contract:

```text
SELECT name, city FROM customers WHERE city = 'NYC'
name,city
Alice,NYC
Carol,NYC

SELECT name FROM customers ORDER BY name DESC LIMIT 2
name
Dave
Carol

SELECT c.name, o.amount FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.category = 'books' ORDER BY o.amount
c.name,o.amount
Carol,15.0
Carol,25.0

SELECT c.city, COUNT(*) AS n, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.city ORDER BY c.city
c.city,n,total
LA,2,175
NYC,4,115
SF,1,200
```

Audit notes:

- Qwen Code added a local `conftest.py` to route pytest temp directories into the workspace because the default Windows temp path had permission problems. This is not part of the CSVQL app logic, but it is part of the run evidence.
- Qwen Code changed one generated test expectation for grouped `COUNT(column)` from `2` to `3`. The edit appears correct because the fixture has three grouped cities, but it is still a self-test correction and should be called out in comparisons.
- Before settling on the local pytest workaround, Qwen Code attempted to remove or take ownership of the stale Windows temp path and was denied. Future challenge harnesses should avoid giving local agents a reason to repair machine-level temp state.

Interpretation: the Q8_0/Qwen Code path changes the story for Qwen3.6. The earlier vLLM/OpenGate path remains parked for proxy optimization because its failures were not clean OpenGate repair targets. But the model itself, in this GGUF/Qwen Code serving combination with a 262k context budget and enough wall-clock time, did complete the CSVQL application and passed independent verification.

## 2026-07-05 Q8_0 OpenGate/Codex Follow-Up

The same Q8_0 llama.cpp endpoint was tested through OpenGate/Codex to isolate the harness effect from the model and quantization effect.

Runs:

| Run | Variant | Result |
| --- | --- | --- |
| `20260705-144755-qwen36_27b_q8_0_262k_ogcodex_csvql_writefile-repair` | native Responses input, write-file config active | Failed immediately with llama.cpp/Qwen Jinja error: `System message must be at the beginning` |
| `20260705-145052-qwen36_27b_q8_0_262k_ogcodex_csvql_writefile_flatten-repair` | forced flattened input, write-file injection active | Entered a repeat loop rewriting `csvql/__init__.py` |
| `20260705-151104-qwen36_27b_q8_0_262k_ogcodex_csvql_flatten_no_writefile-repair` | forced flattened input, write-file explicitly disabled | Aborted too early while remote decoding was still active; treated as inconclusive |
| `20260705-153826-qwen36_27b_q8_0_262k_ogcodex_csvql_flatten_no_writefile_r2-repair` | same clean setup, long guard | Completed CSVQL in `3192.153` seconds with 39 proxy exchanges and 12 non-cache files |

Independent checks on the completed r2 workspace passed: compileall succeeded with `PYTHONPYCACHEPREFIX` redirected around a local Windows cache ACL issue, `python -B -m pytest -q` returned `30 passed in 0.19s`, the four required manual queries returned the expected rows, and `python run_csvql.py ...` matched the `python -m csvql` NYC output. The run produced the package, parser, engine, CLI, `run_csvql.py`, fixtures, README, and `tests/test_csvql.py`.

Harness notes:

- The benchmark runner now exposes `-UpstreamInputMode` so the forced flattened path is reproducible.
- The benchmark runner and OpenGate CLI now expose `-DisableWriteFileTool` / `--no-write-file-tool`, because `opengate.toml` can otherwise enable write-file injection even when the run command omits `-WriteFileTool`.
- The OpenGate/Codex result reproduced the Qwen Code pass once native Qwen template issues and write-file transcript confusion were removed. This weakens the "Qwen Code only" interpretation and strengthens the Q8_0 plus large-context plus patience hypothesis.

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
