# Changelog

Open Gate uses semantic versioning while the project is pre-1.0:

- Patch releases fix bugs without changing CLI or fixture behavior.
- Minor releases may add proxy modes, report fields, fixture schemas, or benchmark suites.
- Breaking changes can still happen before 1.0 and should be called out here.

## Unreleased

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
