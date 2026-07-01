# Changelog

Open Gate uses semantic versioning while the project is pre-1.0:

- Patch releases fix bugs without changing CLI or fixture behavior.
- Minor releases may add proxy modes, report fields, fixture schemas, or benchmark suites.
- Breaking changes can still happen before 1.0 and should be called out here.

## Unreleased

## 0.7.2 - 2026-07-01

- Recover imitated Codex-transcript tool calls whose JSON body is unterminated. Some models (observed with Qwen3.6) emit a `assistant tool call <name> ...:` header followed by a JSON object that is missing its closing brace, then trailing XML/fence junk (`</parameter></function></tool_call>`). Strict `raw_decode` failed, so the block was detected-and-stripped but no call was extracted or promoted, leaving a bland final assistant message with no tool call — which ends the Codex turn prematurely. The linter now balances the open brackets and trims the trailing junk, so the call is recovered, promoted to a structured `function_call`, and the turn continues. Also strips the residual close-tags from the cleaned assistant text.
- Benchmark runner (`run_codex_live_benchmark.ps1`): added `-ModelContextWindow`, which passes `-c model_context_window=<n>` to `codex exec` so Codex's native compaction is aware of the served model's real window instead of a wrong default.

## 0.7.1 - 2026-06-30

- `write_file` now emits a one-line stdout confirmation (`wrote <n> bytes to <path>`) after a successful write. `WriteAllBytes` is silent, so the translated `shell` call previously returned an empty tool result; some models (observed with Qwen3-Coder-Next on a multi-file build) read the empty result as a failed write and re-issued the same `write_file` call in a degenerate loop, never advancing past the first file. The explicit confirmation gives positive feedback so the model proceeds. No effect unless the `write_file` tool is enabled.

## 0.7.0 - 2026-06-30

- Added an optional `write_file(path, content)` tool (`--write-file-tool` / `[proxy] write_file_tool`). When enabled, Open Gate injects the tool into the upstream request so local models write files via structured JSON arguments instead of fragile PowerShell here-strings, and advertises it in the tool-discipline guardrail (previously `write_file` was warned against as unavailable). Each returned `write_file` call is translated into a robust base64 `shell` write before Codex sees it, so Codex still only ever receives `shell`. Adds the `write_file_translations` normalization telemetry field. Default off; no behavior change unless enabled. Motivated by repeated local-model failures writing large quote-heavy source files through the shell.

## 0.6.20 - 2026-05-30

- Added the Gemma-4-E4B-IT adaptation results, including direct baselines, OpenGate repair scores, capture-backed repairs, and a clean live Codex smoke gate.
- Added a generic `<channel|>` assistant-text cleanup that keeps the final non-empty suffix and records `channel_delimiter_text_repairs` telemetry, so Gemma-style visible answer prefaces do not leak into Codex-visible final text.
- Extended Gemma-backed parser and command-quality coverage for fenced JSON `toolSpec` wrappers, pipe-style unavailable skill calls, Codex transcript-imitation tool-call blocks, one-item PowerShell script arrays, direct PowerShell aliases/cmdlets with path arguments, and malformed escaped JSON-tail command arrays.
- Extended live Codex reporting and regression fixtures to track channel-delimiter text repairs and assert that repaired output fragments are absent when expected.
- Recorded the larger Gemma software-build load as not passed and parked Gemma for Codex use beyond smoke: after parser repairs, the foreground run hit upstream timeout/connection-reset failures, executed no commands, and produced no artifacts.

## 0.6.18 - 2026-05-29

- Added the DeepSeek-Coder-V2-Lite adaptation results: direct baseline, OpenGate repair scores, live smoke evidence, and a cross-model scorecard entry that parks the model as behavior-limited rather than known-good.
- Fixed request-diet compaction for Codex MCP namespace tools by preserving nested child tool schemas, removing the live vLLM HTTP 400 namespace blocker.
- Extended command-quality repair for bare PowerShell aliases such as `dir`, wrapping them through `powershell.exe -Command ...` so Windows Codex runs do not try to execute aliases as standalone programs.
- Kept Qwen3.6 parked as a benchmark target and removed Qwen3.6-specific runtime/test regression paths that crossed into task-progress steering.

