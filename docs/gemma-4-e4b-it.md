# Gemma-4-E4B-IT Compatibility

This note records the OpenGate validation status for `google/gemma-4-E4B-it`.

## Status

- Model repository: `google/gemma-4-E4B-it`
- Served model name: `Gemma-4-E4B-IT`
- Server: vLLM at `http://127.0.0.1:8001/v1`
- OpenGate target version: `0.6.20`
- OpenGate mode: `repair`
- Upstream input mode: `auto`
- Context policy: `full` for first synthetic comparisons, `spoon` for live Codex work and long histories.
- Validation status: parked for Codex use beyond smoke after the larger software-build gate failed with upstream errors and no artifacts.
- Validation date: `2026-05-29` America/New_York.

## vLLM Setup

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

The important tool-related settings are `--enable-auto-tool-choice`, `--tool-call-parser gemma4`, and the Gemma 4 tool chat template. This adaptation validates that parser/template pair as served.

## OpenGate Setup

Use a local ignored `opengate.toml` with `model = "auto"` so OpenGate detects the served vLLM model:

```toml
[upstream]
scheme = "http"
host = "127.0.0.1"
port = 8001
path = "/v1"
model = "auto"
capability_probe = "auto"
capability_probe_timeout = 8

[proxy]
normalization_mode = "repair"
upstream_input_mode = "auto"
context_policy = "full"
upstream_max_output_tokens = 4096
```

Expected startup behavior:

- `/v1/models` reports `Gemma-4-E4B-IT`.
- `/health` reports `model = Gemma-4-E4B-IT`.
- Capability probing records whether the upstream accepts developer/system roles and native tool-history input.

## Result Log

| Check | Expected | Result |
| --- | --- | --- |
| `/v1/models` | `id = Gemma-4-E4B-IT` | pass: `root = google/gemma-4-E4B-it`, `max_model_len = 16384` |
| Upstream `/version` | vLLM version recorded | pass: `0.20.1` |
| Upstream `/health` | endpoint healthy | pass |
| OpenGate `/health` | `model = Gemma-4-E4B-IT`, autodetected | pass: `model_source = upstream /models` |
| OpenGate capability probe | record supported input shapes | pass: native Responses input, developer/system roles, and native tool history supported; flattening not required |
| Direct smoke baseline | record strict success and leakage rates | pass: 9/9 strict, 0 leaks |
| Direct leak-stress baseline | record leak and argument-leak behavior | complete: 0/12 strict, 12/12 text leaks |
| Direct serious baseline | record raw failure/leakage behavior | complete: 27/60 strict, 33/60 text leaks, 8 invalid calls |
| OpenGate observe/full | record normalization opportunities while returning raw output | complete: 9/20 strict, 11/20 text leaks |
| OpenGate repair/full | zero returned text/reasoning leaks and zero invalid tool calls | complete: pre-repair 57/60 strict; post-repair r1 19/20 strict, 0 leaks, 0 invalid calls |
| OpenGate repair/spoon | zero returned leaks with compact context | complete: pre-repair 18/20 strict; post-repair r1 19/20 strict, 0 leaks, 0 invalid calls |
| Live Codex smoke | turns complete without Codex-visible leaks or policy blocks | complete: latest workspace smoke completed 3/3 turns, 0 upstream errors, 0 returned text/tool leaks, 0 returned invalid calls, 0 returned command-quality issues, and 3 channel-delimiter text repairs; final messages contain only the answer suffix |

## Report Files

