# Tool-Call Quality Linter

Open Gate has two layers of model-output checks:

- `open_gate.linter` parses leaked tool-call syntax from assistant text and reasoning.
- `open_gate.command_quality` inspects structured tool calls that already parse as JSON but are likely to fail when Codex executes them.

## Why This Exists

Some open models successfully emit a Responses `function_call`, but the call is still operationally bad. Qwen3-Coder-Next exposed this during live Codex testing: the proxy and vLLM returned HTTP 200 responses, but the model repeatedly chose commands that failed in Windows PowerShell or called tools with impossible arguments.

These failures should be measured separately from JSON leakage:

- Leakage: the model printed tool syntax in text or reasoning.
- Invalid call: the tool arguments fail schema validation.
- Command-quality issue: the call is structured but likely to fail at execution time.

## Current Rules

The leakage parser recognizes:

- XML-ish `<tool_call>` and `<tool_calls>` blocks, including GLM `<arg_key>/<arg_value>` payloads.
- DeepSeek/vLLM delimited function blocks, including partial close/output marker stripping when a safe tool name cannot be recovered.
- Bare `recipient_name=functions.*` response headers.
- Fenced or raw JSON tool-call objects and arrays when they parse cleanly.
- Pythonic `functions.tool({...})` text.

The linter currently reports:

- `nested_powershell`: `powershell.exe -Command` wrapped inside another PowerShell `-Command`.
- `executable_only_command`: a shell call invokes only `powershell.exe`, `pwsh`, or `cmd` instead of providing the actual script. This often appears when a model leaks useful command content into `prefix_rule`, `sandbox_permissions`, or `justification`.
- `split_powershell_command`: `powershell.exe -Command` followed by split parameter array items instead of one script string.
- `direct_powershell_cmdlet`: a bare PowerShell cmdlet or alias such as `Write-Host`, `Set-Content`, or `dir` used as the executable.
- `windows_powershell_chain_operator`: `&&` used under Windows PowerShell.
- `powershell_here_string_header`: a here-string header followed by escaped `` `n `` text instead of a real newline.
- `malformed_powershell_here_string`: a file write uses invalid or placeholder here-string syntax instead of a real PowerShell here-string with complete content.
- `bare_here_string_file_write`: a PowerShell here-string contains the artifact body, but the command forgot the `Set-Content` cmdlet and only includes `-Path`/`-Encoding` arguments.
- `malformed_json_array_command`: malformed JSON-array text passed as a PowerShell `-Command` script. If the nested array is otherwise recoverable, Open Gate can unwrap it, including GLM-style uppercase `\N` newline escapes inside the encoded command.
- GLM sometimes places a full multi-line HTML document inside a quoted JSON-like `shell.command` array. Open Gate parses that relaxed array shape before falling back to string-command repair.
- GLM can also emit the full `index.html` body as a bare here-string followed by file parameters. Open Gate repairs that into a PowerShell `Set-Content` command so Codex receives a runnable tool call.
- OpenGate `0.6.10` also quarantines structured shell calls with error-level command-quality issues. Instead of silently dropping a bad structured call when assistant prose is present, OpenGate replaces the call with a safe diagnostic shell call such as `Write-Output 'Open Gate blocked...'`. That gives Codex a tool-output loop it can recover from.
- OpenGate `0.6.11` treats Codex `web_search` as a hosted upstream tool rather than a local client function. If a local model returns `web_search` as a normal tool call, OpenGate converts URL lookups into a bounded PowerShell metadata fetch through `shell`, including `site:domain` queries.
- OpenGate `0.6.12` blocks executable-only shell calls and strips approval metadata from diagnostic quarantines.
- OpenGate `0.6.15` quarantines malformed here-string placeholders before Codex executes them.
- OpenGate `0.6.17` keeps diagnostics generic by default and prefers a safe `shell` observation over `update_plan` when shell is available, avoiding task-specific artifact steering in normal proxy mode.
- OpenGate also treats JSON `function.parameters` as tool arguments when `function.arguments` is absent, matching DeepSeek/vLLM text-tool-call captures without adding model-name branches.
- Bare PowerShell aliases such as `dir`, `ls`, and `type` use the same repair path as direct cmdlets, so Codex receives `powershell.exe -Command ...` instead of trying to execute the alias as a program.
- `python_compound_statement_one_liner`: `python -c` with compound statements such as `async def` packed after semicolons.
- `uv_run_playwright_entrypoint`: `uv run playwright ...` before the Playwright console script is known to exist.
- `unbounded_web_fetch`: full-page web fetches that print whole HTML content into the model context.
- `empty_artifact_write`: `WriteAllText`, `Set-Content`, or equivalent PowerShell that creates/truncates a code or document artifact to empty content.
- `relative_cd_without_workdir`: inline relative `cd` instead of the shell tool's `workdir`.
- `nested_relative_cd`: inline `cd` into the same directory already provided as `workdir`.
- `view_image_non_image_path`: `view_image` pointed at a path without a known image extension.
- `skill_file_as_mcp_resource`: a Codex skill file attempted through `read_mcp_resource`.

## Proxy Metadata

Proxy captures include command-quality telemetry in `normalization`:

- `upstream_command_quality_issues`: issues found before Open Gate repair.
- `normalized_command_quality_issues`: issues that remain after repair/promotion.
- `text_tool_call_repairs`: leaked text tool calls whose arguments were repaired before promotion.
- `command_quality_suppressed_structured_calls`: structured calls removed because error-level command-quality issues remained after repair.

Repair mode may fix safe command-shape problems such as nested PowerShell, split PowerShell command arrays, bare PowerShell cmdlets or aliases, or JSON-array encoded PowerShell. Empty artifact writes and leaked shell calls with unrepaired command-quality errors are quarantined into harmless diagnostics so Codex receives feedback and can continue the normal loop without running the bad command. Diagnostic quarantines are deliberately minimal and do not preserve approval metadata from the blocked call. Hosted `web_search` calls are routed to bounded shell metadata fetches when a URL can be derived. Structured calls with remaining error-level issues are suppressed before Codex can execute them; Open Gate returns a short generic diagnostic instead of the bad tool call. It does not rewrite risky shell semantics such as replacing `&&` with `;`.

## CLI Usage

```powershell
python -m open_gate.lint fixtures\leaks\qwen_xml_tool_call.txt --tools fixtures\tools\codex_like_tools.json --pretty
```

The output includes `command_quality_issues` next to parsed leaked tool calls.

## Adversarial Validation

GLM can split XML-ish tag names across whitespace, for example `<tool_ca ll>` or `</ arg_key>`. The adversarial validator creates deterministic whitespace mutations of GLM-style tool calls and runs them through the full proxy normalizer:

```powershell
python -m open_gate.adversarial --iterations 300 --seed 6047
```

For broader local checks, run the validation loop:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_validation_loop.ps1 -Loops 3 -AdversarialIterations 300
```
