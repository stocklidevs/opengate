# Live Codex Benchmark

The synthetic benchmark calls `/v1/responses` directly. The live Codex benchmark runs `codex exec` against Open Gate so we can measure the whole loop:

- model response shape
- Open Gate normalization
- Codex streaming acceptance
- tool execution
- policy rejection recovery
- final assistant answer

## Modes

Open Gate has two proxy modes:

- `repair`: return the normalized response to Codex. This is the user-facing mode.
- `observe`: compute and record the same normalization report, but return the raw upstream response. This is useful for baseline comparisons.

Open Gate also has an upstream input mode. The default, `auto`, forwards simple user turns natively and flattens richer Codex history before sending it to vLLM. This avoids vLLM 400 validation errors on assistant history, `function_call`, or `function_call_output` input items.

For streamed Codex requests, Open Gate sends SSE headers immediately and emits Responses `response.in_progress` heartbeat events while it waits for the buffered upstream response. Tune this with `--stream-heartbeat-seconds`; the app default is `2.0`.

Start the proxy manually:

```powershell
opengate
```

Run the live suite:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Mode repair -Runs 3
```

Run the software-build stress suite:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 `
  -Model GLM-4.7-Flash `
  -Suite fixtures\codex_live\software_build.json `
  -CodexCwd C:\Users\example\source\repos\glm-live-software `
  -Mode repair `
  -ContextPolicy spoon `
  -Sandbox workspace-write `
  -FailOnPromptSandboxMismatch `
  -Runs 1 `
  -Label glm47_software_build
```

For constrained-context model probes, add `-UpstreamMaxOutputTokens <n>`. The live harness forwards this to OpenGate as `--upstream-max-output-tokens` and records it in `manifest.json` as `upstream_max_output_tokens`. This is useful when Codex's default output reservation would consume too much of a 64k window; it is a measurement knob, not a repair.

Run a baseline comparison:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Mode observe -Runs 3 -Label codex_live_observe
```