- Health probe capture directory: `runs/gemma4_e4b_it_health_probe/captures`
- Direct smoke: `runs/gemma4_e4b_it_direct_smoke_r3.json`
- Direct leak-stress: `runs/gemma4_e4b_it_direct_leak_stress_r3.json`
- Direct serious: `runs/gemma4_e4b_it_direct_serious_r3.json`
- OpenGate observe/full: `runs/gemma4_e4b_it_open_gate_observe_full_r1.json`
- OpenGate repair/full pre-repair: `runs/gemma4_e4b_it_open_gate_repair_full_r3.json`
- OpenGate repair/spoon pre-repair: `runs/gemma4_e4b_it_open_gate_repair_spoon_r1.json`
- OpenGate repair/full post-`toolSpec` repair: `runs/gemma4_e4b_it_open_gate_repair_full_toolspec_r1.json`
- OpenGate repair/spoon post-`toolSpec` repair: `runs/gemma4_e4b_it_open_gate_repair_spoon_toolspec_r1.json`
- Live smoke before command-quality repairs: `runs/codex-live/20260529-193656-gemma4_e4b_it_live_smoke_workspace-repair`
- Live smoke after command-quality repairs: `runs/codex-live/20260529-195244-gemma4_e4b_it_live_smoke_workspace_cq_repair2-repair`
- Live smoke after channel-delimiter repair: `runs/codex-live/20260529-201419-gemma4_e4b_it_live_smoke_workspace_0619_channel_filter-repair`
- Regression fixtures: `fixtures/regressions/gemma4_toolspec_wrapper_20260529.json`, `fixtures/regressions/gemma4_direct_powershell_pipeline_20260529.json`, `fixtures/regressions/gemma4_escaped_json_tail_command_20260529.json`, `fixtures/regressions/gemma4_direct_powershell_dot_path_20260529.json`, `fixtures/regressions/gemma4_channel_delimited_final_answer_20260529.json`

## Serving Evidence

- `/v1/models`: `id = Gemma-4-E4B-IT`, `root = google/gemma-4-E4B-it`, `max_model_len = 16384`, `owned_by = vllm`.
- Upstream `/version`: `0.20.1`.
- Upstream `/health`: healthy.
- Startup warnings: not available through the HTTP endpoint from this workspace; no health or capability-probe warning was observed.
- OpenGate `/health`: `version = 0.6.18` during the initial health probe; the latest live smoke manifest records `version = 0.6.19`. Both runs report `model = Gemma-4-E4B-IT`, `normalization_mode = repair`, and `upstream_input_mode = auto`.
- OpenGate capability probe: `supports_responses_user_input = true`, `supports_developer_role = true`, `supports_system_role = true`, `supports_native_tool_history = true`, `requires_flattened_input = false`, with no probe errors.

## Direct Baseline Interpretation

Direct baseline commands ran successfully against `http://127.0.0.1:8001/v1` with no HTTP, protocol, or transport errors.

| Report | Total | Strict success | Text leaks | Reasoning leaks | Missed tools | Wrong tools | Over-eager tools | Invalid calls | Command-quality issues |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct smoke r3 | 9 | 9 (100%) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Direct leak-stress r3 | 12 | 0 (0%) | 12 (100%) | 0 | 0 | 0 | 0 | 0 | 0 |
| Direct serious r3 | 60 | 27 (45%) | 33 (55%) | 0 | 4 (6.67%) | 6 (10%) | 6 (10%) | 8 (13.33%) | 0 |

Category highlights:

- Smoke passed both `single_tool` and `tool_selection` categories with 100% strict success.
- Leak-stress failed all `leak_bait` cases as returned assistant text leaks.
- Serious `normal_tool` and `wrong_tool_bait` categories were clean.
- Serious failures concentrated in `leak_bait` (18/18 text leaks), `no_tool` bait prompts (9/15 failures, including wrong/over-eager tool calls), and `schema_pressure` (6/9 failures, including 5 invalid calls and 4 missed calls).

Initial reading: Gemma is protocol-compatible and good on ordinary tool calls, but raw output frequently exposes tool-call-like text under bait and schema pressure. The no-tool over-eagerness is behavior evidence; parser/schema repair candidates require OpenGate observe/repair captures before code changes.

## OpenGate Comparison

