# Qwen3-Coder-Next Compatibility

This note records the first known-good Open Gate setup for Qwen3-Coder-Next through Codex.

## Status

- Model: `Qwen3-Coder-Next`
- Server: vLLM at `http://127.0.0.1:8001/v1`
- Open Gate: `0.5.0`
- Mode: `repair`
- Upstream input mode: `auto`
- Context policy: `spoon` for long interactive runs; `full` for apples-to-apples legacy baselines.
- Validation date: `2026-05-10` UTC, `2026-05-09` America/New_York

## Required Setup

The vLLM server was started with:

```bash
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

Open Gate should sit between Codex and vLLM:

```powershell
python -m open_gate `
  --host 127.0.0.1 `
  --port 8765 `
  --model Qwen3-Coder-Next `
  --upstream http://127.0.0.1:8001/v1 `
  --normalization-mode repair `
  --upstream-input-mode auto `
  --context-policy spoon `
  --context-max-chars 60000 `
  --context-recent-items 10 `
  --stream-heartbeat-seconds 5
```

Codex should point at Open Gate with `wire_api = "responses"` and model `Qwen3-Coder-Next`.

## Known-Good Smoke

Run folder:

```text
runs\qwen-known-good\20260509-203637-qwen-known-good-fast-0.3.0
```

Prompt:

```text
Use shell to count the entries in the current directory, then answer with exactly one sentence containing the count.
```

Result summary:

| Metric | Value |
| --- | ---: |
| Codex exit code | 0 |
| Codex turns completed | 1/1 |
| Proxy exchanges | 2 |
| Upstream errors | 0 |
| Flattened upstream requests | 1 |
| Stream heartbeats | 44 |
| Max proxy duration | 5.481s |
| Structured argument repairs | 1 |
| Returned command-quality issues | 0 |
| Returned invalid tool calls | 0 |
| Returned clean capture rate | 100% |

Final assistant message:

```text
The current directory contains 0 entries.
```

This proves the current stack can complete a full Codex loop: model call, tool call, shell execution, tool output, second model call, and final assistant answer.

## Stress Observation

A larger HTML-generation smoke was also attempted in:

```text
runs\qwen-known-good\20260509-202007-qwen-known-good-0.3.0
```

That run exceeded the local 15-minute harness timeout, so it is not a pass. It did confirm that the Open Gate `0.3.0` heartbeat path stayed active during long upstream waits:

| Metric | Value |
| --- | ---: |
| Proxy exchanges | 12 |
| Stream heartbeats | 841 |
| Max proxy duration | 120.109s |
| Flattened upstream requests | 7 |

Use smaller deterministic prompts for pass/fail compatibility checks. Use large-generation prompts only as stress tests.

## Qwen Code CSVQL Probe

On 2026-07-03, the same `fixtures\codex_live\csvql_only.json` CSVQL prompt was run through Qwen Code CLI `0.19.5` instead of the OpenGate live Codex runner. The shareable challenge prompt and verifier are in `docs\csvql-local-agent-challenge.md`. Qwen Code was installed locally and configured to use the GX10 vLLM endpoint as an OpenAI-compatible provider:

```text
model = Qwen3-Coder-Next
baseUrl = http://<gx10-host>:8000/v1
```

The first pass used the original 32k serving window. It wrote a single large `csvql.py`, then Qwen Code could not continue:

```text
runs\qwen-code-live\20260703-082748-qwen3_coder_next_qwencode_csvql
```

Failure shape:

- Duration: `288.224 s`
- Exit code: `0`, but final result was an API error from Qwen Code's context manager
- Files: `1`
- Error: `COMPRESSION_FAILED_INFLATED_TOKEN_COUNT`
- Estimated prompt tokens after the big file write: `23638`
- Qwen Code safe hard limit for that run: about `20203`

This was a harness budget failure, not a model-config limit. The local model config reports `max_position_embeddings = 262144`, and vLLM served cleanly at `--max-model-len 131072` with `/v1/models` reporting `max_model_len = 131072`. Qwen Code's `contextWindowSize` was then updated to `131072`.

The 128k retry:

```text
runs\qwen-code-live\20260703-084553-qwen3_coder_next_qwencode_csvql_128k_r2
```

Summary:

| Metric | Value |
| --- | ---: |
| Context window | 131072 |
| Duration | 2011.884 s |
| Exit code | -1, stopped after benchmark drift |
| Files landed | 7 |
| Compression errors | 0 |

The 128k run continued past the large file write and actively used tools, including file writes, reads, edits, and shell commands. It still failed the benchmark. The workspace contained `csvql.py`, `README.md`, `TESTS.md`, `EXAMPLES.md`, `sample_data/employees.csv`, `sample_data/products.csv`, and bytecode. It missed the required `customers.csv`, `orders.csv`, `run_csvql.py`, `csvql/__init__.py`, `csvql/__main__.py`, and `tests/` suite.

Independent verification:

- `csvql.py` syntax parsed successfully.
- `python -m csvql --query "SELECT name, city FROM customers WHERE city = 'NYC'" --table customers=customers.csv --table orders=orders.csv` failed because the generated CLI treated `--query` as a CSV path.
- `python run_csvql.py ...` failed because `run_csvql.py` did not exist.
- pytest was not run because no `tests/` directory existed.

Interpretation: Qwen Code at 128k removed the immediate context compression blocker, but the run drifted into a different single-file demo and then self-debugged that demo instead of returning to the requested CSVQL app contract. This does not change Qwen3-Coder-Next's earlier known-good OpenGate smoke/software-build evidence; it records that the harder CSVQL case remains unpassed even through Qwen's own harness.

## Notes

- `--upstream-input-mode auto` is required for later Codex turns because vLLM may reject native assistant history, `function_call`, and `function_call_output` input items.
- `--context-policy spoon` is recommended for large interactive work. It prevents runaway flattened histories by summarizing older Codex state and preserving compact constraints from failed tool attempts.
- `repair` mode is the recommended user-facing mode. In the known-good smoke, Qwen produced a shell command shape that Open Gate repaired before Codex saw it.
- A later live test with web/screenshot tooling showed a different failure mode: Qwen produced valid structured tool calls that were operationally bad, including `view_image` on a directory, Windows PowerShell `&&`, malformed here-strings, brittle `python -c` async code, and `uv run playwright` before Playwright was installed. Open Gate `0.4.0` records these as command-quality issues; Open Gate `0.5.0` can also feed the constraints back through `--context-policy spoon`.
- Plugin and skill sync warnings from Codex are not Open Gate failures. They can appear when Codex tries to reach external OpenAI/GitHub plugin endpoints.
- If Open Gate captures upstream status `599` with a socket permission error, rerun the smoke with local-network access to the vLLM host.