## 0.6.17 - 2026-05-12

- Removed the default Qwen3.6 artifact-pressure/task-steering path: OpenGate no longer blocks `update_plan` because an artifact appears pending, no longer injects "write the complete file now" pressure into spoon context, and no longer tracks artifact completion state.
- Changed OpenGate diagnostics to prefer safe `shell` observations before `update_plan`, so proxy feedback does not appear as model-authored plan updates when shell is available.
- Stopped inferring file writes from raw artifact-looking shell strings plus a requested prompt target; OpenGate now keeps default repair focused on explicit command-shape fixes.
- Kept generic command-quality protections such as executable-only shell detection, malformed here-string quarantine, empty artifact-write quarantine, bounded web metadata routing, protocol adaptation, request diet, and captures.

## 0.6.16 - 2026-05-12

- Added `upstream_max_output_tokens` config/CLI support, defaulting to `4096`, so local models cannot spend an entire turn generating oversized artifacts before timing out.
- Added compact artifact-size guidance to artifact recovery diagnostics, keeping requested files target-agnostic while discouraging huge single-turn generations.
- Changed OpenGate-generated diagnostic feedback to prefer `update_plan` when Codex advertises it, avoiding no-op diagnostic shell calls that can stall before the model receives feedback.
- Kept a quote-safe fallback for shell-only sessions by emitting PowerShell `-EncodedCommand` diagnostics with base64-carried messages.
- Made hosted `web_search` routing artifact-aware: URL lookups still become bounded shell metadata fetches for research-only turns, but artifact-building turns get an `update_plan` diagnostic telling the model to stop fetching and write the requested file.
- Updated regression replay to decode encoded OpenGate diagnostic commands when checking expected output fragments.

## 0.6.15 - 2026-05-12

