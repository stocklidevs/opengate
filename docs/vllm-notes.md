# vLLM Notes

Checked on 2026-05-09 against `http://127.0.0.1:8001`.

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

This exposes an OpenAI-compatible endpoint at:

```text
http://<host>:8001/v1
```

For the local GX10 setup used here, Codex/Open Gate pointed at:

```text
http://127.0.0.1:8001/v1
```

The important tool-related flags are `--enable-auto-tool-choice` and `--tool-call-parser qwen3_coder`. Open Gate still sits in front of the server because even with vLLM tool parsing enabled, the model can emit tool arguments that are syntactically structured but rejected by Codex policy, such as nested PowerShell.

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
