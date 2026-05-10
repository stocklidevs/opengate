# Changelog

Open Gate uses semantic versioning while the project is pre-1.0:

- Patch releases fix bugs without changing CLI or fixture behavior.
- Minor releases may add proxy modes, report fields, fixture schemas, or benchmark suites.
- Breaking changes can still happen before 1.0 and should be called out here.

## Unreleased

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
