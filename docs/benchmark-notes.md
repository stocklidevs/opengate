# Benchmark Notes

Checked on 2026-05-09 against direct vLLM at `http://127.0.0.1:8001/v1`.

## Suites

`fixtures/benchmarks/codex_shell_smoke.json`

- 3 simple Codex-like cases.
- Expected behavior: structured `shell` or `update_plan` calls.
- One run against direct Qwen/vLLM: 3/3 strict successes.

`fixtures/benchmarks/codex_tool_leak_stress.json`

- 4 adversarial cases that bait XML, JSON, Pythonic, and `recipient_name` leakage.
- One run against direct Qwen/vLLM: 3/4 strict successes.
- No tool syntax leaked into text.
- One case embedded `recipient_name`/`functions.shell` strings inside the structured `update_plan` arguments, counted as `argument_leak`.

## Current Interpretation

The current direct Qwen/vLLM setup is already doing well for basic Responses tool calls. The benchmark is still useful because:

- It creates a repeatable baseline before Open Gate changes anything.
- It separates text leakage from structured argument leakage.
- It gives us a community-friendly report shape for comparing raw backends against the proxy.
- It can be expanded with harder multi-turn Codex traces where leakage is more likely.

## Serious Stress Baseline

`fixtures/benchmarks/qwen_serious_tool_stress.json`

- 20 cases per run.
- Categories: normal tool use, leak bait, no-tool traps, schema pressure, wrong-tool bait.
- Three direct-Qwen runs on 2026-05-09: 60 generation requests.
- Full report: `runs/qwen_direct_serious_r3.json`.

Overall direct-Qwen result:

- Strict successes: 43/60, or 71.67%.
- Failures: 17/60, or 28.33%.
- Text leaks: 10/60, or 16.67%.
- Reasoning leaks: 0/60.
- Proxy-recoverable leaks: 3/60, or 5%.
- Over-eager tool calls in no-tool cases: 9/60, or 15%.
- Invalid structured tool calls: 4/60, or 6.67%.
- HTTP errors: 0.

Category breakdown:

- Normal tool use: 12/12 strict successes.
- Wrong-tool bait: 6/6 strict successes.
- Leak bait: 14/18 strict successes, with 4 text leaks. Three of those leaks were parseable enough to be proxy-recoverable.
- No-tool traps: 6/15 strict successes. The model often either printed raw tool syntax or converted documentation examples into actual tool calls.
- Schema pressure: 5/9 strict successes. Failures were mostly invalid arguments, such as a string command where Codex expects an argv array.

Key failure cases:

- `markdown_fence_bait`: failed 3/3, but all were proxy-recoverable.
- `no_tool_json_example_bait`: failed 3/3 with text leakage and over-eager tool behavior.
- `no_tool_pythonic_example_bait`: failed 3/3 with text leakage and over-eager tool behavior.
- `no_tool_xml_example_bait`: failed 3/3 by converting documentation requests into actual tool calls.
- `schema_string_command_bait`: failed 2/3 with invalid tool arguments.
- `schema_extra_commentary_arg_bait`: failed 2/3 with invalid tool arguments.

## First Proxy Baseline

Open Gate buffered-upstream proxy mode was checked on 2026-05-09 with:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_proxy_benchmark.ps1 -Runs 3 -Label qwen_open_gate_serious_r3 -Output runs\qwen_open_gate_serious_r3.json
```

The proxy forwards `/v1/responses` to direct Qwen/vLLM with `stream: false`, normalizes the upstream response, and returns a Responses-shaped result. For interactive Codex streams, it sends SSE heartbeat comments while waiting for that buffered upstream response. It currently handles:

- Stripping leaked tool syntax from assistant text.
- Promoting parseable leaked tool calls into structured `function_call` items when the prompt does not indicate no-tool/documentation intent.
- Suppressing structured tool calls when the latest user prompt clearly asks not to use tools.
- Repairing simple schema mistakes, including string `shell.command` values and extra arguments when the schema disallows them.
- Repairing nested `powershell.exe -Command` shell calls before Codex policy sees them.

Proxy mode now has two comparison settings:

- `repair`: return normalized responses to Codex or the benchmark caller.
- `observe`: record the normalization report but return the raw upstream response.

Raw Qwen vs Open Gate on `qwen_serious_tool_stress`, 60 requests each:

| Metric | Raw Qwen | Open Gate |
| --- | ---: | ---: |
| Strict success | 43/60, 71.67% | 60/60, 100% |
| Failures | 17/60, 28.33% | 0/60, 0% |
| Text leaks | 10/60, 16.67% | 0/60, 0% |
| Reasoning leaks | 0/60, 0% | 0/60, 0% |
| Over-eager tool calls | 9/60, 15% | 0/60, 0% |
| Invalid tool calls | 4/60, 6.67% | 0/60, 0% |
| HTTP errors | 0/60, 0% | 0/60, 0% |

This began as a benchmark-scope result. The interactive proxy now keeps streamed Codex sockets alive with heartbeat comments while preserving the same normalization guarantee.

Newer reports also include `command_quality_issues_rate`. This metric catches structured tool calls that parse as JSON but are likely to be rejected by Codex policy. Older saved reports in `runs\` predate this metric.

For whole-Codex measurements, use `scripts\run_codex_live_benchmark.ps1` and `open_gate.codex_report`. See `docs\live-codex-benchmark.md`.

## Live Codex Observe Vs Repair

Checked on 2026-05-09 with `fixtures\codex_live\smoke.json`, one run per mode.

| Metric | Repair | Observe |
| --- | ---: | ---: |
| Codex turns completed | 3/3 | 3/3 |
| Policy-blocked Codex runs | 0 | 1 |
| Blocked-by-policy captures | 0 | 3 |
| Returned command-quality issues | 0 | 1 |
| Returned invalid tool calls | 0 | 1 |
| Returned clean capture rate | 100% | 42.86% |

The important nuance is that observe mode eventually recovered, but only after Codex saw and rejected a bad raw tool call. Repair mode removed that failed intermediate step.

## Interactive Smoke

Checked on 2026-05-09 with `scripts/run_codex_proxy_smoke.ps1`.

- Plain `codex exec` assistant-message streaming through Open Gate worked.
- A shell-tool prompt also worked end to end: Codex accepted the streamed `function_call`, ran the shell command, sent the tool output back through Open Gate, and received the final assistant answer.
- The tool prompt revealed one realistic model blemish: Qwen first emitted a nested PowerShell command rejected by Codex policy, then recovered with a simpler allowed command. This is now covered by `fixtures\regressions\qwen_nested_powershell_20260509.json`.
