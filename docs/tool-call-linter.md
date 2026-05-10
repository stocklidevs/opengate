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

The linter currently reports:

- `nested_powershell`: `powershell.exe -Command` wrapped inside another PowerShell `-Command`.
- `windows_powershell_chain_operator`: `&&` used under Windows PowerShell.
- `powershell_here_string_header`: a here-string header followed by escaped `` `n `` text instead of a real newline.
- `python_compound_statement_one_liner`: `python -c` with compound statements such as `async def` packed after semicolons.
- `uv_run_playwright_entrypoint`: `uv run playwright ...` before the Playwright console script is known to exist.
- `relative_cd_without_workdir`: inline relative `cd` instead of the shell tool's `workdir`.
- `nested_relative_cd`: inline `cd` into the same directory already provided as `workdir`.
- `view_image_non_image_path`: `view_image` pointed at a path without a known image extension.
- `skill_file_as_mcp_resource`: a Codex skill file attempted through `read_mcp_resource`.

## Proxy Metadata

Proxy captures include command-quality telemetry in `normalization`:

- `upstream_command_quality_issues`: issues found before Open Gate repair.
- `normalized_command_quality_issues`: issues that remain after repair/promotion.

Repair mode may fix safe command-shape problems such as nested PowerShell or JSON-array encoded PowerShell. It does not rewrite risky shell semantics such as replacing `&&` with `;`.

## CLI Usage

```powershell
python -m open_gate.lint fixtures\leaks\qwen_xml_tool_call.txt --tools fixtures\tools\codex_like_tools.json --pretty
```

The output includes `command_quality_issues` next to parsed leaked tool calls.
