# DeepSeek-Coder-V2-Lite-Instruct Compatibility

This note records the OpenGate validation status for `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`.

## Status

- Model repository: `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`
- Served model name: `DeepSeek-Coder-V2-Lite-Instruct`
- Server: vLLM at `http://127.0.0.1:8001/v1`
- vLLM version: `0.20.1`
- OpenGate mode: `repair`
- Upstream input mode: `auto`
- Context policy: `full` for first synthetic comparisons, `spoon` for live Codex work and long histories.
- Validation status: accepted synthetic repairs and live namespace-tool protocol repair implemented; current live status is behavior-limited, so the model is not known-good yet.
- Validation date: `2026-05-28` America/New_York.

## vLLM Setup

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

The important tool-related settings are `--enable-auto-tool-choice`, `--tool-call-parser deepseek_v3`, and the DeepSeek v3 tool chat template. This adaptation validates that parser/template pair as served.

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

- `/v1/models` reports `DeepSeek-Coder-V2-Lite-Instruct`.
- `/health` reports `model = DeepSeek-Coder-V2-Lite-Instruct`.
- Capability probing records whether the upstream accepts developer/system roles and native tool history.

## Result Log

| Check | Expected | Result |
| --- | --- | --- |
| `/v1/models` | `id = DeepSeek-Coder-V2-Lite-Instruct` | pass; `root = deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`, `max_model_len = 16384` |
| Upstream `/version` | vLLM version recorded | pass; `0.20.1` |
| Upstream `/health` | endpoint healthy | pass; HTTP success with empty body |
| OpenGate `/health` | `model = DeepSeek-Coder-V2-Lite-Instruct`, autodetected | pass; `model_source = upstream /models`, `mode = proxy`, `normalization_mode = repair`, `context_policy = full` |
| OpenGate capability probe | record supported input shapes | pass; user, developer, system, and native tool-history input supported; `requires_flattened_input = false` |
| Direct smoke baseline | record strict success and leakage rates | complete; `0/9` strict successes, `9/9` missed tool calls, zero leaks, zero invalid calls, zero command-quality issues, zero HTTP errors |
| Direct leak-stress baseline | record leak and argument-leak behavior | complete; `0/12` strict successes, `6/12` text leaks, `3/12` proxy-recoverable, `9/12` missed tool calls, zero invalid calls, zero HTTP errors |
| Direct serious baseline | record raw failure/leakage behavior | complete; `9/60` strict successes, `18/60` text leaks, `45/60` missed tool calls, `6/60` wrong tools, `3/60` over-eager tools, `9/60` invalid calls, zero HTTP errors |
| OpenGate observe/full | record normalization opportunities while returning raw output | complete; `3/20` strict successes, `6/20` text leaks, `15/20` missed tool calls, `3/20` invalid calls, zero HTTP errors |
| OpenGate repair/full before DeepSeek parser | zero returned text/reasoning leaks and zero invalid tool calls | complete; `12/60` strict successes, zero legacy leak markers, zero invalid calls, zero command-quality issues, `42/60` missed tool calls; capture scan found DeepSeek delimiter text not yet recognized by the linter |
| OpenGate repair/spoon before DeepSeek parser | zero returned leaks with compact context | complete; `9/20` strict successes, `1/20` legacy text leak, zero invalid calls, zero command-quality issues, `10/20` missed tool calls |
| OpenGate repair/full after accepted repairs | zero returned text/reasoning leaks and zero invalid tool calls | complete; `48/60` strict successes, zero returned leaks, zero invalid calls, zero command-quality issues, `12/60` missed tool calls, zero HTTP/protocol errors |
| OpenGate repair/spoon after accepted repairs | zero returned leaks with compact context | complete; `17/20` strict successes, zero returned leaks, zero invalid calls, zero command-quality issues, `3/20` missed tool calls, zero HTTP/protocol errors |
| Live Codex smoke before namespace repair | turns complete without Codex-visible leaks or policy blocks | attempted; Codex recorded `3/3` completed turns and zero policy blocks, but all `3/3` upstream requests returned HTTP 400 validation errors on Codex `namespace` tool schemas, with zero command executions |
| Live Codex smoke after namespace repair | meaningful generation without upstream schema errors, Codex-visible leaks, invalid calls, or command-quality issues | complete; latest workspace-write run recorded `3/3` completed turns, `0` upstream errors, `1` command execution, zero returned leaks, zero returned invalid calls, zero returned command-quality issues, and `returned_clean_capture_rate = 1.0`; still behavior-limited because the no-tool documentation answer included DeepSeek chat-template preamble text |