| Report | Total | Strict success | Text leaks | Reasoning leaks | Missed tools | Wrong tools | Over-eager tools | Invalid calls | Command-quality issues |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Observe/full r1 | 20 | 9 (45%) | 11 (55%) | 0 | 1 (5%) | 1 (5%) | 1 (5%) | 1 (5%) | 0 |
| Repair/full r3, before `toolSpec` repair | 60 | 57 (95%) | 0 | 0 | 3 (5%) | 0 | 0 | 0 | 0 |
| Repair/spoon r1, before `toolSpec` repair | 20 | 18 (90%) | 0 | 0 | 2 (10%) | 0 | 0 | 0 | 0 |
| Repair/full r1, after `toolSpec` repair | 20 | 19 (95%) | 0 | 0 | 1 (5%) | 0 | 0 | 0 | 0 |
| Repair/spoon r1, after `toolSpec` repair | 20 | 19 (95%) | 0 | 0 | 1 (5%) | 0 | 0 | 0 | 0 |

OpenGate already removed the dominant raw leakage and invalid-call issues. The accepted repair covered an additional parser gap where Gemma emitted a duplicated fenced JSON `toolSpec` wrapper, including a second copy immediately after a `<channel|>` marker. After the repair, the previously failing `markdown_fence_bait` case passes in `repair/spoon`.

The remaining post-repair synthetic failures are missed-tool cases where Gemma explains a schema conflict instead of emitting a structured call:

- `schema_extra_commentary_arg_bait`: requested `update_plan` with an invalid extra top-level argument, and Gemma refused to call the tool.
- `schema_extra_recipient_arg_bait`: requested `shell` with an invalid extra `recipient_name` argument, and Gemma reasoned about the conflict instead of emitting a clean call in the post-repair spoon run.

Those are behavior/schema-pressure misses, not returned leaks, invalid structured calls, protocol errors, or command-quality failures.

## Live Codex Smoke

The first workspace-write live smoke reached Codex but exposed command-quality gaps that were not visible in the synthetic reports:

- Gemma emitted `shell.command = ["Get-ChildItem | Measure-Object -Line"]`; OpenGate wrapped that as `powershell.exe -Command 'Get-ChildItem | Measure-Object -Line'`, which PowerShell treated as a string literal instead of executing the pipeline.
- On retry, Gemma emitted an escaped JSON-tail command array that Codex attempted to execute as a malformed program name.
- A later live run emitted `shell.command = ["Get-ChildItem -Path . | Measure-Object"]`; the previous cmdlet detector missed it because it considered the `.` path argument part of the executable name.

Those shapes are command-quality repairs, not model behavior steering. They are now covered by live capture-derived fixtures and focused tests.

Live smoke after command-quality repair:

| Run | Result |
| --- | --- |
| `runs/codex-live/20260529-195244-gemma4_e4b_it_live_smoke_workspace_cq_repair2-repair` | 3/3 Codex turns completed, 0 upstream errors, 0 returned text/tool leaks, 0 returned invalid calls, 0 returned command-quality issues, 1 structured argument repair, 1 shell command execution |

The tool-use case succeeded after repair: Codex executed `Get-ChildItem` in `C:\Users\example\source\repos\glm-test`, and Gemma answered that it saw 4 entries. However, all three final message files include visible pre-answer analysis followed by a `<channel|>` delimiter before the user-facing answer. That is a model output-format behavior issue, so the model should not be marked known-good for Codex yet.

The accepted follow-up repair is narrow and model-agnostic: if assistant-visible message text contains `<channel|>` and the final marker has a non-empty suffix, OpenGate returns only that suffix. It does not strip arbitrary planning prose, and it does not touch reasoning items.

Latest live smoke:

| Run | Result |
| --- | --- |
| `runs/codex-live/20260529-201419-gemma4_e4b_it_live_smoke_workspace_0619_channel_filter-repair` | 3/3 Codex turns completed, 0 upstream errors, 0 returned text/tool leaks, 0 returned invalid calls, 0 returned command-quality issues, 1 structured argument repair, 3 channel-delimiter text repairs, 1 shell command execution, `returned_clean_capture_rate = 1.0` |

Visible final messages after repair:

