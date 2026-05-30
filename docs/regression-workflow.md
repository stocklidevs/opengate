# Regression Workflow

Open Gate regressions replay captured upstream model responses through the normalizer. This keeps real model failures reproducible without needing the local model online.

## Create A Fixture

Use a proxy capture that contains an upstream response:

```powershell
python -m open_gate.capture_to_fixture captures\20260509-123610-677429-proxy-c9b21604.json --name qwen_nested_powershell_20260509
```

By default the fixture keeps the latest user input and only the tools used by the upstream response. Use `--full-request` when debugging request-shape behavior that depends on the whole Codex prompt.

Fixtures are written to `fixtures\regressions\`. Each fixture contains:

- `request`: the minimal request context needed by normalization.
- `upstream_response`: the raw model response to replay.
- `expected`: assertions such as no text leaks, no invalid tool calls, no command quality issues, expected or absent output fragments, and minimum repair counts.
- `observed_after_normalization`: the normalized behavior observed when the fixture was created.

## Replay Fixtures

```powershell
python -m open_gate.regression --pretty
```

The command exits non-zero if any fixture fails. It is intentionally independent from vLLM and Codex so it can run quickly in CI or before sharing a benchmark report.

## First Real Regression

`fixtures\regressions\qwen_nested_powershell_20260509.json` comes from the Codex tool-call smoke. Qwen emitted:

```json
{"command":"powershell.exe -Command \"Get-ChildItem -Force | Measure-Object | Select-Object -ExpandProperty Count\""}
```

The old proxy converted that to a nested command array:

```json
["powershell.exe","-Command","powershell.exe -Command \"Get-ChildItem -Force | Measure-Object | Select-Object -ExpandProperty Count\""]
```

Codex rejected it by policy. The current proxy repairs it to:

```json
["powershell.exe","-Command","Get-ChildItem -Force | Measure-Object | Select-Object -ExpandProperty Count"]
```

The benchmark scorer also counts the unrepaired version as `command_quality_issue`, so future baseline reports can separate "tool call exists" from "tool call Codex will actually accept."