Each run writes a folder under `runs\codex-live\` with:

- `manifest.json`: suite, mode, timing, prompt metadata.
- `codex-*.jsonl`: combined `codex exec --json` output.
- `last-*.txt`: Codex's final assistant message for each case.
- `captures\`: Open Gate proxy captures.
- `report.json`: summarized metrics from `open_gate.codex_report`.

You can regenerate the report:

```powershell
python -m open_gate.codex_report runs\codex-live\<run-id>\captures --codex-dir runs\codex-live\<run-id> --pretty --summary-only
```

## Key Metrics

- `codex_turn_completion_rate`: how often Codex reached `turn.completed`.
- `codex_runs_with_policy_blocks`: how often Codex reported a policy rejection.
- `upstream_command_quality_issues`: raw model command-shape problems.
- `returned_command_quality_issues`: command-shape problems after Open Gate mode is applied.
- `structured_argument_repairs`: repairs Open Gate applied or would apply.
- `channel_delimiter_text_repairs`: assistant final-answer prefaces removed by keeping the suffix after a final non-empty `<channel|>` marker.
- `average_proxy_duration_seconds` and `max_proxy_duration_seconds`: upstream wait plus normalization time from proxy captures.
- `stream_heartbeats`: Responses heartbeat events sent while Codex waited for buffered upstream responses.
- `returned_clean_capture_rate`: captures with no returned leaks, invalid calls, command-quality issues, or policy block markers.

## Sandbox Preflight

The live harness records `prompt_sandbox` for each case by asking `codex debug prompt-input` what sandbox text Codex will show the model. This matters because a software-build benchmark is invalid if the prompt tells the model that file creation is forbidden.

Use `-FailOnPromptSandboxMismatch` for write-heavy suites. The harness will skip the case with exit code `125` if the requested sandbox and model-visible sandbox differ. On this nested Windows Codex session, `-Sandbox workspace-write` rendered as `read-only`, so write-heavy GLM runs are invalid unless the prompt-visible sandbox is fixed. `danger-full-access` renders correctly but should only be used in a disposable folder after an explicit risk decision.

## 2026-05-10 GLM Cosmic Page Incident

Run folder: `runs\manual-glm47-live3`

The run did not produce a file: `glm-test\index.html` stayed at zero bytes. Open Gate normalized the returned tool calls with zero returned text leaks and zero returned command-quality issues, but the live loop failed for two infrastructure reasons:

- Codex's model-visible prompt said `sandbox_mode` was `read-only` when launched with `-s workspace-write -a never`, so shell/network actions were policy-rejected before execution.
- One upstream GLM response took just over five minutes; comment-only keepalives were not enough to prevent Codex from retrying the stream before the file-write call could be consumed.

Open Gate `0.6.6` changes the stream keepalive path to real Responses heartbeat events and repairs the GLM bare here-string file-write shape observed in this run. The remaining live validation should use a disposable folder with a prompt-visible writable sandbox.

## Software-Build Suite

`fixtures\codex_live\software_build.json` contains three higher-value live cases:

- `expense_cli`: build and test a no-dependency CSV expense analyzer.
- `incident_log_triage`: build and test a no-dependency log triage CLI with `--since` and `--json`.
- `habit_tracker_web`: build and verify a single-file localStorage habit tracker.

The suite is intentionally write-heavy. It is designed to test whether the model can make progress through Codex's real tool loop, not just whether Open Gate can hide leaked tool syntax.

## CSVQL Suite

`fixtures\codex_live\csvql_only.json` contains one harder single-case build: a zero-dependency Python SQL query engine over CSV files. It requires a package, CLI entry point, sample CSVs, README, pytest coverage, and manual query checks for filtering, ordering, joins, grouping, aggregation, aliases, and HAVING.

The point is to make fabrication and partial file custody obvious. A model has not passed this case unless the produced workspace can be executed independently, regardless of the final assistant message.

For a shareable version of the exact prompt, pass criteria, verifier commands, and expected manual outputs, see `docs\csvql-local-agent-challenge.md`.

## 2026-07-02/03 GLM-4.5-Air-NVFP4 CSVQL

Model: `GLM-4.5-Air-NVFP4`, served from `Firworks/GLM-4.5-Air-nvfp4` with vLLM nightly aarch64, `glm47` tool and reasoning parsers.

Summary:

| Run | Context Window | Output Cap | Exchanges | Upstream Errors | Commands | Files Landed | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `20260702-180525-glm45airnv_csvql-repair` | 131072 | 32768 default | 16 | 0 | 15 | 6 | failed partial app; final response hit `max_output_tokens` |
| `20260702-200142-glm45airnv_csvql_64k-repair` | 65536 | 32768 default | 7 | 1 | 6 | 1 | failed upstream 400 because prompt plus output reserve exceeded 64k |
| `20260702-200615-glm45airnv_csvql_64k_cap16k-repair` | 65536 | 16384 | 24 | 0 | 23 | 3 | failed behavior; only CSV files plus an empty package marker landed |

The capped 64k run is the relevant behavior result. It avoided the context-window error and returned zero invalid tool calls after OpenGate normalization, but the final capture contained XML-ish `write_file` text in the assistant message instead of structured executable tool calls. The workspace had no engine, parser, CLI, README, or tests. Independent checks failed for both `python -m csvql ...` and `python run_csvql.py ...`.

Conclusion: GLM-4.5-Air-NVFP4 is parked for this benchmark. The failure is not a new OpenGate repair target; it is an inability to complete the app under the live Codex harness. Detailed notes are in `docs\glm-4-5-air-nvfp4.md`.

## 2026-07-02/03 Kimi-Linear-48B-A3B-NVFP4 CSVQL

Model: `Kimi-Linear-48B-A3B-NVFP4`, served from `Firworks/Kimi-Linear-48B-A3B-Instruct-nvfp4` with vLLM nightly aarch64, `--max-model-len 65536`, `--enable-auto-tool-choice`, and `--tool-call-parser kimi_k2`.

Summary:

| Run | Context Policy | Output Cap | Exchanges | Upstream Errors | Commands | Files Landed | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `20260702-212631-kimi_linear_nvfp4_csvql_64k-repair` | `full` / native Responses | 16384 | 1 | 0 | 0 | 0 | failed immediately; unrelated email-analytics answer |
| `20260702-212847-kimi_linear_nvfp4_csvql_64k_spoon-repair` | `spoon` / flattened transcript | 16384 | 1 | 0 | 0 | 0 | failed after 179 s; unrelated puzzle/fish answer |

Both runs completed from Codex's perspective, but neither entered the tool loop. The workspace stayed empty. The direct `/v1/responses` plain-text sanity probe worked, while minimal tool probes did not produce structured tool calls. OpenGate now has a generic parser for Kimi reserved-token tool-call text seen during probing, but this live run produced no parseable Kimi tool syntax.

Conclusion: Kimi-Linear-48B-A3B-NVFP4 is parked for this benchmark on the current vLLM stack. This is a tool-interface and prompt-grounding failure, not a partial CSVQL implementation and not a new task-steering repair target.

## 2026-07-02/03 MiniMax-M3-MXFP8 Deployment Probe

Model: `MiniMax-M3-MXFP8`, attempted from `MiniMaxAI/MiniMax-M3-MXFP8` with vLLM nightly aarch64, `--max-model-len 65536`, and `--trust-remote-code`.

The model never reached a usable OpenAI-compatible endpoint, so the CSVQL suite was not run. vLLM accepted the custom architecture and selected the MiniMax MXFP8/sparse-attention path, but the first launch failed during model construction with CUDA OOM on the 119 GiB GX10. A retry with `--cpu-offload-gb 8`, `--kv-cache-dtype fp8`, and `--enforce-eager` reached `UVAOffloader` but saturated host memory and made SSH unresponsive.

Conclusion: MiniMax-M3-MXFP8 is deployment-blocked on this host. Do not score it as a CSVQL failure or add OpenGate repairs from this attempt. Detailed notes are in `docs\minimax-m3-mxfp8.md`.

## 2026-07-02/03 Devstral-Small-2507 CSVQL

Model: `Devstral-Small-2507`, served from `mistralai/Devstral-Small-2507` with vLLM nightly aarch64, Mistral tokenizer/config/load modes, `--max-model-len 65536`, `--enable-auto-tool-choice`, and `--tool-call-parser mistral`.

Summary:

| Run | Variant | Output Cap | Exchanges | Upstream Errors | Commands | Files Landed | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `20260702-225235-devstral_small_2507_csvql_64k-repair` | before upstream tool schema filter | 16384 | 1 | 1 | 0 | 0 | failed immediately on vLLM tool schema validation |
| `20260702-225804-devstral_small_2507_csvql_64k_r2-repair` | schema filter, shell only | 16384 | 4 | 0 | 3 | 0 | created directories, then stopped before app files |
| `20260702-230200-devstral_small_2507_csvql_64k_writefile_r3-repair` | schema filter plus `-WriteFileTool` | 16384 | 9 | 0 | 7 | 5 | partial workspace, syntactically broken engine, no CLI/tests |

The first run drove a valid OpenGate protocol fix: vLLM/Mistral requires function tools with an explicit boolean `strict` field and rejects Codex's hosted/namespace tool shapes. The proxy now filters unsupported upstream tool shapes, adds `strict: false`, and wraps `web_search` into a function-shaped tool before forwarding to vLLM.

The best Devstral run used `-WriteFileTool` and landed `README.md`, the two CSV fixtures, `csvql/__init__.py`, and `csvql/db.py`. Independent checks failed: `csvql/db.py` has a syntax error at `elif expr['op'] == '>/g')`, `python -m csvql ...` fails because `csvql.__main__` is missing, and `python run_csvql.py ...` fails because `run_csvql.py` is missing.

Conclusion: Devstral-Small-2507 is parked for this benchmark. It can run on the GX10 and enter the Codex file-writing loop, but it did not complete a runnable CSVQL application. Detailed notes are in `docs\devstral-small-2507.md`.

## 2026-07-03 Qwen3-Coder-Next Through Qwen Code CSVQL

Model: `Qwen3-Coder-Next`, served from `cyankiwi/Qwen3-Coder-Next-AWQ-4bit` with vLLM nightly aarch64 and `qwen3_coder` tool parser. Harness: Qwen Code CLI `0.19.5`, configured as an OpenAI-compatible provider against `http://<gx10-host>:8000/v1`.