- `plain_text`: `Hello! How can I assist you today?`
- `shell_count`: `I inspected the current directory, C:\Users\example\source\repos\glm-test, and I saw 4 entries.`
- `no_tool_documentation`: returns only the PowerShell command explanation, without the pre-answer analysis or `<channel|>` marker.

## Capture Inspection And Repair Decisions

| Candidate | Classification | Evidence | Upstream shape | Codex-visible impact | Decision |
| --- | --- | --- | --- | --- | --- |
| Fenced JSON `toolSpec` wrapper, duplicated after `<channel|>` | Parser | `runs/gemma4_e4b_it_open_gate_repair_spoon_r1/captures/20260529-230431-387188-proxy-8cccd545.json`; `fixtures/regressions/gemma4_toolspec_wrapper_20260529.json` | Assistant text includes Markdown JSON with `toolSpec.name` and `toolSpec.args`, plus a duplicate block after a channel marker | Before repair, the wrapper was not promoted and one copy could remain visible as text | Implemented model-agnostic parser repair in `open_gate/linter.py` |
| Single-item PowerShell script arrays | Command-quality | `runs/codex-live/20260529-193656-gemma4_e4b_it_live_smoke_workspace-repair/captures/20260529-233750-215310-proxy-52a41a7d.json`; `fixtures/regressions/gemma4_direct_powershell_pipeline_20260529.json`; `fixtures/regressions/gemma4_direct_powershell_dot_path_20260529.json` | Structured `shell` call uses a one-item command array whose item is a PowerShell cmdlet script or pipeline | Codex tries to execute the whole script as a program, or OpenGate quotes the script as a literal string | Implemented model-agnostic repair that wraps the script as `powershell.exe -Command <script>` without adding literal quotes |
| Escaped JSON tail inside `shell.command` | Command-quality | `runs/codex-live/20260529-193656-gemma4_e4b_it_live_smoke_workspace-repair/captures/20260529-233818-075718-proxy-72da48a3.json`; `fixtures/regressions/gemma4_escaped_json_tail_command_20260529.json` | Structured `shell.command` contains escaped fragments such as `powershell.exe\",\"-Command\"...],\"workdir\"...` as one array item | Codex attempts to execute a malformed program name | Implemented model-agnostic quarantine as command-quality error |
| `<channel|>` final-answer preface | Output-format repair | `runs/codex-live/20260529-195244-gemma4_e4b_it_live_smoke_workspace_cq_repair2-repair/captures/20260529-235403-246354-proxy-54ef0e4d.json`; `fixtures/regressions/gemma4_channel_delimited_final_answer_20260529.json` | Assistant text contains private answer analysis before the marker and the actual user-facing answer after it | Codex-visible final text includes analysis that should have stayed hidden | Implemented model-agnostic suffix filter only when a non-empty suffix follows the final marker |
| Gemma pipe-style unavailable skill call after `<channel|>` | Parser/output-format | `runs/codex-live/20260529-202640-gemma4_e4b_it_software_build_0619-repair/captures/20260530-002917-615925-proxy-6033a1af.json`; `fixtures/regressions/gemma4_pipe_skill_call_20260529.json` | Assistant text includes `<|tool_call>call:superpowers:brainstorming{...}<tool_call|>` after the channel marker | Codex receives raw unavailable skill syntax instead of a valid tool loop | Implemented parser detection and a generic diagnostic tool-output loop; do not add task-specific skill/tool steering |
| Codex transcript-style tool call text | Parser/output-format | `runs/codex-live/20260529-204513-gemma4_e4b_it_software_build_0619_pipe_full-repair/captures/20260530-004732-147768-proxy-d380f5ba.json`; `fixtures/regressions/gemma4_codex_transcript_tool_call_20260529.json` | Assistant text says `assistant tool call shell ...` followed by JSON arguments and a fabricated `tool output` block | Codex treats the block as assistant text, so no command executes and artifacts are not created | Implemented model-agnostic parser promotion for the JSON command while stripping the fabricated transcript/output text |
| Invalid-extra-argument schema pressure | Behavior | `runs/gemma4_e4b_it_open_gate_repair_full_toolspec_r1.json`; `runs/gemma4_e4b_it_open_gate_repair_spoon_toolspec_r1.json` | Gemma explains why an extra argument conflicts with the tool schema rather than emitting a corrected structured call | Missed expected tool only; no returned leaks or invalid calls | Document only; do not add task-steering/model-behavior repair |

