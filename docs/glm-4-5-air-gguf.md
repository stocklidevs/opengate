# GLM-4.5-Air GGUF Compatibility

Status: failed CSVQL through OpenGate/Codex after a feasible llama.cpp GGUF deployment. The server path works; the benchmark failure is model behavior and transcript/tool drift, not a GPU load failure.

## Serving Facts

Checked on 2026-07-05 with the GX10 host.

- Model repo: `unsloth/GLM-4.5-Air-GGUF`.
- Quantization tested: `UD-Q4_K_XL`.
- Served model name: `GLM-4.5-Air-UD-Q4_K_XL`.
- Serving stack: llama.cpp `llama-server`.
- Context: `65536`.
- KV cache: `q8_0` for K and V.
- Template: Jinja enabled.
- Reasoning: `auto`.

Sanitized serving command:

```bash
llama-server \
  -hf unsloth/GLM-4.5-Air-GGUF:UD-Q4_K_XL \
  --host 0.0.0.0 \
  --port 8003 \
  --alias GLM-4.5-Air-UD-Q4_K_XL \
  --ctx-size 65536 \
  --n-gpu-layers all \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --jinja \
  --reasoning auto \
  --no-webui
```

Load facts from llama.cpp:

- GGUF file type: `Q4_K - Medium`.
- File size: `63.06 GiB`.
- Model type: `106B.A12B`.
- Parameters: `110.47 B`.
- Train context: `131072`.
- Runtime context: `65536`.
- Layers offloaded: `48/48`.
- CUDA model buffer: about `62209 MiB`.
- 64k q8_0 KV cache: about `6256 MiB`.
- `/v1/models` reported model blob size `67711712256`.

Q8_0 was not loaded in this pass. The Q8_0 listing is about 117 GB before KV cache, so it remains a separate memory-risk deployment cell rather than a completed behavior test.

## CSVQL Runs

The benchmark suite was `fixtures/codex_live/csvql_only.json`. Both runs used OpenGate `0.7.4`, repair mode, `workspace-write`, 64k model context, `-UpstreamMaxOutputTokens 16384`, and `-DisableWriteFileTool`.

| Run | Input Mode | Context | Duration | Exchanges | Upstream Errors | Commands | Files | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `20260705-172631-glm45air_udq4xl_64k_ogcodex_csvql_flatten_no_writefile-repair` | forced flatten | 65536 | 518.578 s | 12 | 1 | 9 | 2 | failed |
| `20260705-173954-glm45air_udq4xl_64k_ogcodex_csvql_auto_no_writefile_r2-repair` | auto/native | 65536 | 1313.724 s | 8 | 0 | 5 | 0 | failed |

### Forced Flatten

Run folder:

```text
runs\codex-live\20260705-172631-glm45air_udq4xl_64k_ogcodex_csvql_flatten_no_writefile-repair
```

This run created only:

- `csvql/csvql/__init__.py`
- `csvql/csvql/engine.py`

The files were corrupt or incomplete. Independent verification failed:

```text
python -B -m compileall -q csvql run_csvql.py
```

Result:

- `csvql/__init__.py` had invalid bytes.
- `csvql/engine.py` had invalid Python syntax, including backtick-quoted names such as ``count``.
- `run_csvql.py` was missing.

The final assistant-visible error was an upstream llama.cpp 500:

```text
Failed to parse input at pos 294: <tool_call>
                    request_plugin_install
...
```

Interpretation: forced flattening made GLM's earlier plugin-install tool call reappear as raw transcript text. llama.cpp then tried to parse that raw `<tool_call>` block on a later turn. The run also showed model-level fragility before the 500: brittle PowerShell file writes, malformed quote handling, and a partial engine.

### Auto/Native Retry

Run folder:

```text
runs\codex-live\20260705-173954-glm45air_udq4xl_64k_ogcodex_csvql_auto_no_writefile_r2-repair
```

This run avoided the upstream 500. OpenGate's capability probe reported native Responses and native tool-history support, and the run completed with:

- `upstream_errors = 0`
- `returned_text_leaks = 0`
- `returned_invalid_tool_calls = 0`
- `returned_command_quality_issues = 0`
- `returned_clean_capture_rate = 1.0`

It still failed the task. GLM produced no CSVQL artifacts and spent the long final response searching for `writing-plans` skill files under `C:/Users/pstoc/.codex/skills/.system`. The final message was about 56 KB of repeated directory-search command transcripts.

Independent verification failed at the existence gate:

```text
python -B -m compileall -q csvql run_csvql.py
Can't list 'csvql'
Can't list 'run_csvql.py'
```

## Interpretation

The GGUF deployment itself was healthy. The useful contrast is:

- Forced flatten: some artifact attempts, but corrupt files and a later raw-tool-call parser 500.
- Auto/native: no protocol error, clean returned channel, but complete task drift and no artifacts.

This keeps GLM-4.5-Air GGUF in the behavior-failed bucket for CSVQL through OG/Codex. It is not a new OpenGate repair target unless a future capture shows a generic transport, parser, or command-quality rule that would help other models too.