## Report Files

- `runs\deepseek_v2_lite_direct_smoke_r3.json`
- `runs\deepseek_v2_lite_direct_leak_stress_r3.json`
- `runs\deepseek_v2_lite_direct_serious_r3.json`
- `runs\deepseek_v2_lite_open_gate_observe_full_r1.json`
- `runs\deepseek_v2_lite_open_gate_repair_full_r3.json`
- `runs\deepseek_v2_lite_open_gate_repair_spoon_r1.json`
- `runs\deepseek_v2_lite_open_gate_repair_full_deepseek_v3_parser_r3.json`
- `runs\deepseek_v2_lite_open_gate_repair_spoon_deepseek_v3_parser_v2_r1.json`
- `runs\codex-live\20260527-235147-deepseek_v2_lite_live_smoke_repair_spoon-repair\report.json`
- `runs\codex-live\20260528-164449-deepseek_v2_lite_live_smoke_repair_spoon_namespace_tools-repair\report.json`
- `runs\codex-live\20260528-164649-deepseek_v2_lite_live_smoke_repair_spoon_namespace_tools_workspace-repair\report.json`
- `runs\codex-live\20260528-165042-deepseek_v2_lite_live_smoke_repair_spoon_namespace_alias_workspace-repair\report.json`

## Direct Baseline Interpretation

Direct DeepSeek did not hit transport or protocol problems in the synthetic benchmark harness: all three direct benchmark reports completed with zero HTTP errors and zero protocol incompatibilities.

The dominant raw failure is missed expected tool calls:

- Smoke suite: `9/9` missed tool calls across basic shell and plan prompts.
- Leak-stress suite: `9/12` missed tool calls, with JSON tool-call bait leaking parseable text in `3/3` cases.
- Serious suite: `45/60` missed tool calls, including all normal-tool and wrong-tool-bait cases.

The second important failure shape is assistant-text leakage:

- Leak-stress suite: `6/12` text leaks, all in JSON or XML bait cases.
- Serious suite: `18/60` text leaks, concentrated in leak-bait, no-tool JSON/XML examples, response-tag bait, and schema extra-recipient bait.

Direct serious also produced `9/60` invalid structured calls and `6/60` wrong-tool failures. There were no command-quality issues in the raw structured calls that were scored.

Initial classification: DeepSeek is reachable and protocol-compatible with the benchmark harness, but the parser/template combination is not reliably converting Codex-style tool prompts into structured tool calls. OpenGate repair focuses on parser/text-tool-call recovery and schema repair, while documenting no-tool over-eager behavior separately.

## Synthetic Repair Implementation

The accepted repairs are model-agnostic and capture-backed:

- Parse DeepSeek/vLLM delimited function text such as `<\uff5ctool\u2581call\u2581begin\uff5c>function<\uff5ctool\u2581sep\uff5c>shell` followed by fenced JSON arguments.
- Strip partial DeepSeek close/output markers such as `<\uff5ctool\u2581call\u2581end\uff5c>`, `<\uff5ctool\u2581calls\u2581end\uff5c>`, and `<\uff5ctool\u2581outputs\u2581begin\uff5c>` when no safe tool name can be recovered.
- Treat JSON `tool_calls` objects that use `function.parameters` as equivalent to `function.arguments` when arguments are absent.
- Avoid adding diagnostic shell calls after negative-tool-intent no-tool/documentation prompts.
- Neutralize residual literal `<tool_call>` tag text that remains after other repairs.

Implemented regression fixtures:

- `fixtures/regressions/deepseek_v3_delimited_shell_20260528.json`
- `fixtures/regressions/deepseek_v3_partial_marker_strip_20260528.json`
- `fixtures/regressions/json_tool_calls_function_parameters_20260528.json`
- `fixtures/regressions/negative_tool_intent_no_actionable_tool_20260528.json`