Verification after the accepted repair:

- Focused parser tests: `uv run pytest tests\test_linter.py::LinterTests::test_tool_spec_wrapper_becomes_tool_call tests\test_proxy.py::ProxyNormalizationTests::test_promotes_fenced_tool_spec_wrapper`
- Focused suites: `uv run pytest tests\test_linter.py tests\test_proxy.py`
- Regression replay: `uv run python -m open_gate.regression --pretty`
- Post-repair synthetic checks: `repair/full` r1 and `repair/spoon` r1, both 19/20 strict with zero leaks and zero invalid calls.
- Live command-quality repair tests: `python -m pytest tests\test_command_quality.py tests\test_proxy.py`
- Latest regression replay: `python -m open_gate.regression --pretty`
- Channel-delimiter focused tests: `python -m pytest tests\test_proxy.py -k "channel_delimiter or channel_delimited"` and `python -m pytest tests\test_codex_report.py tests\test_regression.py tests\test_capture_to_fixture.py`
- Latest live smoke summary: `python -m open_gate.codex_report runs\codex-live\20260529-201419-gemma4_e4b_it_live_smoke_workspace_0619_channel_filter-repair\captures --codex-dir runs\codex-live\20260529-201419-gemma4_e4b_it_live_smoke_workspace_0619_channel_filter-repair --pretty --summary-only`
- Software-build load after pipe/transcript repairs: `runs\codex-live\20260529-210308-gemma4_e4b_it_software_build_0619_transcript_repair_fg-repair` completed 1/3 Codex turns, timed out 2/3 cases, recorded 3 upstream errors, executed 0 commands, and produced no workspace artifacts.

## Compatibility State

Current state: `parked`; smoke-clean, but not reliably usable with Codex beyond smoke.

OpenGate can repair Gemma's current tool-call, command-quality, channel-delimited final-answer, pipe-style skill-call, and transcript-imitation shapes well enough for the small live smoke tool path to run cleanly. The larger software-build suite is not passed: after parser repairs, the foreground run hit upstream timeout/connection-reset errors, produced no command executions, and created no requested artifacts. Treat Gemma as parked for Codex use unless a future serving/model change makes the larger live build gate produce real artifacts.

The remaining documented limitations are synthetic schema-pressure behavior and larger-run reliability. When a prompt deliberately asks for invalid extra tool arguments, Gemma may explain the conflict instead of emitting a corrected tool call. Under heavier Codex build load, Gemma/vLLM can stall or close the upstream connection before meaningful tool use. Those are behavior/runtime reliability findings, not task-steering repair targets.

## Failure Classification Rules

- **Protocol**: vLLM rejects Codex-style roles, tool history, tool schemas, or Responses input before meaningful generation.
- **Parser**: model emits tool syntax as assistant/reasoning text instead of structured calls.
- **Schema**: structured calls exist but violate tool argument schemas.
- **Command-quality**: structured calls parse but would fail Codex policy or runtime checks.
- **Behavior**: wrong tool choice, planning loops, stalls, no-tool answer artifacts, or task-progress drift.

Only protocol, parser, schema, and command-quality failures are OpenGate repair candidates. Behavior-only failures should be documented without task-steering repair logic.

## Acceptance Criteria

- Direct vLLM baselines are recorded before OpenGate claims are made.
- OpenGate `repair` returns zero assistant-text or reasoning tool-call leaks.
- OpenGate returns zero invalid structured tool calls and zero error-level command-quality issues to Codex.
- Any new repair is model-agnostic and backed by a real capture or benchmark failure shape.
- Live Codex smoke must reach meaningful model generation and complete without upstream schema errors before the model is marked known-good.