Summary:

| Run | Context Window | Duration | Exit | Files Landed | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `20260703-082748-qwen3_coder_next_qwencode_csvql` | 32768 | 288.224 s | 0 | 1 | wrote one large `csvql.py`, then Qwen Code aborted continuation with context compression failure |
| `20260703-084553-qwen3_coder_next_qwencode_csvql_128k_r2` | 131072 | 2011.884 s | -1, stopped after drift | 7 | continued past the context issue, but built a different single-file demo and entered a self-debug loop |

The 32k run failed inside Qwen Code's own context manager after the first large file write: estimated prompt tokens `23638` exceeded its safe hard limit of about `20203`, even though the vLLM endpoint itself had a 32k max model length. The model config supports much more context (`max_position_embeddings = 262144`), so the GX10 endpoint was restarted at `--max-model-len 131072` and Qwen Code's `contextWindowSize` was updated to `131072`.

The 128k run proved that larger context fixes the compression ceiling. It did not pass CSVQL. The workspace contained `csvql.py`, `README.md`, `TESTS.md`, `EXAMPLES.md`, `sample_data/employees.csv`, `sample_data/products.csv`, and bytecode, but it missed `customers.csv`, `orders.csv`, `run_csvql.py`, the `csvql/` package, and a pytest suite. Independent checks failed: `python -m csvql --query ...` treated `--query` as a CSV path, `python run_csvql.py ...` failed because the file was missing, and pytest was skipped because there was no tests directory.