After those repairs, `repair/full` reached `48/60` strict successes with zero returned leaks, zero invalid calls, zero command-quality issues, and `12/60` missed tool calls. The category breakdown was complete for normal tool use (`12/12`) and schema pressure (`9/9`), clean for no-tool traps (`15/15`), and still limited by missed tool calls in leak-bait and wrong-tool-bait cases. `repair/spoon` reached `17/20` strict successes with the same zero-leak/zero-invalid guarantee.

## Live Codex Smoke

The first live Codex smoke after the synthetic repairs used `repair/spoon`. Codex recorded `3/3` completed turns, zero Codex-visible policy blocks, and a `returned_clean_capture_rate` of `1.0`, but that was not a known-good live pass: all `3/3` proxy captures contained upstream HTTP 400 validation errors before generation.

The root cause was in OpenGate request compaction, not DeepSeek text parsing. Codex forwarded an MCP namespace tool such as `mcp__node_repl__` with nested child tools, but the request-diet compactor preserved the outer `type = "namespace"` object while dropping its nested `tools` array. vLLM then rejected the malformed namespace schema before generation. OpenGate now recursively preserves nested namespace tools during schema compaction.

After that fix, a `repair/spoon` live smoke without workspace-write produced `0` upstream errors but no command executions because Codex was sandboxed read-only. A workspace-write smoke then exposed a second repairable command-quality shape: the model promoted `shell` with `command = ["dir"]`, which Windows cannot execute as a standalone program. OpenGate now treats bare PowerShell aliases such as `dir` like direct cmdlets and wraps them as `powershell.exe -Command dir`.

The latest workspace-write run, `runs\codex-live\20260528-165042-deepseek_v2_lite_live_smoke_repair_spoon_namespace_alias_workspace-repair`, recorded `3/3` completed turns, `0` upstream errors, `1` successful command execution, zero returned leaks, zero returned invalid calls, zero returned command-quality issues, and `returned_clean_capture_rate = 1.0`.

That moves DeepSeek from live `protocol-blocked` to live `behavior-limited`. The model is still not known-good because the no-tool documentation answer includes DeepSeek chat-template preamble text before the useful answer. That is answer-quality/model behavior, not a protocol, parser, schema, or command-quality repair candidate yet.

## Capture Inspection And Repair Decisions

