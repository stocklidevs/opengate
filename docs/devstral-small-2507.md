# Devstral-Small-2507 Notes

Date checked: 2026-07-03 UTC, 2026-07-02 America/New_York.

Status: parked after live CSVQL behavior and artifact failures. The endpoint serves the model at 64k, plain generation works, and named/forced tool calling works, but the live Codex CSVQL run did not produce a runnable application.

## Serving

Model:

- `mistralai/Devstral-Small-2507`
- Served as `Devstral-Small-2507`
- Serving stack: `vllm/vllm-openai:nightly-aarch64`
- Context setting: `--max-model-len 65536`
- Tool parser: `--tool-call-parser mistral`

GX10 Docker command:

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

`GET /v1/models` after boot:

```json
{
  "id": "Devstral-Small-2507",
  "root": "mistralai/Devstral-Small-2507",
  "max_model_len": 65536
}
```

Observed load facts:

- vLLM resolved `MistralForCausalLM`, BF16, `load_format=mistral`, and `tokenizer_mode=mistral`.
- Checkpoint size was about `43.91 GiB`.
- Model loading used about `43.94 GiB` and took about `1040 s`.
- KV cache memory was about `53.65 GiB`, with a reported cache capacity of `351,584 tokens`.
- After the host reboot, the container was again up on port `8000`; memory was about `108 GiB` used, `11 GiB` available, and swap was effectively unused.

## Direct Probes

Plain Responses generation worked:

```text
input: Reply with exactly: CSVQL sanity OK
output: CSVQL sanity OK
```

Tool probes exposed two important boundaries:

- vLLM rejected tool schemas without a boolean `strict` field.
- With `strict: false`, `tool_choice: auto` returned JSON-like assistant text instead of a structured call.
- With a named/forced `ping` tool, both Responses and Chat Completions returned a structured tool call.

This led to a model-agnostic OpenGate protocol fix: filter unsupported upstream tool shapes before forwarding to vLLM/Mistral, add `strict: false` to function tools when missing, wrap hosted `web_search` as a function-shaped tool, and remove unsupported hosted/namespace tools such as image generation, Gmail, Linear, security, and node namespaces.

## Live CSVQL Runs

Suite: `fixtures\codex_live\csvql_only.json`

Command shape:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_codex_live_benchmark.ps1 `
  -Suite fixtures\codex_live\csvql_only.json `
  -Model Devstral-Small-2507 `
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

Results:

| Run | Variant | Exchanges | Upstream Errors | Commands | Files | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `20260702-225235-devstral_small_2507_csvql_64k-repair` | before tool-schema filter | 1 | 1 | 0 | 0 | Failed immediately with vLLM schema validation on unsupported Codex tool shapes |
| `20260702-225804-devstral_small_2507_csvql_64k_r2-repair` | schema filter, shell only | 4 | 0 | 3 | 0 | Created directories, then stopped while preparing package files |
| `20260702-230200-devstral_small_2507_csvql_64k_writefile_r3-repair` | schema filter plus `-WriteFileTool` | 9 | 0 | 7 | 5 | Landed partial files, but no runnable app |

The `r3` write-file run is the most meaningful Devstral measurement. Summary metrics:

- `codex_command_executions`: `7`
- `stream_heartbeats`: `359`
- `promoted_tool_calls`: `3`
- `upstream_text_leaks`: `4`
- `returned_text_leaks`: `0`
- `upstream_invalid_tool_calls`: `4`
- `returned_invalid_tool_calls`: `2`
- `returned_clean_capture_rate`: `0.7778`
- Duration: about `784.858 s`

Workspace files from `r3`:

- `README.md`
- `customers.csv`
- `orders.csv`
- `csvql/__init__.py`
- `csvql/db.py`

Missing required artifacts:

- `run_csvql.py`
- `csvql/__main__.py`
- pytest suite
- manual query output

Independent verification failed:

```text
python -m py_compile csvql/db.py
SyntaxError: unmatched ')' at line 191: elif expr['op'] == '>/g'):

python -m csvql ...
No module named csvql.__main__; 'csvql' is a package and cannot be directly executed

python run_csvql.py ...
can't open file 'run_csvql.py': [Errno 2] No such file or directory
```

The final assistant message was: `Great! Now let's create the main entry point for the application in run_csvql.py:`. The run ended before that entry point was created.

## Decision

Devstral-Small-2507 is parked for OpenGate CSVQL on this stack. It is not deployment-blocked like MiniMax and not a zero-tool loop like Kimi. It can serve, answer, call forced tools, and write files through OpenGate. The failure is still decisive: the generated code is syntactically broken, the CLI entry points are missing, and the requested tests and manual checks never happened.

The accepted OpenGate changes from this pass are protocol/harness changes only: vLLM-safe upstream tool schema normalization and the optional live-harness `-WriteFileTool` path. Do not add task-progress steering or CSVQL-specific repairs for this result.
