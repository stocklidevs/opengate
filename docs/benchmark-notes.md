# Benchmark Notes

Checked against direct vLLM at `http://127.0.0.1:8001/v1`:

- Qwen3-Coder-Next checked on 2026-05-09.
- GLM-4.7-Flash checked on 2026-05-10.
- Qwen3.6-27B basic smoke checked on 2026-05-11 UTC, 2026-05-10 America/New_York.

## Suites

`fixtures/benchmarks/codex_shell_smoke.json`

- 3 simple Codex-like cases.
- Expected behavior: structured `shell` or `update_plan` calls.
- One run against direct Qwen/vLLM: 3/3 strict successes.
- Three runs against direct GLM-4.7-Flash/vLLM: 0/9 strict successes.

`fixtures/benchmarks/codex_tool_leak_stress.json`

- 4 adversarial cases that bait XML, JSON, Pythonic, and `recipient_name` leakage.
- One run against direct Qwen/vLLM: 3/4 strict successes.
- No tool syntax leaked into text.
- One case embedded `recipient_name`/`functions.shell` strings inside the structured `update_plan` arguments, counted as `argument_leak`.
- Three runs against direct GLM-4.7-Flash/vLLM: 0/12 strict successes, with text leakage in 12/12 cases.

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

## Raw Model Comparison

These are direct vLLM results before Open Gate repairs. Run counts differ because Qwen was established first and GLM is the new adaptation target.

| Suite | Model | Runs | Strict Success | Text Leaks | Reasoning Leaks | Missed Tool Calls | Invalid Tool Calls | HTTP Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `codex_shell_smoke` | Qwen3-Coder-Next | 1 | 3/3, 100% | 0/3, 0% | 0/3, 0% | 0/3, 0% | 0/3, 0% | 0/3, 0% |
| `codex_shell_smoke` | Qwen3.6-27B | 3 | 9/9, 100% | 0/9, 0% | 0/9, 0% | 0/9, 0% | 0/9, 0% | 0/9, 0% |
| `codex_shell_smoke` | GLM-4.7-Flash | 3 | 0/9, 0% | 6/9, 66.67% | 0/9, 0% | 9/9, 100% | 0/9, 0% | 0/9, 0% |
| `codex_tool_leak_stress` | Qwen3-Coder-Next | 1 | 3/4, 75% | 0/4, 0% | 0/4, 0% | 0/4, 0% | 0/4, 0% | 0/4, 0% |
| `codex_tool_leak_stress` | GLM-4.7-Flash | 3 | 0/12, 0% | 12/12, 100% | 1/12, 8.33% | 12/12, 100% | 0/12, 0% | 0/12, 0% |
| `qwen_serious_tool_stress` | Qwen3-Coder-Next | 3 | 43/60, 71.67% | 10/60, 16.67% | 0/60, 0% | not recorded | 4/60, 6.67% | 0/60, 0% |
| `qwen_serious_tool_stress` | Qwen3.6-27B | 1 | 0/20, 0% | 0/20, 0% | 0/20, 0% | 15/20, 75% | 0/20, 0% | 20/20, 100% |
| `qwen_serious_tool_stress` | GLM-4.7-Flash | 1 | 2/20, 10% | 17/20, 85% | 5/20, 25% | 15/20, 75% | 1/20, 5% | 0/20, 0% |

## Prepared Qwen3.6-27B Benchmark

The next target is `Qwen3.6-27B` served from `Qwen/Qwen3.6-27B` with vLLM `--max-model-len 65536`, `--reasoning-parser qwen3`, `--enable-auto-tool-choice`, and `--tool-call-parser qwen3_coder`. The benchmark should be read in this order:

1. Direct `codex_shell_smoke`, three runs: complete, `9/9` strict successes.
2. Direct `qwen_serious_tool_stress`, one run: complete, `0/20` due to protocol incompatibility, not model leakage.
3. OpenGate `repair/full` on `qwen_serious_tool_stress`, three runs.
4. OpenGate `repair/spoon` on `qwen_serious_tool_stress`, one partial run: `17/20` captures completed before the external command timeout, `14/17` derived strict successes, zero returned leaks, invalid calls, or command-quality issues.
5. Live Codex software-build suite in a disposable writable folder.

Prepared commands and result placeholders are in `docs\qwen3-6-27b.md`.