| Candidate | Classification | Evidence | Upstream shape | Codex-visible impact | Decision |
| --- | --- | --- | --- | --- | --- |
| DeepSeek-v3 delimited function text | Parser | `baseline_shell_list` run 0 capture `runs\deepseek_v2_lite_open_gate_repair_full_r3\captures\20260528-031116-512242-proxy-6532531a.json`; same full delimiter shape in `33/60` repair/full captures | DeepSeek tool-call begin marker, `function`, tool separator, tool name, fenced JSON arguments, and close/output markers | OpenGate returned raw delimiter text, missed the expected structured tool, and prior leak metrics undercounted it | Implemented in `open_gate.linter`; fixture `fixtures/regressions/deepseek_v3_delimited_shell_20260528.json` |
| DeepSeek partial close/output marker text | Parser | `markdown_fence_bait` run 0 capture `runs\deepseek_v2_lite_open_gate_repair_full_r3\captures\20260528-031206-790714-proxy-c9888859.json`; partial marker shape in `15/60` repair/full captures | Fenced JSON or tool-output text followed by DeepSeek close/output markers without a reliable opening tool-name delimiter | Codex could see raw delimiter/output syntax; promotion would be unsafe when the tool name is absent | Implemented marker stripping without unsafe promotion; fixture `fixtures/regressions/deepseek_v3_partial_marker_strip_20260528.json` |
| JSON `tool_calls` objects using `function.parameters` | Schema/parser | `json_tool_calls_bait` run 0 capture `runs\deepseek_v2_lite_open_gate_repair_full_r3\captures\20260528-031149-691578-proxy-b74ab5cb.json` | `{"tool_calls":[{"function":{"name":"shell","parameters":{...}}}]}` | OpenGate treated arguments as empty, then returned a diagnostic shell call instead of the intended command | Implemented in JSONish tool-call normalization; fixture `fixtures/regressions/json_tool_calls_function_parameters_20260528.json` |
| Diagnostic tool call after negative tool intent | Command-quality | `no_tool_xml_example_bait` run 0 capture `runs\deepseek_v2_lite_open_gate_repair_full_r3\captures\20260528-031227-357438-proxy-bdbbb9b8.json` and `no_tool_json_example_bait` run 0 capture `runs\deepseek_v2_lite_open_gate_repair_full_r3\captures\20260528-031229-899821-proxy-558d5c3d.json` | User asked for documentation/no tools; OpenGate stripped sample syntax, promotion was blocked as `negative_tool_intent`, then actionable-output fallback added a diagnostic `shell` call | A no-tool request became an over-eager tool call | Implemented by gating actionable-output fallback on tool-promotion eligibility; fixture `fixtures/regressions/negative_tool_intent_no_actionable_tool_20260528.json` |
| Live Codex namespace tool schemas after request-diet compaction | Protocol | Initial live run `runs\codex-live\20260527-235147-deepseek_v2_lite_live_smoke_repair_spoon-repair`; follow-up live runs `runs\codex-live\20260528-164449-deepseek_v2_lite_live_smoke_repair_spoon_namespace_tools-repair` and `runs\codex-live\20260528-164649-deepseek_v2_lite_live_smoke_repair_spoon_namespace_tools_workspace-repair` | Codex forwarded MCP namespace tools with nested child tools, but request compaction dropped the nested `tools` array while preserving `type = "namespace"` | vLLM returned HTTP 400 before generation | Implemented: compacted namespace schemas retain nested tools recursively; latest live runs have `0` upstream errors |
| Bare PowerShell alias as shell executable | Command-quality | Workspace live run `runs\codex-live\20260528-164649-deepseek_v2_lite_live_smoke_repair_spoon_namespace_tools_workspace-repair`; verified by `runs\codex-live\20260528-165042-deepseek_v2_lite_live_smoke_repair_spoon_namespace_alias_workspace-repair` | Model emitted a promoted `shell` call with `command = ["dir"]` | Codex on Windows tries to execute `dir` as a program and fails before the PowerShell alias can resolve | Implemented: direct PowerShell cmdlet repair also recognizes common aliases and wraps them in `powershell.exe -Command ...` |
| Remaining missed or wrong-tool behavior | Behavior | Post-repair leak-bait and wrong-tool-bait misses | Model explains, declines, or misses tool use even when output is leak-free | No Codex-visible leak or invalid call, but not a strict benchmark success | Document only unless a new protocol/parser/schema/command-quality shape appears |

## Compatibility State

Current state: `synthetic-repaired; live behavior-limited`.

OpenGate now repairs the accepted synthetic DeepSeek parser/schema/actionable-output failures and the live namespace schema compaction failure without model-name branching. The model should not be marked `known-good` for live Codex because the latest smoke still shows behavior-quality issues in no-tool/documentation output. Decision: park this model here. The remaining issue is model behavior, and OpenGate should not add task-steering or model-behavior repair for this target.

## Failure Classification Rules

- **Protocol**: vLLM rejects Codex-style roles, tool history, tool schemas, or Responses input before meaningful generation.
- **Parser**: model emits tool syntax as assistant/reasoning text instead of structured calls.
- **Schema**: structured calls exist but violate tool argument schemas.
- **Command-quality**: structured calls parse but would fail Codex policy or runtime checks.
- **Behavior**: wrong tool choice, planning loops, stalls, or task-progress drift.

Only protocol, parser, schema, and command-quality failures are OpenGate repair candidates. Behavior-only failures should be documented without task-steering repair logic.

## Acceptance Criteria

- Direct vLLM baselines are recorded before OpenGate claims are made.
- OpenGate `repair` returns zero assistant-text or reasoning tool-call leaks.
- OpenGate returns zero invalid structured tool calls and zero error-level command-quality issues to Codex.
- Any new repair is model-agnostic and backed by a real capture or benchmark failure shape.
- Live Codex smoke must reach meaningful model generation and complete without upstream schema errors before the model is marked known-good.
