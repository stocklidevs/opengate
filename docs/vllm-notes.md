# vLLM Notes

Checked against `http://127.0.0.1:8001`:

- Qwen3-Coder-Next on 2026-05-09.
- GLM-4.7-Flash on 2026-05-10.

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

## Reproducible GLM Setup

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

Open Gate also adapts Codex's multi-turn Responses input for vLLM. A first user-only turn can be accepted natively, but later Codex turns may include assistant history, `function_call`, and `function_call_output` items. vLLM can reject those with a 400 validation error. Open Gate's default `--upstream-input-mode auto` detects that shape and sends vLLM a flattened transcript while preserving the normal Responses API contract for Codex.

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