- Fixed artifact state tracking so an attempted write only clears artifact pressure after the matching tool output succeeds; failed writes such as PowerShell parser errors keep the requested artifact pending.
- Prioritized artifact-progress recovery before the generic "reasoning only" recovery, so reasoning-only turns after artifact failures get file-specific guidance.
- Added command-quality detection for malformed PowerShell here-string/file-content placeholders such as `-Value @```ENDOFHTML``@`, quarantining them before Codex executes the bad command.
- Added regression coverage for Qwen3.6's latest Refero/index.html failure: reasoning-only recovery, malformed file-write quarantine, and failed-write pending state.

## 0.6.14 - 2026-05-12

- Generalized artifact-pressure and recovery diagnostics from `index.html` to the requested target file, so tasks like `main.cpp`, `app.py`, or `README.md` get file-specific guidance.
- Added artifact target detection for common source-code extensions, including C, C++, C#, Go, Java, Kotlin, Rust, shell, SQL, Swift, and related header/script files.
- Added regression coverage proving plan-blocking, prose-only recovery, spoon constraints, and executable-only shell recovery use `main.cpp` without leaking `index.html`-specific instructions.

## 0.6.13 - 2026-05-11

- Added artifact-pressure constraints in spoon mode after exhausted web/research attempts, telling the model to stop planning and write the requested `index.html` directly.
- Quarantined non-productive `update_plan` calls when artifact creation is pending after a prior OpenGate web/policy diagnostic.
- Added regression coverage for the Qwen3.6 failure where the model updated the plan after metadata was already available, then timed out on the next artifact turn.

## 0.6.12 - 2026-05-11

- Added `executable_only_command` command-quality detection for shell calls that only invoke `powershell.exe`, `pwsh`, or `cmd` without a real script.
- Made command-quality quarantines strip approval metadata such as `prefix_rule`, `sandbox_permissions`, and `justification` from safe diagnostic shell calls.
- Added artifact-aware command-quality recovery text that tells the model to write the complete `index.html` in one valid shell command after malformed artifact-write attempts.
- Updated tool guardrails so upstream models are explicitly told not to put approval metadata inside shell commands.

## 0.6.11 - 2026-05-11

- Added schema-aware handling for Codex's hosted `web_search` tool shape, including type-only tool specs such as `{"type":"web_search"}`.
- Converted upstream `web_search`/browser-style URL calls into bounded PowerShell `shell` metadata fetches, because Codex CLI does not execute returned `function_call` items named `web_search`.
- Added URL cleanup and `site:domain` query handling for web-search-shaped model calls.
- Added a non-artifact repeated-URL terminal message so failed URL inspection tasks end cleanly instead of looping through diagnostic shell calls.

## 0.6.10 - 2026-05-11

- Quarantined structured shell calls with command-quality errors into safe diagnostic shell calls instead of dropping them when assistant prose is also present.
- Added capture reporting for `structured_command_quality_quarantines`.
- Recorded the Qwen3.6 live stuck-feeling case where an unbounded reference-site fetch was correctly blocked but previously left Codex without actionable tool feedback.

## 0.6.9 - 2026-05-11

- Added upstream capability probing for Responses protocol support, including user input, `developer` role, `system` role, and native tool-call history.
- Decoupled protocol adaptation from spoon context compression: `--upstream-input-mode auto` can now flatten unsupported instruction roles even when `--context-policy full` is active.
- Added a native-request retry path that automatically retries flattened input when an upstream server returns role/history validation errors such as `Unexpected message role`.
- Made tool-discipline guardrail injection role-aware so OpenGate can avoid adding a `developer` message when probes show that the upstream rejects that role.
- Updated benchmark reports to write partial output after every case and classify protocol incompatibilities separately from model/tool-call failures.
- Updated live/proxy benchmark harnesses to wait for capability-probed OpenGate startup and expose capability probe controls.
- Added capture reporting for unrecoverable stripped tool syntax, separating "OpenGate cleaned leaked text" from "OpenGate confidently promoted a tool call."

## 0.6.8 - 2026-05-11

- Added Qwen3.6-27B setup notes with the vLLM serving command, OpenGate autodetection expectations, and ready-to-run benchmark commands.
- Updated the README and vLLM notes so the next model adaptation has documented setup, benchmark, and acceptance criteria before live validation begins.
- Recorded the first Qwen3.6-27B direct smoke result: `9/9` strict successes with zero leaks, invalid calls, or HTTP errors at `max_model_len = 65536`.

## 0.6.7 - 2026-05-10

- Added the friendly `opengate` console command alongside the existing `open-gate` command.
- Added TOML config loading with `opengate.toml`, `open-gate.toml`, `.opengate.toml`, `~/.opengate/config.toml`, and `OPENGATE_CONFIG` discovery.
- Added an `opengate.example.toml` template and ignored local `opengate.toml` files for machine-specific vLLM endpoints.
- Added upstream model autodetection from `GET /v1/models` when `model = "auto"`.
- Added upstream model rewriting so Codex can keep a stable OpenGate profile while OpenGate forwards requests to whichever model vLLM is currently serving.
- Added a startup banner showing the OpenGate version, listener URL, active flags, descriptions, and current values.

## 0.6.6 - 2026-05-10

- Replaced comment-only streamed keepalives with real Responses `response.in_progress` heartbeat events while Open Gate waits on buffered upstream vLLM output, avoiding Codex's five-minute SSE idle retry path on very slow local-model generations.
- Added repair and command-quality detection for GLM's bare PowerShell here-string file-write shape, where the model emits the full `index.html` body followed by `-Path ... -Encoding ...` but omits the `Set-Content` cmdlet.
- Added focused regression coverage for streamed lifecycle continuation and bare here-string artifact repair.
- Updated live-run documentation to distinguish Open Gate normalization failures from Codex sandbox/policy failures.

## 0.6.5 - 2026-05-10

- Added command-quality detection for empty artifact writes, including GLM's repeated `WriteAllText('index.html', '')` placeholder calls.
- Added a quarantine repair that rewrites empty artifact writes into harmless diagnostic shell calls, preserving Codex's tool-output loop without truncating the target file.
- Added diagnostic quarantine for leaked shell calls with unrepaired command-quality errors, such as full-page `curl` fetches, so Codex gets tool feedback and the model can continue instead of ending on cleaned text.
- Added tolerant parsing for GLM's large multi-line shell command arrays, where the HTML body appears as raw newlines inside a quoted JSON-like `command` value.
- Increased the proxy CLI's default upstream timeout to 420 seconds for large local-model code-generation turns, while SSE heartbeats continue to keep Codex connected.
- Extended the spoon/tool guardrails and context constraints so repeated empty-placeholder writes feed back as a compact "write the complete artifact" instruction.
- Updated the interactive proxy launch docs with the GLM-focused spoon command and longer upstream timeout.

## 0.6.4 - 2026-05-10

- Added live Codex software-build fixture cases for a CSV expense CLI, incident-log triage CLI, and single-file habit tracker app.
- Added per-case live benchmark working directories, sandbox selection, Codex last-message capture, and timeout-bounded case execution.
- Added prompt-visible sandbox preflight to the live Codex benchmark, with `-FailOnPromptSandboxMismatch` to skip poisoned runs where Codex tells the model a different sandbox than the harness requested.
- Added tolerant repair for GLM nested PowerShell JSON-array calls that contain uppercase `\N` newline escapes inside the encoded command.
- Fixed negative-tool-intent detection so words such as "sample" in artifact names or sample commands no longer block valid tool-call promotion.
- Updated live reporting so `last-*.txt` final-message files are not counted as Codex JSONL run streams.

## 0.6.3 - 2026-05-10

- Added policy protection for `spawn_agent`: Open Gate now warns upstream models not to call it unless the user explicitly asks for subagents, and suppresses/promotes leaked calls accordingly.
- Added validation for `spawn_agent.agent_type`, allowing only `default`, `explorer`, or `worker`.
- Added command-quality detection for malformed JSON-array text passed as a PowerShell `-Command` script.
- Blocked promotion of leaked text tool calls that still contain unrepaired command-quality errors after schema repair.
- Added repair for GLM/Qwen shell calls that split PowerShell `-Command` across array items, such as `["powershell.exe","-Command","Set-Content","-Path",...]`.
- Added repair for bare PowerShell cmdlets such as `["Write-Host","loading"]`, wrapping them as `powershell.exe -Command ...`.
- Added suppression for structured tool calls with remaining error-level command-quality issues, including full-page web fetches that would dump whole HTML into context.

## 0.6.2 - 2026-05-10

- Added an upstream request diet stage that can digest oversized Codex instructions and compact oversized tool schemas before forwarding to vLLM.
- Added `--instruction-policy full|auto|digest` and `--tool-schema-policy full|auto|compact`; both default to `auto`.
- Added request-size metadata to proxy captures, including original/sent instruction and tool-schema character counts plus final upstream body size.
- Preserved transformed upstream request metadata on upstream timeouts by returning timeout responses through the normal proxy-result capture path.
- Added command-quality detection for unbounded full-page web fetches such as `Invoke-WebRequest ... | Select-Object -ExpandProperty Content`.
- Extended helper scripts and health checks with request-diet policy settings.

## 0.6.1 - 2026-05-10

- Added upstream tool-discipline guardrails for native and flattened requests, so open models see the exact callable tool names before choosing a tool.
- Explicitly warns local models not to invent common aliases such as `web_search`, `browser`, `fetch`, `write_file`, `read_file`, or `apply_patch` unless those names are actually advertised by Codex.
- Strengthened the spoon context header with the same structured-tool-only and unavailable-tool guidance.
- Added regression coverage for the GLM live failure where the model emitted `<tool_call>web_search...` even though Codex had only advertised tools such as `shell` and `update_plan`.

## 0.6.0 - 2026-05-10

- Added model-agnostic recovery for GLM-style leaked `<tool_call>tool<arg_key>...<arg_value>...</arg_value></tool_call>` assistant text.
- Added recovery for bare `recipient_name=functions.*` response headers and residual syntax scrubbing for `recipient_name`, `<response>`, and unparsable tool-call documentation blocks.
- Normalization now sanitizes reasoning text and top-level `output_text` in addition to assistant message content.
- Repairable leaked calls are promoted after schema cleanup, so string `shell.command` values and extra disallowed arguments can become valid structured calls.
- Added Open Gate health metadata for version/model/context policy and hardened `scripts\run_proxy_benchmark.ps1` against stale proxy ports.
- Added a deterministic adversarial validation loop for GLM tag whitespace mutations so malformed tags are tested through the full proxy normalizer rather than patched one sample at a time.
- GLM-4.7-Flash serious-suite result improved from direct `2/20` strict successes with `18/20` leaks to Open Gate `repair/full` `20/20` strict successes with zero leaks. `repair/spoon` reached `19/20` with zero leaks; the remaining miss is an incomplete fenced JSON block that Open Gate intentionally does not guess.

- Documented the first `GLM-4.7-Flash` direct baseline alongside the Qwen benchmark notes.
- Added the GLM vLLM serving command and current parser flags to the vLLM notes.
- Fixed the proxy benchmark runner so its Open Gate server uses the requested `-Model` instead of the original Qwen default, and added context-policy flags.
- Documented the first GLM `repair/full` and `repair/spoon` benchmark results.

## 0.5.0 - 2026-05-10

- Added `--context-policy spoon`, a budgeted context compiler for Codex Responses history before forwarding to vLLM.
- Added context capture metadata for original flattened size, budgeted size, summarized items, exact recent items, and dropped context characters.
- Added durable user-constraint extraction so requirements like `Everything must be contained in index.html` survive long compiled histories.
- Added tool-failure constraint extraction so repeated Codex turns can carry compact reminders about unsupported tools, unavailable dependencies, bad PowerShell patterns, and timeouts.
- Added repair for PowerShell here-string commands that use escaped `` `n`` after the here-string header.
- Added command-quality detection for shell commands that print a full HTML document to stdout instead of writing `index.html`.
- Added repair for Bash heredoc file writes emitted inside Windows PowerShell commands.
- Fixed PowerShell `&&` detection so JavaScript `&&` inside a here-string is not reported as a shell chain operator.
- Added large recent tool-output summarization and completed diagnostic responses for upstream failures to reduce Codex retry storms.
- Added context-size fields to `open_gate.codex_report`.
- Documented the spoon-feed mode for long interactive Codex runs against local open models.

