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

Start the proxy manually:

```powershell
python -m open_gate --upstream http://127.0.0.1:8001/v1 --normalization-mode repair
```

Run the live suite:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Mode repair -Runs 3
```

Run a baseline comparison:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Mode observe -Runs 3 -Label codex_live_observe
```

Each run writes a folder under `runs\codex-live\` with:

- `manifest.json`: suite, mode, timing, prompt metadata.
- `codex-*.jsonl`: combined `codex exec --json` output.
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
- `returned_clean_capture_rate`: captures with no returned leaks, invalid calls, command-quality issues, or policy block markers.

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
