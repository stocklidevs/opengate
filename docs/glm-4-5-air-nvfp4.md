# GLM-4.5-Air-NVFP4 Compatibility

Status: parked after live CSVQL behavior failures. The endpoint can serve the model, OpenGate can talk to it, and a trivial tool probe can produce a structured call, but the model did not build a usable CSVQL application through the live Codex harness.

## Serving Facts

Final checked configuration:

- Model repo as served locally: `Firworks/GLM-4.5-Air-nvfp4`.
- Served model name: `GLM-4.5-Air-NVFP4`.
- Serving stack: `vllm/vllm-openai:nightly-aarch64` on an aarch64/GX10 host.
- Final context setting: `--max-model-len 65536`.
- Earlier probe: `--max-model-len 131072`.
- Tool parser: `--tool-call-parser glm47`.
- Reasoning parser: `--reasoning-parser glm47`.
- OpenGate mode for live runs: `repair`, `full` context policy, `workspace-write`.

Sanitized serving command:

```bash
docker run --rm --gpus all \
  -p 8000:8000 \
  -v <hf-cache>:/root/.cache/huggingface \
  vllm/vllm-openai:nightly-aarch64 \
  --model Firworks/GLM-4.5-Air-nvfp4 \
  --served-model-name GLM-4.5-Air-NVFP4 \
  --max-model-len 65536 \
  --enable-auto-tool-choice \
  --tool-call-parser glm47 \
  --reasoning-parser glm47
```

Endpoint checks:

- `GET /v1/models` reported `id = GLM-4.5-Air-NVFP4`, `root = Firworks/GLM-4.5-Air-nvfp4`, and `max_model_len = 65536` after the restart.
- A trivial tool-call probe returned a structured `tool_calls` item for `ping`.
- Very small content probes can be misleading because the model may spend the output cap on reasoning and stop before visible content.

## CSVQL Live Runs

The CSVQL benchmark is `fixtures/codex_live/csvql_only.json`. It asks Codex to build a zero-dependency Python SQL engine over CSV files, including package files, CLI entry points, README, pytest coverage, and manual query checks.

| Run | Window | Output Cap | Exchanges | Upstream Errors | Commands | Files Landed | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `20260702-180525-glm45airnv_csvql-repair` | 131072 | 32768 default | 16 | 0 | 15 | 6 | Failed. Ended on `max_output_tokens`; wrote partial engine/parser files but no working CLI or tests. |
| `20260702-200142-glm45airnv_csvql_64k-repair` | 65536 | 32768 default | 7 | 1 | 6 | 1 | Failed. Upstream 400 because prompt tokens plus the default output reservation exceeded the 64k window. |
| `20260702-200615-glm45airnv_csvql_64k_cap16k-repair` | 65536 | 16384 | 24 | 0 | 23 | 3 | Failed. No context 400, but the final response narrated XML-ish `write_file` calls as assistant text and did not create the app. |

The capped 64k run is the cleanest measurement of model behavior because it removed the context-budget error. It still produced only:

- `csvql/customers.csv`
- `csvql/orders.csv`
- `csvql/csvql/__init__.py` as an empty package marker

It did not produce an engine, parser, CLI, README, or tests. Independent CLI checks failed with `No module named csvql.__main__` and a missing `run_csvql.py`.

## Comparison Notes

| Model / Run | Exchanges | Commands | Files | Outcome Shape |
| --- | ---: | ---: | ---: | --- |
| `Qwen3.5-122B-A10B-NVFP4` CSVQL | 4 | 2 | 2 | Authored a large `engine.py`, then stopped on a 64k context 400; demo queries were still wrong. |
| `GLM-4.5-Air-NVFP4` CSVQL 131k | 16 | 15 | 6 | More files than the capped 64k run, but partial package only and no runnable CLI. |
| `GLM-4.5-Air-NVFP4` CSVQL 64k cap16k | 24 | 23 | 3 | Avoided upstream 400, but mostly produced prose and fake XML-ish file writes. |
| `Qwen3.6-27B-NVFP4` CSVQL | 44 | 57 | 12 | Much more complete workspace, still correctness-failed. |
| `Qwen3.6-35B-A3B-FP8 r5` CSVQL | 95 | 113 | 14 | Most complete CSVQL attempt so far, still correctness-failed. |

Interpretation:

- The 64k retry needed a measurement knob, not a model-specific repair. The live harness now exposes `-UpstreamMaxOutputTokens` so the requested output reserve can be recorded explicitly in the manifest.
- Capping output tokens fixed the context arithmetic failure but did not improve the model enough to build CSVQL.
- The capped run returned zero invalid tool calls after OpenGate normalization. The remaining failure is model agent behavior: fake tool syntax in prose, missing artifacts, and no independently runnable program.
- This is not a new OpenGate repair target. It is benchmark evidence for the current model capability boundary.

## Reproduction

Pure 64k run that exposes the context-budget failure:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 `
  -Port 8766 `
  -Suite fixtures\codex_live\csvql_only.json `
  -CodexCwd C:\tmp\glm45airnv-csvql-64k `
  -Label glm45airnv_csvql_64k `
  -Model GLM-4.5-Air-NVFP4 `
  -UpstreamBaseUrl http://<gx10-host>:8000/v1 `
  -Mode repair `
  -ContextPolicy full `
  -Sandbox workspace-write `
  -FailOnPromptSandboxMismatch `
  -UpstreamTimeoutSeconds 9000 `
  -CaseTimeoutSeconds 9000 `
  -ModelContextWindow 65536
```

Capped 64k run that isolates behavior:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 `
  -Port 8767 `
  -Suite fixtures\codex_live\csvql_only.json `
  -CodexCwd C:\tmp\glm45airnv-csvql-64k-cap16k `
  -Label glm45airnv_csvql_64k_cap16k `
  -Model GLM-4.5-Air-NVFP4 `
  -UpstreamBaseUrl http://<gx10-host>:8000/v1 `
  -Mode repair `
  -ContextPolicy full `
  -Sandbox workspace-write `
  -FailOnPromptSandboxMismatch `
  -UpstreamTimeoutSeconds 9000 `
  -CaseTimeoutSeconds 9000 `
  -ModelContextWindow 65536 `
  -UpstreamMaxOutputTokens 16384
```
