# vLLM Notes

Checked against local OpenAI-compatible serving endpoints, mostly vLLM at `http://127.0.0.1:8001`:

- Qwen3-Coder-Next on 2026-05-09.
- GLM-4.7-Flash on 2026-05-10.
- Qwen3.6-27B basic smoke checked on 2026-05-11 UTC, 2026-05-10 America/New_York.
- GLM-4.5-Air-NVFP4 live CSVQL checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- Kimi-Linear-48B-A3B-NVFP4 live CSVQL checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- MiniMax-M3-MXFP8 deployment checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- Devstral-Small-2507 live CSVQL checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- Qwen3.6-27B Q8_0 GGUF through llama.cpp and Qwen Code CSVQL checked on 2026-07-05.

## Live Server

`GET /v1/models` reported:

- `id`: `Qwen3-Coder-Next`
- `root`: `cyankiwi/Qwen3-Coder-Next-AWQ-4bit`
- `max_model_len`: `32768`

## Reproducible Qwen Setup

The local Qwen3-Coder-Next server used for these Open Gate notes was started with vLLM:

```bash
python3 -m venv ~/qwen3next-venv
source ~/qwen3next-venv/bin/activate

pip install -U "vllm>=0.15.0"

vllm serve "cyankiwi/Qwen3-Coder-Next-AWQ-4bit" \
  --host 0.0.0.0 \
  --port 8001 \
  --served-model-name "Qwen3-Coder-Next" \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --performance-mode interactivity
```

OpenGate `0.6.7+` can use that endpoint directly. Set `model = "auto"` in `opengate.toml`; on startup OpenGate detects the served model and rewrites Codex's forwarded `model` field so a stale Codex profile does not cause vLLM "model does not exist" errors.

This exposes an OpenAI-compatible endpoint at:

```text
http://<host>:8001/v1
```

For the local GX10 setup used here, Codex/Open Gate pointed at:

```text
http://127.0.0.1:8001/v1
```

The important tool-related flags are `--enable-auto-tool-choice` and `--tool-call-parser qwen3_coder`. Open Gate still sits in front of the server because even with vLLM tool parsing enabled, the model can emit tool arguments that are syntactically structured but rejected by Codex policy, such as nested PowerShell.

## Reproducible Qwen3.6-27B Setup

The next Qwen target is `Qwen/Qwen3.6-27B`, served under the model name `Qwen3.6-27B`:

```bash
source ~/qwen3next-venv/bin/activate

vllm serve "Qwen/Qwen3.6-27B" \
  --host 0.0.0.0 \
  --port 8001 \
  --served-model-name "Qwen3.6-27B" \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85 \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
```

OpenGate should keep using `model = "auto"` in `opengate.toml` for this target. On startup, `GET /v1/models` should report `Qwen3.6-27B`, and OpenGate should rewrite Codex's requested model to that active upstream model. This keeps the Codex profile stable while the served vLLM model changes.

The first endpoint check reported `root = Qwen/Qwen3.6-27B` and `max_model_len = 65536`. Direct `codex_shell_smoke` passed `9/9`, but direct `qwen_serious_tool_stress` returned `HTTP 400: Unexpected message role` for all 20 cases because that suite uses a Codex-like `developer` message. OpenGate `0.6.9` handles this as a protocol-adaptation problem: startup probes detect unsupported roles, `--upstream-input-mode auto` can flatten unsupported role shapes independently from spoon compression, and native role/history validation errors are retried once with flattened input. Prepared validation steps and result placeholders are in `docs\qwen3-6-27b.md`.

## Reproducible Qwen3.6-27B Q8_0 llama.cpp Setup

The CSVQL pass on 2026-07-05 used a different serving stack from the vLLM setup above: ggml-org's Q8_0 GGUF through llama.cpp, driven by Qwen Code CLI `0.19.5`.

```bash
/home/altsens/llama.cpp/build/bin/llama-server \
  -m /home/altsens/models/ggml-org/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q8_0.gguf \
  --host 0.0.0.0 \
  --port 8002 \
  --alias Qwen3.6-27B-Q8_0 \
  -c 262144 \
  -ngl all \
  -fa on \
  --fit off \
  --reasoning auto \
  --reasoning-format deepseek \
  --jinja \
  --no-webui
```

Observed serving facts:

- GGUF file: `Qwen3.6-27B-Q8_0.gguf`
- Quantization: Q8_0
- File size: about 28.6 GB
- Context: `n_ctx = 262144`
- Layers: all 65 layers on GPU
- Endpoint: `http://<gx10-host>:8002/v1`
- Served model alias: `Qwen3.6-27B-Q8_0`

Qwen Code workspace settings used:

```json
{
  "modelProviders": {
    "openai": {
      "protocol": "openai",
      "models": [
        {
          "id": "Qwen3.6-27B-Q8_0",
          "baseUrl": "http://<gx10-host>:8002/v1",
          "generationConfig": {
            "timeout": 1800000,
            "maxRetries": 0,
            "contextWindowSize": 262144,
            "samplingParams": {
              "temperature": 0.2,
              "max_tokens": 8192
            }
          }
        }
      ]
    }
  }
}
```

Run Qwen Code from an isolated workspace with the exact CSVQL prompt piped through stdin:

```powershell
$Prompt = (Get-Content -LiteralPath fixtures\codex_live\csvql_only.json -Raw | ConvertFrom-Json).cases[0].prompt
$Prompt | qwen `
  --auth-type openai `
  --model Qwen3.6-27B-Q8_0 `
  --openai-base-url http://<gx10-host>:8002/v1 `
  --openai-api-key sk-local-qwen-q8 `
  --approval-mode yolo `
  --max-wall-time 8h `
  --max-session-turns 300 `
  --openai-logging `
  --chat-recording true `
  --input-format text `
  --prompt ""
```

Use a long wall-clock guard from the start. The recorded run first used `120m`, hit that guard while still making progress, then completed only after resuming the same Qwen Code chat with an `8h` guard.

## Reproducible GLM-4.5-Air-NVFP4 Setup

The GLM-4.5-Air-NVFP4 CSVQL probe was served on the GX10 with Docker:

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

Earlier in the same experiment the server was also run with `--max-model-len 131072`. The final 64k retry confirmed `/v1/models` returned:

- `id`: `GLM-4.5-Air-NVFP4`
- `root`: `Firworks/GLM-4.5-Air-nvfp4`
- `max_model_len`: `65536`

A trivial tool probe produced a structured tool call, so the endpoint/parser path was viable. The live CSVQL benchmark still failed because the model did not complete the app. The uncapped 64k run also exposed a context-budget issue: Codex requested 32768 output tokens while the prompt already occupied 32769 tokens. Use `-UpstreamMaxOutputTokens` in `scripts\run_codex_live_benchmark.ps1` when measuring smaller context windows so the output reserve is explicit in the manifest.

See `docs\glm-4-5-air-nvfp4.md` for the CSVQL run matrix and interpretation.

## Reproducible Kimi-Linear-48B-A3B-NVFP4 Setup

The Kimi Linear CSVQL probe used the NVFP4 quantization `Firworks/Kimi-Linear-48B-A3B-Instruct-nvfp4` on the GX10:

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

The cached remote tokenizer initially failed to import `bytes_to_unicode` from `transformers.models.gpt2.tokenization_gpt2`; the live server was booted after patching that cached `tokenization_kimi.py` with a local fallback implementation. After load, `/v1/models` returned:

- `id`: `Kimi-Linear-48B-A3B-NVFP4`
- `root`: `Firworks/Kimi-Linear-48B-A3B-Instruct-nvfp4`
- `max_model_len`: `65536`

Plain `/v1/responses` generation worked for a trivial sanity prompt. Tool use did not: a minimal Responses request with one `ping` tool produced explanatory text instead of a structured function call, and the live CSVQL runs made zero Codex tool calls. OpenGate includes a narrow parser for Kimi reserved-token tool-call text observed during probing, but this vLLM/Kimi serving path should be treated as parked until auto tool calling is fixed upstream or served through a working parser/template pair.

## MiniMax-M3-MXFP8 Deployment Attempt

MiniMax-M3-MXFP8 was attempted on the GX10 with the public MXFP8 checkpoint:

```bash
docker run -d --name minimax_m3_mxfp8 --gpus all --ipc=host \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:nightly-aarch64 \
  MiniMaxAI/MiniMax-M3-MXFP8 \
  --served-model-name MiniMax-M3-MXFP8 \
  --trust-remote-code \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85 \
  --host 0.0.0.0 \
  --port 8000
```

vLLM recognized `MiniMaxM3SparseForConditionalGeneration`, `quantization=mxfp8`, and the MiniMax sparse-attention path, but failed during model construction:

```text
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 4.50 GiB.
GPU 0 has a total capacity of 119.61 GiB of which 2.79 GiB is free.
Including non-PyTorch memory, this process has 112.40 GiB memory in use.
```

A retry with `--cpu-offload-gb 8 --kv-cache-dtype fp8 --enforce-eager` was accepted and selected `UVAOffloader`, but saturated the 119 GiB host memory before the server exposed `/v1/models`. No direct probe or CSVQL run was possible. See `docs\minimax-m3-mxfp8.md`.

## Reproducible Devstral-Small-2507 Setup

Devstral-Small-2507 was served on the GX10 with the Mistral vLLM path:

```bash
docker run -d --name devstral_small_2507 --gpus all --ipc=host \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:nightly-aarch64 \
  mistralai/Devstral-Small-2507 \
  --served-model-name Devstral-Small-2507 \
  --tokenizer-mode mistral \
  --config-format mistral \
  --load-format mistral \
  --tool-call-parser mistral \
  --enable-auto-tool-choice \
  --max-model-len 65536 \
  --max-num-seqs 1 \
  --gpu-memory-utilization 0.85 \
  --host 0.0.0.0 \
  --port 8000
```

After load, `/v1/models` returned:

- `id`: `Devstral-Small-2507`
- `root`: `mistralai/Devstral-Small-2507`
- `max_model_len`: `65536`

The endpoint passed plain `/v1/responses` sanity generation. Minimal tool probes showed that vLLM rejected function tools without `strict: false`; with `strict: false`, named/forced tool calls worked, while auto tool choice on a trivial probe returned JSON-like assistant text instead of a structured call.

OpenGate now normalizes upstream tool schemas for this class of server by filtering unsupported hosted/namespace tools, wrapping hosted `web_search` as a function-shaped tool, and adding `strict: false` to function tools before forwarding to vLLM. This fixed the initial 400 in the live CSVQL run, but the best `-WriteFileTool` attempt still produced a syntactically broken partial app with no CLI or tests. See `docs\devstral-small-2507.md`.

## Reproducible GLM-4.7-Flash Setup

The first GLM-4.7-Flash baseline used the same virtual environment and served:

```bash
source ~/qwen3next-venv/bin/activate
export VLLM_ATTENTION_BACKEND=FLASH_ATTN

vllm serve "zai-org/GLM-4.7-Flash" \
  --host 0.0.0.0 \
  --port 8001 \
  --served-model-name "GLM-4.7-Flash" \
  --max-model-len 131072 \
  --gpu-memory-utilization 0.85 \
  --enable-auto-tool-choice \
  --tool-call-parser glm47 \
  --reasoning-parser glm45
```

`GET /v1/models` reported:

- `id`: `GLM-4.7-Flash`
- `root`: `zai-org/GLM-4.7-Flash`
- `max_model_len`: `131072`

The first direct benchmark showed that vLLM returned HTTP 200 responses, but GLM often emitted tool calls as assistant text such as `<tool_call>...` rather than structured Responses `function_call` items. Open Gate `0.6.0` repairs that dialect transparently by parsing GLM `<arg_key>/<arg_value>` blocks, promoting recoverable calls, and scrubbing raw syntax from assistant and reasoning text. See `docs\benchmark-notes.md` for the measured baseline and repaired results.

Open Gate also adapts Codex's multi-turn Responses input for vLLM. A first user-only turn can be accepted natively, but later Codex turns may include assistant history, `developer` instructions, `function_call`, and `function_call_output` items. vLLM can reject those with a 400 validation error. Open Gate's default `--upstream-input-mode auto` detects or probes those shapes and sends vLLM a flattened transcript while preserving the normal Responses API contract for Codex.

Codex sends streamed `/v1/responses` requests, but Open Gate intentionally asks vLLM for `stream: false` so it can inspect and repair the full model response before Codex sees it. Long Qwen/GLM generations can otherwise leave Codex staring at a silent socket until Codex retries the turn. Open Gate now sends real Responses `response.in_progress` heartbeat events every `--stream-heartbeat-seconds` while waiting, then replays the normalized response as standard Responses SSE events.

The request-size probe used `POST /tokenize` to avoid generation. The server accepted JSON request bodies of approximately:

- 4 KB
- 8 KB
- 16 KB
- 64 KB
- 262 KB

So this server does not appear to have a 4 KB JSON request-body limit.

## Relevant vLLM Flags

Current vLLM docs list `--h11-max-incomplete-event-size` as the HTTP parser limit for incomplete HTTP events, including headers or body. The documented default is `4194304` bytes, or 4 MB.

If Codex/Open Gate eventually sends very large tool schemas or prompts that exceed the default, increase that HTTP parser limit explicitly:

```powershell
vllm serve ... --h11-max-incomplete-event-size 33554432
```

That is separate from context length. Context length is controlled by model/config options such as `--max-model-len`; raising `--max-model-len` does not necessarily raise the HTTP request-body parser limit.

For auto tool calling, vLLM needs auto tool choice plus a parser appropriate for the model. This Qwen3-Coder-Next setup used:

```bash
vllm serve ... --enable-auto-tool-choice --tool-call-parser qwen3_coder
```

The docs also distinguish `tool_choice="auto"` from `tool_choice="required"` or named function calls. In `auto`, vLLM parses model text; in `required` or named function mode, vLLM can use structured outputs for schema-shaped arguments. Codex normally sends `tool_choice: "auto"`, so parser robustness remains important.
