# Open Gate

![Version](https://img.shields.io/badge/version-0.3.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)
![API](https://img.shields.io/badge/API-Responses-111827)
![Proxy Modes](https://img.shields.io/badge/proxy-repair%20%7C%20observe-16A34A)
![Platform](https://img.shields.io/badge/platform-Windows%20first-7C3AED)

Open Gate is a local harness and proxy for making open coding models behave like a Responses API agent backend for Codex. It captures real Codex traffic, detects tool-call leakage, repairs common open-model tool-call failures, and produces repeatable baseline reports that other home-lab users can compare.

Current release: `0.3.0`. See `CHANGELOG.md` for release notes and `docs\release-process.md` for versioning.

## Current Shape

- `open_gate.server` runs a fake `/v1/responses` and `/v1/chat/completions` server.
- `open_gate.server --upstream-base-url ...` or `python -m open_gate --upstream ...` runs buffered-upstream `/v1/responses` proxy mode.
- Proxy mode supports `--normalization-mode repair` and `--normalization-mode observe`.
- Proxy mode defaults to `--upstream-input-mode auto`, which flattens multi-turn Codex Responses history when vLLM rejects native item types.
- Streamed proxy requests emit SSE heartbeat comments while waiting for vLLM, then replay the normalized response as Responses SSE events.
- Every request is written to `captures/` with sensitive headers redacted.
- `open_gate.linter` extracts leaked tool calls from XML tags, JSON tool-call arrays, fenced JSON, and Pythonic `functions.tool({...})` calls.
- `open_gate.command_quality` detects shell commands that are structured but likely to be rejected by Codex policy, starting with nested PowerShell.
- `open_gate.regression` replays captured upstream responses through normalization as stable fixtures.
- `open_gate.codex_report` summarizes live Codex JSONL output and proxy captures.
- Fixtures in `fixtures/leaks/` model common bad outputs from open-model tool-call formats.

## Run The Capture Server

```powershell
python -m open_gate.server --host 127.0.0.1 --port 8765
```

Proxy mode can also be started through the package entrypoint:

```powershell
python -m open_gate --upstream http://127.0.0.1:8001/v1 --host 127.0.0.1 --port 8765
```

Use `repair` for normal usage and `observe` to capture what Open Gate would fix while returning the raw upstream response:

```powershell
python -m open_gate --upstream http://127.0.0.1:8001/v1 --normalization-mode observe
```

Use `--upstream-input-mode native` only when the upstream server fully supports Codex-style multi-turn Responses input. vLLM may reject assistant history, function-call items, or tool-output items unless Open Gate flattens that history first.

Use `--stream-heartbeat-seconds` to tune keepalive comments for streamed Codex requests. The default is `5.0`, which keeps Codex from seeing a silent socket while Qwen/vLLM spends a minute or more producing a large tool call.

Use a temporary Codex provider/profile that points at `http://127.0.0.1:8765/v1` with `wire_api = "responses"`. Your current real model endpoint can stay as:

```toml
[model_providers.qwen_local]
name = "Qwen3-Coder-Next via vLLM"
base_url = "http://127.0.0.1:8001/v1"
wire_api = "responses"
```

For capture-only probing, use a local provider like:

```toml
[model_providers.open_gate_capture]
name = "Open Gate capture"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"

[profiles.open_gate_capture]
model_provider = "open_gate_capture"
model = "open-gate-probe"
model_context_window = 32768
model_supports_reasoning_summaries = false
```

Then run:

```powershell
codex --profile open_gate_capture -C "C:\Users\example\source\repos\glm-test"
```

In this sandboxed harness, detached background processes can be cleaned up between commands. The probe scripts keep the server alive only for the duration of the request:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_http_probe.ps1
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_codex_capture_probe.ps1
```

Summarise the newest captured request:

```powershell
python -m open_gate.inspect_capture --pretty
```

## Lint A Fixture

```powershell
python -m open_gate.lint fixtures\leaks\qwen_xml_tool_call.txt --tools fixtures\tools\codex_like_tools.json --pretty
```

## Benchmark Tool Calls

The Qwen baseline used vLLM serving `cyankiwi/Qwen3-Coder-Next-AWQ-4bit` as `Qwen3-Coder-Next`. Full setup notes are in `docs\vllm-notes.md`.

Run a raw baseline against the GX10 vLLM server:

```powershell
python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Qwen3-Coder-Next --suite fixtures\benchmarks\codex_shell_smoke.json --runs 3 --label qwen_direct --output runs\qwen_direct.json
```

Run a harder leakage-bait suite:

```powershell
python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Qwen3-Coder-Next --suite fixtures\benchmarks\codex_tool_leak_stress.json --runs 3 --label qwen_direct_stress --output runs\qwen_direct_stress.json
```

Run the broader serious baseline:

```powershell
python -m open_gate.benchmark --base-url http://127.0.0.1:8001/v1 --model Qwen3-Coder-Next --suite fixtures\benchmarks\qwen_serious_tool_stress.json --runs 3 --label qwen_direct_serious_r3 --output runs\qwen_direct_serious_r3.json --summary-only
```

Run the same benchmark through Open Gate proxy mode:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_proxy_benchmark.ps1
```

Direct Qwen scored `43/60` strict successes on the serious suite. The first Open Gate proxy baseline scored `60/60` on the same suite. See `docs\benchmark-notes.md`.

For interactive Codex usage, see `docs\interactive-codex.md`.

The key summary fields are `strict_successes_rate`, `leaks_rate`, `argument_leaks_rate`, `proxy_recoverable_rate`, `missed_tool_calls_rate`, and `invalid_tool_calls_rate`. A leaked but parseable tool call is counted as a failure for the raw backend and as `proxy_recoverable`, which is the number Open Gate should drive toward a structured success.

`command_quality_issues_rate` is stricter than basic tool-call validity. It catches structured commands that are likely to fail inside Codex even though they parse as valid JSON, such as `powershell.exe -Command` nested inside another PowerShell command.

Probe request-size behavior without generation:

```powershell
python -m open_gate.payload_probe --base-url http://127.0.0.1:8001/v1 --model Qwen3-Coder-Next
```

Summarise a benchmark report by category and case:

```powershell
python -m open_gate.summarize_report runs\qwen_direct_serious_r3.json --pretty
```

Observed local results are recorded in `docs\benchmark-notes.md` and `docs\vllm-notes.md`.

## Live Codex Benchmark

Run actual `codex exec` prompts through Open Gate:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Mode repair -Runs 3
```

Run the same suite in raw-observation mode:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 -Mode observe -Runs 3 -Label codex_live_observe
```

Summarise an existing live run:

```powershell
python -m open_gate.codex_report runs\codex-live\<run-id>\captures --codex-dir runs\codex-live\<run-id> --pretty --summary-only
```

Live benchmark details are in `docs\live-codex-benchmark.md`.

Latest local smoke result:

| Metric | Repair | Observe |
| --- | ---: | ---: |
| Codex turns completed | 3/3 | 3/3 |
| Policy-blocked Codex runs | 0 | 1 |
| Returned command-quality issues | 0 | 1 |
| Returned invalid tool calls | 0 | 1 |
| Returned clean capture rate | 100% | 42.86% |

## Capture Regressions

Turn a proxy capture into a replayable fixture:

```powershell
python -m open_gate.capture_to_fixture captures\20260509-123610-677429-proxy-c9b21604.json --name qwen_nested_powershell_20260509
```

Replay all regression fixtures:

```powershell
python -m open_gate.regression --pretty
```

The first real fixture locks in the nested PowerShell repair seen during interactive Codex smoke testing. See `docs\regression-workflow.md`.

## Verify

```powershell
python -m unittest discover -s tests
python -m open_gate.regression --pretty
```

The first Codex capture showed `POST /v1/responses` with `stream: true`, three input messages, and ten tools. See `docs/codex-capture-notes.md`.

## Versioning

Open Gate uses semantic versioning before `1.0`. Keep `VERSION`, `pyproject.toml`, and `open_gate\version.py` in sync. The current version is `0.3.0`.

## Next Milestone

The next step is to expand `fixtures\codex_live\smoke.json` into a broader live coding suite and publish paired `observe` vs `repair` reports for Qwen3-Coder-Next.
