# Kimi-Linear-48B-A3B-NVFP4 Notes

Date checked: 2026-07-03 UTC, 2026-07-02 America/New_York.

## Serving

Model:

- `Firworks/Kimi-Linear-48B-A3B-Instruct-nvfp4`
- Served as `Kimi-Linear-48B-A3B-NVFP4`
- Base model: `moonshotai/Kimi-Linear-48B-A3B-Instruct`
- Quantization: NVFP4

GX10 Docker command:

```bash
docker run -d --name kimi_linear_nvfp4 --gpus all --ipc=host \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:nightly-aarch64 \
  Firworks/Kimi-Linear-48B-A3B-Instruct-nvfp4 \
  --served-model-name Kimi-Linear-48B-A3B-NVFP4 \
  --max-model-len 65536 \
  --trust-remote-code \
  --gpu-memory-utilization 0.85 \
  --enable-auto-tool-choice \
  --tool-call-parser kimi_k2
```

The first boot failed because cached `tokenization_kimi.py` imported `bytes_to_unicode` from `transformers.models.gpt2.tokenization_gpt2`, where it was not available in the vLLM image. The run used a local cached-tokenizer patch that adds a fallback `bytes_to_unicode()` implementation.

`GET /v1/models` after boot:

```json
{
  "id": "Kimi-Linear-48B-A3B-NVFP4",
  "root": "Firworks/Kimi-Linear-48B-A3B-Instruct-nvfp4",
  "max_model_len": 65536
}
```

## Direct Probes

Plain Responses generation worked:

```text
input: Reply with exactly: CSVQL sanity OK
output: CSVQL sanity OK
```

Minimal tool probes did not produce executable calls in this serving configuration:

- `/v1/responses` with one `ping` tool returned assistant text explaining a JSON-looking call instead of a `function_call`.
- `/v1/chat/completions` with one `ping` tool also returned explanatory text instead of a structured `tool_call`.

An earlier probe showed Kimi-family reserved-token tool syntax of this shape:

```text
<|reserved_token_163595|><|reserved_token_163597|>functions.ping:0<|reserved_token_163598|>{"x": "ok"}<|reserved_token_163599|><|reserved_token_163596|>
```

OpenGate now parses that generic reserved-token shape if it appears in assistant text, but the live CSVQL runs below emitted no parseable Kimi tool calls.

## Live CSVQL Runs

Suite: `fixtures\codex_live\csvql_only.json`

Command shape:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 `
  -Suite fixtures\codex_live\csvql_only.json `
  -Model Kimi-Linear-48B-A3B-NVFP4 `
  -UpstreamBaseUrl http://<gx10-host>:8000/v1 `
  -Mode repair `
  -Sandbox workspace-write `
  -FailOnPromptSandboxMismatch `
  -ModelContextWindow 65536 `
  -UpstreamMaxOutputTokens 16384
```

Results:

| Run | Context | Exchanges | Commands | Files | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `20260702-212631-kimi_linear_nvfp4_csvql_64k-repair` | `full`, native Responses | 1 | 0 | 0 | Off-task email-analytics answer |
| `20260702-212847-kimi_linear_nvfp4_csvql_64k_spoon-repair` | `spoon`, flattened transcript | 1 | 0 | 0 | Off-task puzzle/fish answer |

Both runs completed from Codex's perspective, but neither entered the tool loop. The target workspaces remained empty. OpenGate reported zero returned leaks, invalid tool calls, and command-quality issues because there were no tool-call candidates to repair.

## Decision

Kimi-Linear-48B-A3B-NVFP4 is parked for OpenGate CSVQL on this vLLM stack. The failure is not a partial CSVQL implementation. It is a tool-interface and prompt-grounding failure: Kimi did not emit executable tool calls for Codex, and no requested files were created.

The only accepted OpenGate change from this pass is the model-agnostic Kimi reserved-token parser. Do not add task-progress steering or behavior-specific repairs for this result.