Conclusion: Qwen Code plus 128k gives a healthier tool loop than the 32k attempt, but this CSVQL result is still a behavior/artifact drift failure. The model lost the benchmark contract and self-debugged a non-fixture demo rather than producing the requested app. Detailed notes are in `docs\qwen3-coder-next.md`.

## 2026-05-29 Gemma-4-E4B-IT Smoke

Run folder: `runs\codex-live\20260529-201419-gemma4_e4b_it_live_smoke_workspace_0619_channel_filter-repair`

Summary:

| Metric | Value |
| --- | ---: |
| Codex turns completed | 3/3 |
| Upstream errors | 0 |
| Returned text leaks | 0 |
| Returned invalid tool calls | 0 |
| Returned command-quality issues | 0 |
| Structured argument repairs | 1 |
| Channel delimiter text repairs | 3 |
| Codex command executions | 1 |
| Returned clean capture rate | 100% |

Interpretation: Gemma reached meaningful Codex generation and completed the smoke suite after generic parser, command-quality, and channel-delimiter final-answer repairs. The final visible messages no longer include the pre-answer analysis or `<channel|>` marker. This is a smoke-clean result, not a broad build-workload certification.

## 2026-05-29 Gemma-4-E4B-IT Software-Build Load

Run folder: `runs\codex-live\20260529-210308-gemma4_e4b_it_software_build_0619_transcript_repair_fg-repair`

Summary:

| Metric | Value |
| --- | ---: |
| Codex turns completed | 1/3 |
| Upstream errors | 3 |
| Timed-out cases | 2/3 |
| Returned text leaks | 0 |
| Returned invalid tool calls | 0 |
| Returned command-quality issues | 0 |
| Codex command executions | 0 |
| Generated workspace artifacts | 0 |
| Returned clean capture rate | 100% |

Interpretation: this larger write-heavy gate did not pass. OpenGate kept returned responses clean after the pipe-style skill-call and transcript-imitation parser repairs, but Gemma/vLLM did not sustain the live build loop: two CLI cases timed out, the web case returned only an upstream connection-reset message, and no requested files were created. For Codex use, Gemma is therefore parked as not reliably usable beyond smoke; remaining failures are model/runtime behavior, not OpenGate repair targets.

## 2026-05-10 GLM Software-Build Attempt

Run folder: `runs\codex-live\20260510-123257-glm47_software_build_rerun-repair`

Summary:

| Metric | Value |
| --- | ---: |
| Codex turns completed | 3/3 |
| Proxy exchanges | 8 |
| Upstream text leaks | 6 |
| Returned text leaks | 0 |
| Promoted tool calls | 6 |
| Codex command executions | 2 |
| Generated project files | 1 |

Interpretation: Open Gate removed all returned text leaks, but the run was not a valid software-build success. Codex's model-visible permissions still said `read-only`, so one case refused to write, one case only created `sample_app.log`, and one case hit the upstream timeout path. The follow-up preflight run `runs\codex-live\20260510-124650-preflight_probe2-repair` now catches that mismatch before the model call.

## 2026-05-09 Qwen Validation

The first paired live validation used:

- Model: `Qwen3-Coder-Next`
- vLLM endpoint: `http://127.0.0.1:8001/v1`
- Suite: `fixtures\codex_live\smoke.json`
- Runs: `1`
- Cases: `plain_text`, `shell_count`, `no_tool_documentation`

Generated reports:

- Repair: `runs\codex-live\20260509-090222-codex_live_validation-repair\report.json`
- Observe: `runs\codex-live\20260509-113910-codex_live_validation-observe\report.json`

Summary:

| Metric | Repair | Observe |
| --- | ---: | ---: |
| Codex turns completed | 3/3 | 3/3 |
| Upstream errors | 0 | 0 |
| Policy-blocked Codex runs | 0 | 1 |
| Blocked-by-policy captures | 0 | 3 |
| Upstream command-quality issues | 1 | 1 |
| Returned command-quality issues | 0 | 1 |
| Upstream invalid tool calls | 1 | 1 |
| Returned invalid tool calls | 0 | 1 |
| Structured argument repairs | 1 | 1 recorded |
| Returned clean capture rate | 100% | 42.86% |

Interpretation: Qwen recovered in observe mode, so all three turns eventually completed. But raw observe mode made Codex hit policy blocks and extra exchanges because the bad shell command was returned to Codex. Repair mode returned the normalized command array immediately, so Codex completed the same suite without policy blocks.