OpenGate `0.6.9` changes benchmark interpretation for this case: `HTTP 400: Unexpected message role` is classified as a protocol incompatibility, and direct raw results should not be presented as ordinary tool-call failures. The proxy path addresses this by probing upstream role support and flattening unsupported native Responses input.

## GLM-4.7-Flash Direct Baseline

The GLM endpoint was served as `GLM-4.7-Flash` from `zai-org/GLM-4.7-Flash` with vLLM `max_model_len` 131072, `--tool-call-parser glm47`, and `--reasoning-parser glm45`. Full serving notes are in `docs\vllm-notes.md`.

Report files:

- `runs\glm47_flash_direct_smoke_r3.json`
- `runs\glm47_flash_direct_leak_stress_r3.json`
- `runs\glm47_flash_direct_serious_r1.json`

Overall direct-GLM result:

- Smoke suite: 0/9 strict successes, 6/9 text leaks, 9/9 missed structured tool calls.
- Leak-stress suite: 0/12 strict successes, 12/12 text leaks, 12/12 missed structured tool calls.
- Serious suite: 2/20 strict successes, 18/20 leaks, 15/20 missed tool calls, 3/20 over-eager tool calls, 1/20 invalid tool calls.

Open Gate GLM validation on `qwen_serious_tool_stress`:

| Mode | Context Policy | Strict Success | Text Leaks | Reasoning Leaks | Proxy Recoverable | Missed Tool Calls | Invalid Tool Calls |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| direct vLLM | n/a | 2/20, 10% | 17/20, 85% | 5/20, 25% | 0/20, 0% | 15/20, 75% | 1/20, 5% |
| Open Gate `repair` before GLM text parser | `full` | 2/20, 10% | 16/20, 80% | 9/20, 45% | 0/20, 0% | 13/20, 65% | 0/20, 0% |
| Open Gate `repair` before GLM text parser | `spoon` | 2/20, 10% | 15/20, 75% | 8/20, 40% | 2/20, 10% | 13/20, 65% | 1/20, 5% |
| Open Gate `0.6.0 repair` | `full` | 20/20, 100% | 0/20, 0% | 0/20, 0% | 0/20, 0% | 0/20, 0% | 0/20, 0% |
| Open Gate `0.6.0 repair` | `spoon` | 19/20, 95% | 0/20, 0% | 0/20, 0% | 0/20, 0% | 1/20, 5% | 0/20, 0% |

Open Gate `0.6.0` solves the repeatable GLM leakage shape without requiring the user to name the model. The linter recognizes GLM's XML-ish mini-format, promotes parseable leaked calls into Responses `function_call` items, repairs schema-cleanable arguments, and scrubs residual raw syntax from assistant and reasoning text.

The dominant raw failure was not HTTP or vLLM rejection. GLM returned HTTP 200, but emitted tool calls as assistant text, for example:

```text
<tool_call>shell<arg_key>command</arg_key>...
```

That shape was not converted by vLLM into Responses `function_call` items, so Codex-style clients saw leaked assistant text rather than executable tool calls. The `repair/full` result is now the preferred GLM setting for this synthetic suite. `repair/spoon` is still useful for long live Codex histories, but on this short synthetic suite it missed one case where GLM emitted an incomplete fenced JSON `tool_calls` block; Open Gate deliberately does not infer a tool call from incomplete JSON.

Final GLM report files:

- `runs\glm47_flash_open_gate_repair_glm_tags_v3_r1.json`
- `runs\glm47_flash_open_gate_repair_spoon_glm_tags_v4_r1.json`

## First Proxy Baseline

Open Gate buffered-upstream proxy mode was checked on 2026-05-09 with:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_proxy_benchmark.ps1 -Runs 3 -Label qwen_open_gate_serious_r3 -Output runs\qwen_open_gate_serious_r3.json
```

The proxy forwards `/v1/responses` to direct Qwen/vLLM with `stream: false`, normalizes the upstream response, and returns a Responses-shaped result. For interactive Codex streams, it sends Responses heartbeat events while waiting for that buffered upstream response. It currently handles:

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

This began as a benchmark-scope result. The interactive proxy now keeps streamed Codex sockets alive with Responses heartbeat events while preserving the same normalization guarantee.

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