## 0.4.0 - 2026-05-09

- Added command-quality lint rules for Windows PowerShell chain operators, bad here-string headers, Python compound one-liners, relative `cd` usage, `uv run playwright`, non-image `view_image` paths, and skill files read as MCP resources.
- Added repair support for PowerShell commands encoded as JSON arrays inside another PowerShell `-Command` string.
- Added upstream and normalized command-quality issue metadata to proxy normalization captures.
- Added command-quality issue output to `python -m open_gate.lint`.

## 0.3.0 - 2026-05-09

- Added SSE heartbeat comments for streamed Codex requests while Open Gate waits on buffered upstream vLLM responses.
- Added proxy timing metadata and live-report summary fields for request duration and heartbeat counts.
- Added automatic upstream input flattening for vLLM `/v1/responses` requests that contain Codex assistant history, function calls, or tool outputs.
- Added reporting for flattened upstream requests.
- Added the first Qwen3-Coder-Next known-good compatibility note and model adaptation checklist.

## 0.2.0 - 2026-05-09

- Added `repair` and `observe` proxy modes.
- Added live Codex benchmark suite and PowerShell runner.
- Added `open_gate.codex_report` for capture and Codex JSONL summaries.
- Added real-trace regression replay for the nested PowerShell repair.
- Added command-quality scoring for structured tool calls that Codex may reject.
- Added project version metadata and release notes.

## 0.1.0 - 2026-05-09

- Added capture server for Responses and Chat Completions API requests.
- Added buffered Responses proxy mode for local OpenAI-compatible model servers.
- Added tool-call leakage linter and synthetic benchmark suites.
- Added vLLM payload probing and capture inspection helpers.
