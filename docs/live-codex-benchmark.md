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
