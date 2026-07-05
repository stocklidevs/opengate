# Qwen3-Coder-30B-A3B-Instruct GGUF Compatibility

Status: failed CSVQL through OpenGate/Codex at 128k context. The llama.cpp server path is healthy, but the model fabricated a completed implementation transcript instead of creating artifacts.

## Serving Facts

Checked on 2026-07-05 with the GX10 host.

- Model repo: `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF`.
- Quantization tested: `Q8_0`.
- Served model name: `Qwen3-Coder-30B-A3B-Instruct-Q8_0`.
- Serving stack: llama.cpp `llama-server`.
- Context: `131072`.
- KV cache: `q8_0` for K and V.
- Template: Jinja enabled.
- Reasoning: off.

Sanitized serving command:

```bash
llama-server \
  -hf unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q8_0 \
  --host 0.0.0.0 \
  --port 8004 \
  --alias Qwen3-Coder-30B-A3B-Instruct-Q8_0 \
  --ctx-size 131072 \
  --n-gpu-layers all \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --jinja \
  --reasoning off \
  --no-webui
```

Load facts from llama.cpp:

- Architecture: `qwen3moe`.
- Model type: `30B.A3B`.
- Parameters: `30.53 B`.
- Train context: `262144`.
- Runtime context: `131072`.
- Layers offloaded: `49/49`.
- CUDA model buffer: about `30658 MiB`.
- 128k q8_0 KV cache: about `6528 MiB`.
- `/v1/models` reported model blob size `32477962240`.

## CSVQL Run

The benchmark suite was `fixtures/codex_live/csvql_only.json`. The run used OpenGate `0.7.4`, repair mode, forced flattened upstream input, full context, `workspace-write`, 128k model context, `-UpstreamMaxOutputTokens 16384`, and `-DisableWriteFileTool`.

Run folder:

```text
runs\codex-live\20260705-182317-qwen3coder30b_a3b_q8_0_128k_ogcodex_csvql_flatten_no_writefile-repair
```

Summary:

| Metric | Value |
| --- | ---: |
| Duration | `1170.566` seconds |
| Proxy exchanges | `7` |
| Upstream errors | `0` |
| Codex command executions | `5` |
| Max flattened chars | `136578` |
| Stream heartbeats | `561` |
| Returned invalid tool calls | `0` |
| Returned command-quality issues | `0` |
| Returned clean capture rate | `0.5714` |

The run ended with Codex reporting `turn.completed`, but the artifact was empty. The only workspace entries were directories:

- `csvql/`
- `csvql/csvql/`

Independent verification failed immediately:

```text
python -B -m compileall -q csvql run_csvql.py
Can't list 'run_csvql.py'
```

There was no `run_csvql.py`, no package implementation, no fixtures, no README, and no tests.

## Failure Shape

The model generated a long assistant text block that looked like a completed tool transcript. It included fake lines such as `assistant tool call shell ...`, pretend file-writing commands, pretend `python tests/...` executions, and pretend manual-query outputs. These were not real structured calls, so Codex did not execute them.

OpenGate saw multiple promotion candidates from the fake transcript but did not promote them because the response already contained a real structured call. That preserved tool-channel safety, but it also left the model's fabricated work as assistant text. The few real structured commands created directories and then attempted to run missing files.

The final assistant message claimed success and listed files that did not exist, including `csvql.py`, `run_csvql.py`, CSV fixtures, README, and tests.

## Interpretation

This is not a deployment failure. Qwen3-Coder-30B-A3B-Instruct Q8_0 runs comfortably at 128k on the GX10 through llama.cpp. It is also not a memory/context failure: the largest flattened request stayed inside the 128k window.

The failure is behavioral: the model produced a fake completion transcript and self-reported success without creating artifacts. This keeps the model in the failed bucket for OG/Codex CSVQL unless a future harness or prompt variant can prevent transcript-style fabrication.
