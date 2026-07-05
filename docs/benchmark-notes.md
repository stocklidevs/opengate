# Benchmark Notes

Checked against direct vLLM and later local OpenAI-compatible serving endpoints:

- Qwen3-Coder-Next checked on 2026-05-09.
- GLM-4.7-Flash checked on 2026-05-10.
- Qwen3.6-27B basic smoke checked on 2026-05-11 UTC, 2026-05-10 America/New_York.
- DeepSeek-Coder-V2-Lite-Instruct checked on 2026-05-28.
- Gemma-4-E4B-IT checked on 2026-05-29.
- GLM-4.5-Air-NVFP4 live CSVQL checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- Kimi-Linear-48B-A3B-NVFP4 live CSVQL checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- MiniMax-M3-MXFP8 deployment checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- Devstral-Small-2507 live CSVQL checked on 2026-07-03 UTC, 2026-07-02 America/New_York.
- Qwen3-Coder-Next through Qwen Code CSVQL checked on 2026-07-03.
- Qwen3.6-27B Q8_0 GGUF through Qwen Code CSVQL checked on 2026-07-05.

## Suites

`fixtures/benchmarks/codex_shell_smoke.json`

- 3 simple Codex-like cases.
- Expected behavior: structured `shell` or `update_plan` calls.
- One run against direct Qwen/vLLM: 3/3 strict successes.
- Three runs against direct GLM-4.7-Flash/vLLM: 0/9 strict successes.
- Three runs against direct DeepSeek-Coder-V2-Lite-Instruct/vLLM: 0/9 strict successes.

`fixtures/benchmarks/codex_tool_leak_stress.json`

- 4 adversarial cases that bait XML, JSON, Pythonic, and `recipient_name` leakage.
- One run against direct Qwen/vLLM: 3/4 strict successes.
- No tool syntax leaked into text.
- One case embedded `recipient_name`/`functions.shell` strings inside the structured `update_plan` arguments, counted as `argument_leak`.
- Three runs against direct GLM-4.7-Flash/vLLM: 0/12 strict successes, with text leakage in 12/12 cases.
- Three runs against direct DeepSeek-Coder-V2-Lite-Instruct/vLLM: 0/12 strict successes, with text leakage in 6/12 cases.

## Current Interpretation

The current direct Qwen/vLLM setup is already doing well for basic Responses tool calls. The benchmark is still useful because:

- It creates a repeatable baseline before Open Gate changes anything.
- It separates text leakage from structured argument leakage.
- It gives us a community-friendly report shape for comparing raw backends against the proxy.
- It can be expanded with harder multi-turn Codex traces where leakage is more likely.

## Serious Stress Baseline

`fixtures/benchmarks/qwen_serious_tool_stress.json`

- 20 cases per run.
- Categories: normal tool use, leak bait, no-tool traps, schema pressure, wrong-tool bait.
- Three direct-Qwen runs on 2026-05-09: 60 generation requests.
- Full report: `runs/qwen_direct_serious_r3.json`.

Overall direct-Qwen result:

- Strict successes: 43/60, or 71.67%.
- Failures: 17/60, or 28.33%.
- Text leaks: 10/60, or 16.67%.
- Reasoning leaks: 0/60.
- Proxy-recoverable leaks: 3/60, or 5%.
- Over-eager tool calls in no-tool cases: 9/60, or 15%.
- Invalid structured tool calls: 4/60, or 6.67%.
- HTTP errors: 0.

Category breakdown:

- Normal tool use: 12/12 strict successes.
- Wrong-tool bait: 6/6 strict successes.
- Leak bait: 14/18 strict successes, with 4 text leaks. Three of those leaks were parseable enough to be proxy-recoverable.
- No-tool traps: 6/15 strict successes. The model often either printed raw tool syntax or converted documentation examples into actual tool calls.
- Schema pressure: 5/9 strict successes. Failures were mostly invalid arguments, such as a string command where Codex expects an argv array.

Key failure cases:

- `markdown_fence_bait`: failed 3/3, but all were proxy-recoverable.
- `no_tool_json_example_bait`: failed 3/3 with text leakage and over-eager tool behavior.
- `no_tool_pythonic_example_bait`: failed 3/3 with text leakage and over-eager tool behavior.
- `no_tool_xml_example_bait`: failed 3/3 by converting documentation requests into actual tool calls.
- `schema_string_command_bait`: failed 2/3 with invalid tool arguments.
- `schema_extra_commentary_arg_bait`: failed 2/3 with invalid tool arguments.

## Raw Model Comparison

These are direct vLLM results before Open Gate repairs. Run counts differ because Qwen was established first and GLM is the new adaptation target.

| Suite | Model | Runs | Strict Success | Text Leaks | Reasoning Leaks | Missed Tool Calls | Invalid Tool Calls | HTTP Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `codex_shell_smoke` | Qwen3-Coder-Next | 1 | 3/3, 100% | 0/3, 0% | 0/3, 0% | 0/3, 0% | 0/3, 0% | 0/3, 0% |
| `codex_shell_smoke` | Qwen3.6-27B | 3 | 9/9, 100% | 0/9, 0% | 0/9, 0% | 0/9, 0% | 0/9, 0% | 0/9, 0% |
| `codex_shell_smoke` | GLM-4.7-Flash | 3 | 0/9, 0% | 6/9, 66.67% | 0/9, 0% | 9/9, 100% | 0/9, 0% | 0/9, 0% |
| `codex_shell_smoke` | DeepSeek-Coder-V2-Lite-Instruct | 3 | 0/9, 0% | 0/9, 0% | 0/9, 0% | 9/9, 100% | 0/9, 0% | 0/9, 0% |
| `codex_shell_smoke` | Gemma-4-E4B-IT | 3 | 9/9, 100% | 0/9, 0% | 0/9, 0% | 0/9, 0% | 0/9, 0% | 0/9, 0% |
| `codex_tool_leak_stress` | Qwen3-Coder-Next | 1 | 3/4, 75% | 0/4, 0% | 0/4, 0% | 0/4, 0% | 0/4, 0% | 0/4, 0% |
| `codex_tool_leak_stress` | GLM-4.7-Flash | 3 | 0/12, 0% | 12/12, 100% | 1/12, 8.33% | 12/12, 100% | 0/12, 0% | 0/12, 0% |
| `codex_tool_leak_stress` | DeepSeek-Coder-V2-Lite-Instruct | 3 | 0/12, 0% | 6/12, 50% | 0/12, 0% | 9/12, 75% | 0/12, 0% | 0/12, 0% |
| `codex_tool_leak_stress` | Gemma-4-E4B-IT | 3 | 0/12, 0% | 12/12, 100% | 0/12, 0% | 0/12, 0% | 0/12, 0% | 0/12, 0% |
| `qwen_serious_tool_stress` | Qwen3-Coder-Next | 3 | 43/60, 71.67% | 10/60, 16.67% | 0/60, 0% | not recorded | 4/60, 6.67% | 0/60, 0% |
| `qwen_serious_tool_stress` | Qwen3.6-27B | 1 | 0/20, 0% | 0/20, 0% | 0/20, 0% | 15/20, 75% | 0/20, 0% | 20/20, 100% |
| `qwen_serious_tool_stress` | GLM-4.7-Flash | 1 | 2/20, 10% | 17/20, 85% | 5/20, 25% | 15/20, 75% | 1/20, 5% | 0/20, 0% |
| `qwen_serious_tool_stress` | DeepSeek-Coder-V2-Lite-Instruct | 3 | 9/60, 15% | 18/60, 30% | 0/60, 0% | 45/60, 75% | 9/60, 15% | 0/60, 0% |
| `qwen_serious_tool_stress` | Gemma-4-E4B-IT | 3 | 27/60, 45% | 33/60, 55% | 0/60, 0% | 4/60, 6.67% | 8/60, 13.33% | 0/60, 0% |

## Model Adaptation Scorecard

This table records the practical Codex-backend status after each model's baseline and OpenGate repair pass. `Known-good` requires more than clean wire format: the model also has to behave reliably enough in live Codex loops.

| Model | Baseline Score | Best OpenGate Repair Score | Live Codex Status | Decision |
| --- | ---: | ---: | --- | --- |
| Qwen3-Coder-Next | `43/60` serious strict successes | `60/60` serious strict successes | Known-good first live smoke | Keep as the known-good local baseline |
| Qwen3-Coder-Next via Qwen Code | Live CSVQL only; Qwen Code `0.19.5`, GX10 vLLM 128k | n/a | Parked after CSVQL: 32k hit Qwen Code context compression after one big file; 128k continued but drifted into a single-file demo and self-debug loop | Treat as harness/model behavior evidence, not an OpenGate repair target; see `docs/qwen3-coder-next.md` |
| Qwen3.6-27B Q8_0 via Qwen Code | Live CSVQL only; Qwen Code `0.19.5`, llama.cpp GGUF Q8_0, 262k | n/a | **Passed CSVQL** after one resume past the 120-minute wall guard; `43/43` pytest, manual CLI checks, and `run_csvql.py` all passed | Record as the first local CSVQL pass for this challenge; harness evidence, not an OpenGate repair target; see `docs/qwen3-6-27b.md` |
| GLM-4.7-Flash | `2/20` serious strict successes | `20/20` repair/full, `19/20` repair/spoon | Synthetic repair validated | Keep as repaired for the GLM leak dialect |
| Qwen3.6-27B | `9/9` direct smoke, but `0/20` direct serious due to protocol errors | `14/17` derived strict successes on partial repair/spoon | Parked after live task-progress/runtime failures | Do not optimize further until a clean proxy-layer failure appears |
| DeepSeek-Coder-V2-Lite-Instruct | `9/60` serious strict successes | `48/60` repair/full, `17/20` repair/spoon | Protocol-clean latest smoke, but behavior-limited | Parked: leaks/protocol are repaired, but the model does not behave reliably enough for Codex; do not repair model behavior |
| Gemma-4-E4B-IT | `27/60` serious strict successes | `19/20` post-repair repair/full and `19/20` post-repair repair/spoon | Smoke completed 3/3 cleanly, but software-build load later failed with upstream timeouts/connection resets and no artifacts | Parked: not usable reliably with Codex beyond smoke; do not repair model behavior |
| Ornith-1.0-35B (uncensored NVFP4) | Not run on the serious suite (Qwen-3.5 base = `qwen3_coder` dialect, zero adaptation) | Channel clean on every live app run (all command-quality issues repaired -> 0, 0 leaks) | **Known-good on the `software_build` app gate**: shipped all 3 apps + a correct Delaunay visualizer; Responses-native upstream; ~3-4x faster than Qwen | Keep as a known-good fast Responses-native MoE; see `docs/ornith.md` |
| GLM-4.5-Air-NVFP4 | Live CSVQL only; synthetic serious suite not run | n/a | Parked after CSVQL: endpoint/tool probe works, but 131k and 64k live runs did not produce a runnable app | Keep as benchmark evidence only; no OpenGate repair target |
| Kimi-Linear-48B-A3B-NVFP4 | Live CSVQL only; direct plain `/responses` sanity passed, tool probes did not produce structured calls | n/a | Parked after CSVQL: native and flattened live runs made zero tool calls and created zero files | Treat as a vLLM/Kimi tool-interface mismatch for this stack; see `docs/kimi-linear-nvfp4.md` |
| MiniMax-M3-MXFP8 | Deployment only; no API endpoint reached | n/a | Blocked before CSVQL: vLLM recognized the MiniMax architecture and MXFP8 path, but model construction OOMed on the 119 GiB GX10 and the offload retry saturated host memory | Treat as deployment-blocked, not a Codex capability result; see `docs/minimax-m3-mxfp8.md` |
| Devstral-Small-2507 | Live CSVQL only; plain Responses sanity passed, forced tool calls worked | n/a | Parked after CSVQL: write-file run landed partial files, but the engine was syntactically broken and CLI/tests were missing | Treat as behavior/artifact failure after a valid protocol fix; see `docs/devstral-small-2507.md` |

## Qwen3-Coder-Next Qwen Code CSVQL Probe (2026-07-03)

After the OpenGate and raw vLLM CSVQL attempts, the same `fixtures\codex_live\csvql_only.json` prompt was run through Alibaba's Qwen Code CLI (`0.19.5`) against the GX10 `Qwen3-Coder-Next` endpoint. Qwen Code was configured as an OpenAI-compatible provider at `http://<gx10-host>:8000/v1`.

The public challenge version of the CSVQL prompt, pass criteria, verifier commands, and expected outputs is `docs\csvql-local-agent-challenge.md`.

Serving facts:

- Model root: `cyankiwi/Qwen3-Coder-Next-AWQ-4bit`
- Tool parser: `qwen3_coder`
- Model config `max_position_embeddings`: `262144`
- 128k serving command used `--max-model-len 131072`; `/v1/models` reported `max_model_len = 131072`
- Qwen Code sandbox could not be used because Docker Desktop's Linux engine was not running, so the run used an isolated `C:\tmp\qwen-code-live\...` workspace with `approval_mode = yolo`

| Run | Context Window | Duration | Exit | Files | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `20260703-082748-qwen3_coder_next_qwencode_csvql` | 32768 | 288.224 s | 0 | 1 | Wrote a single `csvql.py`, then Qwen Code aborted continuation with `COMPRESSION_FAILED_INFLATED_TOKEN_COUNT` (`23638` prompt tokens vs safe limit about `20203`) |
| `20260703-084553-qwen3_coder_next_qwencode_csvql_128k_r2` | 131072 | 2011.884 s | -1, stopped after drift | 7 | Continued past the big write, but drifted into a non-fixture single-file demo and self-debug loop |

The 128k run landed:

- `csvql.py`
- `README.md`
- `TESTS.md`
- `EXAMPLES.md`
- `sample_data/employees.csv`
- `sample_data/products.csv`
- `__pycache__/csvql.cpython-314.pyc`

It missed the required `customers.csv`, `orders.csv`, `run_csvql.py`, `csvql/__init__.py`, `csvql/__main__.py`, and `tests/` suite. Syntax parsing of `csvql.py` passed, but independent verification failed the benchmark contract: `python -m csvql --query ... --table customers=customers.csv --table orders=orders.csv` treated `--query` as a CSV path and failed; `python run_csvql.py ...` failed because `run_csvql.py` did not exist; pytest was not run because there was no tests directory.

Interpretation: the 128k retry proves the first Qwen Code failure was a harness context-budget ceiling, not a GX10/vLLM limit. It does not change the CSVQL capability result. Qwen Code kept using tools and running Python, but it lost the benchmark goal, invented different sample data, and never returned to the required artifact layout. This is behavior/artifact drift, not an OpenGate protocol or repair target.

## Qwen3.6-27B Q8_0 Qwen Code CSVQL Pass (2026-07-05)

The same public CSVQL challenge prompt was then run through Qwen Code CLI `0.19.5` against `Qwen3.6-27B` served by llama.cpp from ggml-org's Q8_0 GGUF. This was not an OpenGate/Codex proxy run. It is recorded here because it is the first local-model run in this experiment that independently passed the full CSVQL artifact contract.

Serving and harness facts:

- Model root: `ggml-org/Qwen3.6-27B-GGUF`
- GGUF file: `Qwen3.6-27B-Q8_0.gguf`, about 28.6 GB
- Served alias: `Qwen3.6-27B-Q8_0`
- Server: llama.cpp `llama-server` on the GX10, OpenAI-compatible endpoint on port `8002`
- Context: `-c 262144`, with Qwen Code `contextWindowSize = 262144`
- Qwen Code: `0.19.5`, OpenAI auth mode, `approval-mode yolo`
- Run folder: `runs\qwen-code-live\20260705-1002-qwen36_27b_q8_0_262k_qwencode_csvql_fullprompt_r3`

| Run | Context Window | Wall Clock | Exit | Files Landed | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `20260705-1002-qwen36_27b_q8_0_262k_qwencode_csvql_fullprompt_r3` | 262144 | about 2h41m including resume | 0 after resume | 12 source/test/fixture files | Passed CSVQL: compile, pytest, manual CLI checks, and `run_csvql.py` entry point |

The initial valid run used the full prompt via stdin and a 120-minute wall-clock guard. It hit only that guard, not a task conclusion. Resuming the same Qwen Code chat with an 8-hour wall-clock limit let it finish at about 2h41m total. The final independent verification was:

```text
python -m compileall -q csvql run_csvql.py
python -m pytest -q
43 passed in 0.24s
```

Manual checks matched the expected challenge outputs for NYC filtering, descending order plus limit, join/filter/order, grouped aggregates, and the standalone `run_csvql.py` entry point.

Important caveats:

- Qwen Code added a local `conftest.py` overriding pytest's `tmp_path` to work around a Windows temp-directory permission issue. This made verification stable, but it is test-environment substrate rather than CSVQL app logic.
- It changed one generated test expectation for `COUNT(column)` from `2` to `3`; that change appears correct because the fixture contains three grouped cities, but it should remain part of the audit trail.
- Before adding the local pytest workaround, it attempted to remove or take ownership of the stale Windows temp directory and was denied. That is a useful harness-safety observation for future local-agent challenges.

Interpretation: this result reverses the prior working hypothesis that current local models could not complete the CSVQL challenge unaided. The successful cell is specific: Qwen3.6-27B, Q8_0 GGUF, llama.cpp, Qwen Code, 262k advertised context, and enough wall-clock budget. The run still needed persistence through slow generation and a wall-clock resume, so the learning is not "any Qwen3.6 setup passes." It is that the right quantization/serving/harness combination can cross the artifact-completion line.

## Devstral-Small-2507 Live CSVQL Probe (2026-07-02/03)

`Devstral-Small-2507` was served from `mistralai/Devstral-Small-2507` with vLLM nightly aarch64, `--max-model-len 65536`, Mistral tokenizer/config/load modes, `--enable-auto-tool-choice`, and `--tool-call-parser mistral`. Full serving notes are in `docs\devstral-small-2507.md`.

The first run exposed a protocol boundary: vLLM/Mistral rejected Codex's mixed hosted and namespace tool list because non-function tools were forwarded and function tools lacked an explicit boolean `strict` field. OpenGate now applies a model-agnostic upstream tool schema normalization step: keep only named function tools, add `strict: false`, wrap hosted `web_search` as a function-shaped tool, and drop unsupported hosted/namespace tools before sending to vLLM.

| Run | Variant | Exchanges | Upstream Errors | Commands | Files Landed | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `20260702-225235-devstral_small_2507_csvql_64k-repair` | before schema filter | 1 | 1 | 0 | 0 | Failed immediately with vLLM schema validation on unsupported tool shapes |
| `20260702-225804-devstral_small_2507_csvql_64k_r2-repair` | schema filter, shell only | 4 | 0 | 3 | 0 | Created directories only, then stopped before writing app files |
| `20260702-230200-devstral_small_2507_csvql_64k_writefile_r3-repair` | schema filter plus `-WriteFileTool` | 9 | 0 | 7 | 5 | Wrote partial files, but no runnable app |

The `r3` run landed `README.md`, `customers.csv`, `orders.csv`, `csvql/__init__.py`, and `csvql/db.py`, but missed `run_csvql.py`, `csvql/__main__.py`, tests, and manual query output. Independent verification failed: `py_compile` found `SyntaxError: unmatched ')'` in `csvql/db.py`, `python -m csvql ...` failed because `csvql.__main__` was missing, and `python run_csvql.py ...` failed because `run_csvql.py` did not exist.

Interpretation: Devstral is a useful middle case. It is not deployment-blocked like MiniMax, and it is not completely outside the tool loop like Kimi. The endpoint works and OpenGate's protocol repair lets the live loop run. The final artifact still fails the benchmark because the implementation is incomplete and syntactically invalid. No CSVQL-specific repair follows from this.

## MiniMax-M3-MXFP8 Deployment Probe (2026-07-02/03)

`MiniMax-M3-MXFP8` was attempted from `MiniMaxAI/MiniMax-M3-MXFP8` with vLLM nightly aarch64, `--max-model-len 65536`, and `--trust-remote-code`. The public model card describes the checkpoint as a 428B-parameter MoE with about 23B activated parameters, MXFP8 quantization, and a 1M-context design; the repository tree is about 444 GB. Full notes are in `docs\minimax-m3-mxfp8.md`.

The GX10 cache was cleared from about 342 GB free to about 560 GB free before launch. vLLM accepted the model configuration, resolved `MiniMaxM3SparseForConditionalGeneration`, selected the MXFP8 MoE path, and started model construction. The non-offloaded launch failed before any usable endpoint came up:

```text
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 4.50 GiB.
GPU 0 has a total capacity of 119.61 GiB of which 2.79 GiB is free.
Including non-PyTorch memory, this process has 112.40 GiB memory in use.
```

An offload retry with `--cpu-offload-gb 8`, `--kv-cache-dtype fp8`, and `--enforce-eager` reached `UVAOffloader`, then saturated the host (`119Gi` of `119Gi` memory used, swap active) and SSH stopped accepting fresh connections. The MiniMax cache was still only about 9.4 MB, so this was not a completed weight-download failure.

Interpretation: MiniMax-M3-MXFP8 is a deployment-blocked target on this single-GPU GX10. It never reached `/v1/models`, direct probes, or the CSVQL harness, so it should not be compared as a CSVQL implementation attempt. No OpenGate repair follows from this result.

## Kimi-Linear-48B-A3B-NVFP4 Live CSVQL Probe (2026-07-02/03)

`Kimi-Linear-48B-A3B-NVFP4` was served from `Firworks/Kimi-Linear-48B-A3B-Instruct-nvfp4` with vLLM nightly aarch64, `--max-model-len 65536`, `--enable-auto-tool-choice`, and `--tool-call-parser kimi_k2`. Full serving notes are in `docs\kimi-linear-nvfp4.md`.

The live benchmark target was the same `fixtures\codex_live\csvql_only.json` write-heavy CSVQL case used for GLM-4.5-Air. Before the run, OpenGate gained a narrow parser for Kimi reserved-token tool-call text of the form `<|reserved_token_163597|>functions.name:0<|reserved_token_163598|>{...}`. The live CSVQL attempts did not exercise that parser because Kimi emitted no parseable tool calls.

| Run | Context Policy | Context Window | Output Cap | Exchanges | Upstream Errors | Commands | Files Landed | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `20260702-212631-kimi_linear_nvfp4_csvql_64k-repair` | `full` / native Responses | 65536 | 16384 | 1 | 0 | 0 | 0 | Failed immediately: final answer was an unrelated email-analytics guide, no tool calls |
| `20260702-212847-kimi_linear_nvfp4_csvql_64k_spoon-repair` | `spoon` / flattened transcript | 65536 | 16384 | 1 | 0 | 0 | 0 | Failed differently: generated a long unrelated puzzle/fish answer, no tool calls |

Direct sanity checks isolate the boundary. A plain `/v1/responses` request obeyed `Reply with exactly: CSVQL sanity OK`. A minimal `/v1/responses` request with one `ping` tool did not call the tool; it wrote explanatory text and a JSON-looking example instead. A comparable `/v1/chat/completions` tool probe also did not return a structured tool call in this serving configuration.

Interpretation: this Kimi run is not a CSVQL near miss. It produced no workspace and no Codex tool activity. The evidence points to a Kimi/vLLM tool-interface incompatibility for this stack, plus poor prompt grounding once Codex's tool schema context is present. There is no task-behavior repair to add in OpenGate; the only accepted code change is the generic reserved-token parser for a Kimi dialect shape observed during probing.

## GLM-4.5-Air-NVFP4 Live CSVQL Probe (2026-07-02/03)

`GLM-4.5-Air-NVFP4` was served from `Firworks/GLM-4.5-Air-nvfp4` with vLLM nightly aarch64, `--tool-call-parser glm47`, `--reasoning-parser glm47`, and tested with both `max_model_len` 131072 and 65536. Full serving and reproduction notes are in `docs\glm-4-5-air-nvfp4.md`.

The live benchmark target was `fixtures\codex_live\csvql_only.json`, a single write-heavy Codex case that asks the model to build a zero-dependency Python SQL query engine over CSV files with CLI entry points, README, pytest coverage, and manual query checks.

| Run | Context Window | Output Cap | Exchanges | Upstream Errors | Invalid Calls Returned | Commands | Files Landed | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `20260702-180525-glm45airnv_csvql-repair` | 131072 | 32768 default | 16 | 0 | 0 | 15 | 6 | Failed partial package; no runnable CLI, tests, or README; final response hit `max_output_tokens` and contained transcript-style fake tool text |
| `20260702-200142-glm45airnv_csvql_64k-repair` | 65536 | 32768 default | 7 | 1 | 0 | 6 | 1 | Failed context arithmetic: prompt 32769 tokens plus requested 32768 output tokens exceeded 65536 |
| `20260702-200615-glm45airnv_csvql_64k_cap16k-repair` | 65536 | 16384 | 24 | 0 | 0 | 23 | 3 | Failed behavior: avoided the 400, but produced only CSV data plus an empty package marker and narrated XML-ish `write_file` calls as text |

The capped 64k run is the cleanest GLM-4.5-Air measurement. It removed the upstream 400, kept returned invalid calls at zero, and still failed to create an engine, parser, CLI, README, or tests. `python -m csvql ...` failed because `csvql.__main__` was missing; `python run_csvql.py ...` failed because the file did not exist.

Comparison against the same CSVQL family of runs:

| Model / Run | Exchanges | Commands | Files | Outcome Shape |
| --- | ---: | ---: | ---: | --- |
| `Qwen3.5-122B-A10B-NVFP4` | 4 | 2 | 2 | Wrote a large `engine.py`, then stopped on a 64k context 400; demo queries still failed |
| `GLM-4.5-Air-NVFP4` 64k cap16k | 24 | 23 | 3 | Avoided context 400, but did not write the app |
| `Kimi-Linear-48B-A3B-NVFP4` 64k native/spoon | 1 each | 0 | 0 | Did not enter the tool loop; produced unrelated prose |
| `Devstral-Small-2507` 64k write-file r3 | 9 | 7 | 5 | Entered the file-writing loop, but produced broken Python and missed CLI/tests |
| `Qwen3-Coder-Next` via Qwen Code 128k r2 | n/a | tool loop active | 7 | Continued past context compression, but lost the requested CSVQL contract and self-debugged a different single-file demo |
| `Qwen3.6-27B Q8_0` via Qwen Code 262k r3 | n/a | 79 Qwen Code tool calls | 12 | Passed full CSVQL after resume; independent compile, pytest, manual CLI, and entry-point checks passed |
| `Qwen3.6-27B-NVFP4` | 44 | 57 | 12 | Much more complete workspace, still correctness-failed |
| `Qwen3.6-35B-A3B-FP8 r5` | 95 | 113 | 14 | Most complete CSVQL attempt so far, still correctness-failed |

Interpretation: `-UpstreamMaxOutputTokens` is a useful benchmark control for constrained context windows, but it does not change the capability conclusion. GLM-4.5-Air-NVFP4's CSVQL failures are model behavior and artifact-completion failures, not protocol, parser, or command-quality bugs for OpenGate to repair.

## Gemma-4-E4B-IT Synthetic Repair Baseline

`Gemma-4-E4B-IT` was served from `google/gemma-4-E4B-it` with vLLM `0.20.1`, `max_model_len` 16384, `--tool-call-parser gemma4`, the Gemma 4 tool chat template, and `--performance-mode interactivity`. Full setup and triage are in `docs\gemma-4-e4b-it.md`.

OpenGate comparison on `qwen_serious_tool_stress`:

| Mode | Context Policy | Strict Success | Text Leaks | Missed Tool Calls | Invalid Tool Calls | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| direct vLLM | n/a | 27/60, 45% | 33/60, 55% | 4/60, 6.67% | 8/60, 13.33% | Protocol-clean raw endpoint; ordinary tool calls are good, bait/schema pressure leaks are common |
| OpenGate `observe` | `full` | 9/20, 45% | 11/20, 55% | 1/20, 5% | 1/20, 5% | Raw output preserved while normalization evidence is recorded |
| OpenGate `repair` before `toolSpec` parser | `full` | 57/60, 95% | 0/60, 0% | 3/60, 5% | 0/60, 0% | Existing repairs removed the main raw leaks and invalid calls |
| OpenGate `repair` before `toolSpec` parser | `spoon` | 18/20, 90% | 0/20, 0% | 2/20, 10% | 0/20, 0% | Revealed duplicated fenced JSON `toolSpec` text after a channel marker |
| OpenGate `repair` after `toolSpec` parser | `full` | 19/20, 95% | 0/20, 0% | 1/20, 5% | 0/20, 0% | Post-repair r1 spot check |
| OpenGate `repair` after `toolSpec` parser | `spoon` | 19/20, 95% | 0/20, 0% | 1/20, 5% | 0/20, 0% | Post-repair r1 spot check |

The accepted repairs are model-agnostic: parse fenced JSON objects shaped as `toolSpec.name` plus `toolSpec.args`, treat fences immediately after `<channel|>` as leaked tool-call blocks, detect Gemma pipe-style `<|tool_call>call:...<tool_call|>` text, and promote Codex transcript-style `assistant tool call ...` JSON command blocks while stripping fabricated `tool output` text. They are covered by `fixtures\regressions\gemma4_toolspec_wrapper_20260529.json`, `fixtures\regressions\gemma4_pipe_skill_call_20260529.json`, and `fixtures\regressions\gemma4_codex_transcript_tool_call_20260529.json`.

Remaining synthetic failures are missed tool calls under invalid-extra-argument schema pressure. They are behavior/schema-pressure misses, not Codex-visible leaks, invalid returned calls, command-quality issues, HTTP errors, or protocol blockers.

Live Codex smoke after the accepted command-quality and channel-delimiter repairs:

| Run | Codex Turns | Upstream Errors | Returned Leaks | Returned Invalid Calls | Returned Command-Quality Issues | Channel Repairs | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `runs\codex-live\20260529-201419-gemma4_e4b_it_live_smoke_workspace_0619_channel_filter-repair` | 3/3 | 0 | 0 | 0 | 0 | 3 | known-good for the current smoke gate |

The channel repair is deliberately narrow: assistant text is reduced to the suffix after the final `<channel|>` marker only when that suffix is non-empty. It does not strip reasoning items or arbitrary planning prose.

Broader software-build load after the pipe/transcript parser repairs:

| Run | Codex Turns | Upstream Errors | Timed-Out Cases | Command Executions | Generated Artifacts | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `runs\codex-live\20260529-210308-gemma4_e4b_it_software_build_0619_transcript_repair_fg-repair` | 1/3 | 3 | 2/3 | 0 | 0 | failed larger build gate |

Interpretation: the repair layer kept returned captures leak-clean, but the larger live run did not produce usable Codex work. The two CLI cases timed out, the web case completed only with an upstream error message, and the target workspace remained empty. This is enough to park Gemma for Codex use: it can pass the small smoke, but it is not reliable for real Codex build workloads, and remaining failures are model/runtime behavior rather than OpenGate repair targets.

## Gemma-4-E4B-IT GX10 Software-Build Re-Run (2026-06-28)

Re-ran the `software_build` `expense_cli` case alone against Gemma-4-E4B-IT now served on the ASUS GX10 (`<gx10-host>:8001`), `repair`/`spoon`, `workspace-write`, with raised timeouts (900 s upstream + case). Run `runs\codex-live\20260628-173546-gemma_expense_cli_gx10-repair`.

| Run | Codex Turns | Upstream Errors | Timed-Out | Command Executions | Artifacts (working) | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `20260628-173546-gemma_expense_cli_gx10-repair` | 1/1 | 0 | no | 6 | 0 | failed app gate (file writes) |

This **revises the parking conclusion above.** On the GX10 the runtime wall is gone: Gemma sustained the agentic loop, completed the turn cleanly in 344 s, and made no upstream errors. The timeouts in the prior run were the prior host, not the model.

The remaining blocker is **a command-quality target, not model/runtime behavior**:

- The model authored a correct `expense_report.py` (real `csv.DictReader`, category/monthly totals, `--category` filter, error handling) in its final message. Its logic is fine.
- It could not get any file onto disk through PowerShell. Every write was malformed Windows quoting: `Set-Content -Path csv -Value 'Date,Category,Amount'`n2024-...'` (literal `` `n `` inside single quotes, mismatched quotes), and retries with **nested** `@"..."@` here-strings inside `powershell -Command @"..."@`. Most returned exit `-1`; the one that "succeeded" wrote a single corrupt line. `expense_report.py` and `README.md` never landed.
- Channel repair worked as designed: 5 upstream text leaks reduced to 1 returned, 3 tool calls promoted.
- But `command_quality` did **not** flag these writes: `returned_command_quality_issues = 0`, `structured_command_quality_quarantines = 0`. The malformed-here-string / bad-`Set-Content` shapes evaded the existing detectors.

Conclusion: for Gemma on this Windows-first stack, the dominant remaining failure is **PowerShell file-write command quality**, which is squarely an OpenGate repair target. This is the next fix to attempt before re-running the cell (one variable, fix once, re-run).

### Re-run after the command-quality fix (`gemma_expense_cli_gx10_r2`)

Added a `single_quoted_literal_newline_file_write` detector + repair (literal `` `n `` in a `Set-Content`/`Out-File` value outside double-quotes/here-strings) and re-ran the identical cell. Run `runs\codex-live\20260628-185059-gemma_expense_cli_gx10_r2-repair`.

| Run | Turns | Upstream Errors | Cmd Exec | CQ issues (upstream→returned) | Repairs | Artifacts (working) | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `...gemma_expense_cli_gx10_r2-repair` | 1/1 | 0 | 2 | 1 → 0 | 1 | 1 of 3 | failed app gate (fabrication) |

The fix worked at its layer: 1 file-write command-quality issue was detected and repaired (0 returned, 0 quarantined), and `sample_expenses.csv` landed **clean with real newlines** — the run-1 corruption is gone. But the failure moved down a layer again. Gemma wrote the CSV, executed 2 commands, then **stopped without writing `expense_report.py` or `README.md`** and returned a final message claiming all three files exist, the tool was tested, and it computes a total of "$320.75". Independent execution of the workspace shows no `expense_report.py` and no Python ever ran. For the `.py` file the model's own message says "(Content was generated inline using Set-Content)" — it narrated the write instead of emitting it, and fabricated the test output.

Interpretation: the command-quality layer is necessary but not sufficient. The remaining blocker is **model behavior** — Gemma avoids the hard multi-line file write and fabricates completion — which OpenGate deliberately does not repair. Catching this requires a harness-owned evaluator that checks artifacts/execution independently rather than trusting the model's self-report. That is an authoring-custody concern (touchstone/TALK), not an OpenGate repair target.

## Qwen3-Coder-Next GX10 Software-Build (2026-06-28)

Strong-model control on the same cell. Ran `software_build/expense_cli` x3 through OpenGate `repair`/`spoon`, `workspace-write`, against Qwen3-Coder-Next on the GX10. Run `runs\codex-live\20260628-203236-qwen_expense_cli_gx10-repair`.

| Model | Turns | Upstream Errors | Cmd Exec | CQ issues (upstream→returned) | Repairs / Quarantines | Leaks | App outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Qwen3-Coder-Next | 3/3 | 0 | 37 | 35 → 0 | 35 / 7 | 0 | **SHIPPED** |

Independent execution of the workspace: all three files present (`expense_report.py`, `sample_expenses.csv`, `README.md`); the CLI runs, prints total ($583.75, hand-verified correct), totals by category and month, and `--category` filters correctly. This is a real, working tool — verified by execution, not self-report.

Two points for OpenGate specifically:

- The command-quality layer carried real weight for the *strong* model too: Qwen emitted **35** malformed file-write/command-quality issues across the three runs, all repaired (`structured_argument_repairs = 35`) or quarantined (7), with **0 returned** and **0 leaks**. The session's `single_quoted_literal_newline_file_write` fix is not Gemma-specific.
- Contrast with Gemma on the identical cell: Gemma wrote 1/3 files and fabricated completion; Qwen ships a correct app. With channel + command-quality repair, capability (the model) is the deciding variable — which is the scale-axis result this run was meant to produce.

Caveat: the three runs shared one workspace, so the verified artifact is the final run's; all three completed exit 0. A per-run-isolated re-run would confirm 3/3 independently.

### Qwen repair vs observe (repair contribution)

Same cell, `observe` mode (repair off), x3 (`runs\codex-live\20260628-205906-qwen_expense_cli_gx10_observe-observe`):

| Mode | Turns | CQ issues returned | Invalid calls returned | Clean capture rate | App outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| `repair` | 3/3 | 0 (of 35) | 0 | ~0.86 | shipped |
| `observe` | 3/3 | 27 (of 27) | 29 | 0.52 | shipped |

Interpretation: repair has a large effect on **channel cleanliness** — without it, 27 command-quality issues and 29 invalid tool calls reach Codex and half the captures are dirty. But for a **strong** model it is **not decisive for the outcome**: Qwen ships either way, recovering through Codex's own retry loop after its bad calls are rejected (consistent with the "Live Codex Observe Vs Repair" note above). Repair's *outcome* value is therefore largest for mid-capability models — good enough to produce mostly-correct work but leaky enough to derail without repair — not for the strongest model (self-recovers) or the weakest (Gemma failed on fabrication regardless). The session's command-quality fix still matters: it is what drives the repaired channel to 0 returned issues.

## Ornith-1.0-35B (uncensored NVFP4) GX10 Software-Build (2026-06-28)

`AEON-7/Ornith-1.0-35B-AEON-Ultimate-Uncensored-NVFP4` (MoE ~3B active, Qwen-3.5 base, DFlash spec-decode), served on the GX10 port 8000 as `ornith`, `--tool-call-parser qwen3_coder`. Same `expense_cli` cell, `repair` x3 (`runs\codex-live\20260628-213642-ornith_expense_cli_gx10-repair`).

| Model | Turns | Cmd Exec | Avg dur/run | CQ issues (up→returned) | Repairs/Quar | Leaks | App outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Ornith-1.0-35B (uncensored) | 3/3 | 21 | ~88 s | 19 → 0 | 20 / 2 | 0 | **SHIPPED** |

Independent execution: all three files present; CLI prints total 543.55 (hand-verified), totals by category and month, `--category` filters correctly (incl. the top-line total). A real, working tool.

Notes for OpenGate:

- **Adaptation was zero**, as predicted: the Qwen-3.5 base means `qwen3_coder` dialect, which OpenGate already handles. No new parser/repair was needed.
- **The uncensored fine-tune did not degrade tool discipline**: 19 malformed file-write/command-quality issues, all repaired/quarantined, 0 returned, 0 leaks, content channel clean (the pre-flight trivial completion was clean too). In line with base Qwen behavior.
- The `single_quoted_literal_newline_file_write` fix fired again (part of the 20 repairs) — third model in a row it carries weight for.

Three-way contrast on the identical cell: Gemma (weak) fabricated 1/3 files; Qwen (strong) shipped; Ornith (35B MoE, uncensored) shipped and ~3-4x faster than Qwen (MoE ~3B active + DFlash). Capability decides; once in the capable tier, the MoE buys speed at equal outcome. Caveat: 3 runs shared one workspace; final-run artifact verified, all exit 0.

### Ornith full software_build suite

Full 3-app suite, `Runs 1` (`runs\codex-live\20260628-214405-ornith_software_build_suite-repair`): all three cases exit 0, 36 command executions, 27 command-quality issues repaired → 0 returned, 0 leaks, 0 invalid.

| App | Surface | Independent verification | Result |
| --- | --- | --- | --- |
| expense_cli | CSV CLI | totals + categories run | shipped |
| incident_log_triage | log CLI | level counts, top errors, `--json` valid, `--since` filters (future date → 0 rows) | shipped |
| habit_tracker_web | single-file web app | real 4.8 KB app: localStorage, add button+fn, complete, streak, delete, 7-day grid | shipped |

Ornith is the first model in this matrix to clear all three surfaces, including the web app where fabrication is harder to hide. Channel discipline held across all three (27 issues repaired, 0 returned). Durations: expense 350 s, log 154 s, web 91 s. Caveat: `Runs 1` per app (single sample each).

**Responses-native upstream (verified).** Ornith's `aeon-vllm-ultimate` stack serves the Responses API natively. The capability probe reported `supports_responses_user_input: true`, `supports_native_tool_history: true`, `requires_flattened_input: false`, zero probe errors. A capture confirms OpenGate sent a Responses-shaped upstream body (`input` / `instructions` / `tools` / `reasoning` / `max_output_tokens`, no `messages`) and the upstream returned an `object: "response"`; OpenGate did **not** flatten to `/v1/chat/completions`. The `flattened_upstream_requests` counter here reflects spoon context compaction applied *within* the Responses shape, not a chat/completions fallback. Notable because Qwen3.6-27B hit protocol walls on native Responses and was parked; Ornith handles it including tools + reasoning. This makes Ornith a clean case for measuring OpenGate in near-passthrough: protocol adaptation is a no-op, so any remaining value is command-quality repair and capture/measurement, not translation.

### Ornith repair vs observe (near-passthrough) — what OpenGate is worth once a model speaks Responses

`expense_cli` x3, `observe` (repair off) (`runs\codex-live\20260628-223858-ornith_expense_cli_gx10_observe-observe`):

| Mode | Turns | CQ returned | Invalid returned | Clean rate | Per-run time | Outcome |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `repair` | 3/3 | 0 (of 19) | 0 | high | ~88 s | 3/3 clean ships |
| `observe` | 2/3 | 33 (of 33) | 28 | 0.49 | 77 / 320 / 916 s (1 timeout) | 2/3 ship (messy), 1 fail |

Because Ornith is Responses-native, `observe` here is effectively pass-through: OpenGate translates nothing, it only declines to repair. The result isolates the command-quality layer's value. Without repair, 33 command-quality issues and 28 invalid calls reach Codex, clean capture halves, and the model thrashes against its own malformed commands until one run hits the 900 s timeout. The final workspace still shipped a working CLI (the capable model recovers via Codex retries 2/3 of the time), but reliability dropped from 3/3 to 2/3 and latency variance exploded.

Conclusion for Responses-native models: OpenGate's *translation* job is moot, but its *command-quality* job still earns its keep — here it converted thrash-prone 2/3 (with a hard timeout) into clean, fast 3/3. This is a stronger result than Qwen's observe contrast, where the strongest model self-recovered 3/3 even pass-through. OpenGate shifts from translator to reliability/latency quality-gate, not zero value.

### Ornith complex single-file build (Delaunay visualizer)

A hard non-suite probe (`runs\codex-live\20260628-231828-ornith_delaunay_viz-repair`): a single-file animated Delaunay triangulation web app. One turn, 836 s, 13 command-quality issues repaired → 0, 0 leaks; output complete (per-turn cap was 16384 and did not bind). The triangulation was independently verified correct (Bowyer-Watson, 0 empty-circumcircle violations across ~97k checks); it missed two UI controls. OpenGate note: the channel stayed clean on a large single-file build, and the per-turn output cap is now `upstream_max_output_tokens = 32768` in the local `opengate.toml` to remove truncation risk on big artifacts.

## DeepSeek-Coder-V2-Lite Synthetic Repair Baseline

`DeepSeek-Coder-V2-Lite-Instruct` was served from `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct` with vLLM `0.20.1`, `max_model_len` 16384, `--tool-call-parser deepseek_v3`, the DeepSeek v3 tool chat template, and `--performance-mode interactivity`. Full setup and repair triage are in `docs\deepseek-coder-v2-lite.md`.

Direct synthetic runs were protocol-clean: zero HTTP, transport, or role-shape errors. The dominant raw failure was unstructured tool text rather than endpoint rejection.

OpenGate comparison on `qwen_serious_tool_stress`:

| Mode | Context Policy | Strict Success | Text Leaks | Missed Tool Calls | Wrong Tools | Invalid Tool Calls | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| direct vLLM | n/a | 9/60, 15% | 18/60, 30% | 45/60, 75% | 6/60, 10% | 9/60, 15% | Raw endpoint completes but often emits tool syntax as text |
| OpenGate `observe` | `full` | 3/20, 15% | 6/20, 30% | 15/20, 75% | 2/20, 10% | 3/20, 15% | Raw output preserved while normalization opportunities are recorded |
| OpenGate `repair` before DeepSeek parser | `full` | 12/60, 20% | 0/60 legacy markers | 42/60, 70% | 6/60, 10% | 0/60, 0% | Capture scan found DeepSeek delimiters not yet detected as leaks |
| OpenGate `repair` before DeepSeek parser | `spoon` | 9/20, 45% | 1/20 legacy markers | 10/20, 50% | 0/20, 0% | 0/20, 0% | Same parser family still needed repair |
| OpenGate `repair` after accepted repairs | `full` | 48/60, 80% | 0/60, 0% | 12/60, 20% | 3/60, 5% | 0/60, 0% | DeepSeek delimiters, partial markers, `function.parameters`, and negative-tool diagnostics repaired |
| OpenGate `repair` after accepted repairs | `spoon` | 17/20, 85% | 0/20, 0% | 3/20, 15% | 0/20, 0% | 0/20, 0% | Compact-context setting kept the zero-leak and zero-invalid guarantee |

The accepted repair candidates were model-agnostic and are now covered by tests and regression fixtures: parse DeepSeek/vLLM delimited function text into Responses `function_call` items, strip partial DeepSeek close/output markers, treat JSON `function.parameters` as arguments when `function.arguments` is absent, avoid adding diagnostic shell calls after negative-tool-intent no-tool prompts, and neutralize residual literal `<tool_call>` tag text.

Live Codex smoke is no longer protocol-blocked. The first `repair/spoon` smoke completed `3/3` Codex turns without leaks or policy blocks, but all `3/3` upstream requests returned HTTP 400 validation errors because OpenGate's request-diet compaction dropped nested child tools from Codex MCP namespace schemas. OpenGate now preserves nested namespace tools recursively. The latest workspace-write `repair/spoon` smoke recorded `3/3` completed turns, `0` upstream errors, `1` command execution, zero returned leaks, zero returned invalid calls, zero returned command-quality issues, and `returned_clean_capture_rate = 1.0`. It remains behavior-limited, not known-good, because the no-tool documentation answer still includes DeepSeek chat-template preamble text. We are parking it here: the remaining issue is model behavior, and OpenGate should not add task-steering or model-behavior repair for this target.

## Qwen3.6-27B Validation Status

`Qwen3.6-27B` was served from `Qwen/Qwen3.6-27B` with vLLM `--max-model-len 65536`, `--reasoning-parser qwen3`, `--enable-auto-tool-choice`, and `--tool-call-parser qwen3_coder`. The recorded score path is:

1. Direct `codex_shell_smoke`, three runs: complete, `9/9` strict successes.
2. Direct `qwen_serious_tool_stress`, one run: complete, `0/20` due to protocol incompatibility, not model leakage.
3. OpenGate `repair/full` on `qwen_serious_tool_stress`: still pending.
4. OpenGate `repair/spoon` on `qwen_serious_tool_stress`, one partial run: `17/20` captures completed before the external command timeout, `14/17` derived strict successes, zero returned leaks, invalid calls, or command-quality issues.
5. Live Codex software-build and Refero-style artifact runs: parked, because the remaining failures were task-progress/runtime behavior rather than clean proxy repair.

Prepared commands and result placeholders are in `docs\qwen3-6-27b.md`.

OpenGate `0.6.9` changes benchmark interpretation for this case: `HTTP 400: Unexpected message role` is classified as a protocol incompatibility, and direct raw results should not be presented as ordinary tool-call failures. The proxy path addresses this by probing upstream role support and flattening unsupported native Responses input.

Qwen3.6 should not be treated as the next OpenGate optimization target right now. The reason is not a single missing repair rule: direct serious requests are rejected by the vLLM Responses endpoint before generation, while live Codex runs that get past protocol adaptation show long stalls, planning loops, wrong tool choice, malformed file writes, and task-progress drift. The temporary artifact-pressure fixes improved one Refero `index.html` path, but they inferred task state from prompts and tool output, which crosses OpenGate's intended boundary. As of OpenGate `0.6.17`, those task-steering hooks are removed; Qwen3.6 stays recorded as a benchmark target until a repeatable failure clearly belongs to transport, protocol adaptation, tool-call repair, or command-quality quarantine.

## GLM-4.7-Flash Direct Baseline

The GLM endpoint was served as `GLM-4.7-Flash` from `zai-org/GLM-4.7-Flash` with vLLM `max_model_len` 131072, `--tool-call-parser glm47`, and `--reasoning-parser glm45`. Full serving notes are in `docs\vllm-notes.md`.

Report files:

- `runs\glm47_flash_direct_smoke_r3.json`
- `runs\glm47_flash_direct_leak_stress_r3.json`
- `runs\glm47_flash_direct_serious_r1.json`

Overall direct-GLM result:

- Smoke suite: 0/9 strict successes, 6/9 text leaks, 9/9 missed structured tool calls.
- Leak-stress suite: 0/12 strict successes, 12/12 text leaks, 12/12 missed structured tool calls.
- Serious suite: 2/20 strict successes, 18/20 leaks, 15/20 missed tool calls, 3/20 over-eager tool calls, 1/20 invalid tool calls.

Open Gate GLM validation on `qwen_serious_tool_stress`:

| Mode | Context Policy | Strict Success | Text Leaks | Reasoning Leaks | Proxy Recoverable | Missed Tool Calls | Invalid Tool Calls |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| direct vLLM | n/a | 2/20, 10% | 17/20, 85% | 5/20, 25% | 0/20, 0% | 15/20, 75% | 1/20, 5% |
| Open Gate `repair` before GLM text parser | `full` | 2/20, 10% | 16/20, 80% | 9/20, 45% | 0/20, 0% | 13/20, 65% | 0/20, 0% |
| Open Gate `repair` before GLM text parser | `spoon` | 2/20, 10% | 15/20, 75% | 8/20, 40% | 2/20, 10% | 13/20, 65% | 1/20, 5% |
| Open Gate `0.6.0 repair` | `full` | 20/20, 100% | 0/20, 0% | 0/20, 0% | 0/20, 0% | 0/20, 0% | 0/20, 0% |
| Open Gate `0.6.0 repair` | `spoon` | 19/20, 95% | 0/20, 0% | 0/20, 0% | 0/20, 0% | 1/20, 5% | 0/20, 0% |

Open Gate `0.6.0` solves the repeatable GLM leakage shape without requiring the user to name the model. The linter recognizes GLM's XML-ish mini-format, promotes parseable leaked calls into Responses `function_call` items, repairs schema-cleanable arguments, and scrubs residual raw syntax from assistant and reasoning text.

The dominant raw failure was not HTTP or vLLM rejection. GLM returned HTTP 200, but emitted tool calls as assistant text, for example:

```text
<tool_call>shell<arg_key>command</arg_key>...
```

That shape was not converted by vLLM into Responses `function_call` items, so Codex-style clients saw leaked assistant text rather than executable tool calls. The `repair/full` result is now the preferred GLM setting for this synthetic suite. `repair/spoon` is still useful for long live Codex histories, but on this short synthetic suite it missed one case where GLM emitted an incomplete fenced JSON `tool_calls` block; Open Gate deliberately does not infer a tool call from incomplete JSON.

Final GLM report files:

- `runs\glm47_flash_open_gate_repair_glm_tags_v3_r1.json`
- `runs\glm47_flash_open_gate_repair_spoon_glm_tags_v4_r1.json`

## First Proxy Baseline

Open Gate buffered-upstream proxy mode was checked on 2026-05-09 with:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_proxy_benchmark.ps1 -Runs 3 -Label qwen_open_gate_serious_r3 -Output runs\qwen_open_gate_serious_r3.json
```

The proxy forwards `/v1/responses` to direct Qwen/vLLM with `stream: false`, normalizes the upstream response, and returns a Responses-shaped result. For interactive Codex streams, it sends Responses heartbeat events while waiting for that buffered upstream response. It currently handles:

- Stripping leaked tool syntax from assistant text.
- Promoting parseable leaked tool calls into structured `function_call` items when the prompt does not indicate no-tool/documentation intent.
- Suppressing structured tool calls when the latest user prompt clearly asks not to use tools.
- Repairing simple schema mistakes, including string `shell.command` values and extra arguments when the schema disallows them.
- Repairing nested `powershell.exe -Command` shell calls before Codex policy sees them.

Proxy mode now has two comparison settings:

- `repair`: return normalized responses to Codex or the benchmark caller.
- `observe`: record the normalization report but return the raw upstream response.

Raw Qwen vs Open Gate on `qwen_serious_tool_stress`, 60 requests each:

| Metric | Raw Qwen | Open Gate |
| --- | ---: | ---: |
| Strict success | 43/60, 71.67% | 60/60, 100% |
| Failures | 17/60, 28.33% | 0/60, 0% |
| Text leaks | 10/60, 16.67% | 0/60, 0% |
| Reasoning leaks | 0/60, 0% | 0/60, 0% |
| Over-eager tool calls | 9/60, 15% | 0/60, 0% |
| Invalid tool calls | 4/60, 6.67% | 0/60, 0% |
| HTTP errors | 0/60, 0% | 0/60, 0% |

This began as a benchmark-scope result. The interactive proxy now keeps streamed Codex sockets alive with Responses heartbeat events while preserving the same normalization guarantee.

Newer reports also include `command_quality_issues_rate`. This metric catches structured tool calls that parse as JSON but are likely to be rejected by Codex policy. Older saved reports in `runs\` predate this metric.

For whole-Codex measurements, use `scripts\run_codex_live_benchmark.ps1` and `open_gate.codex_report`. See `docs\live-codex-benchmark.md`.

## Live Codex Observe Vs Repair

Checked on 2026-05-09 with `fixtures\codex_live\smoke.json`, one run per mode.

| Metric | Repair | Observe |
| --- | ---: | ---: |
| Codex turns completed | 3/3 | 3/3 |
| Policy-blocked Codex runs | 0 | 1 |
| Blocked-by-policy captures | 0 | 3 |
| Returned command-quality issues | 0 | 1 |
| Returned invalid tool calls | 0 | 1 |
| Returned clean capture rate | 100% | 42.86% |

The important nuance is that observe mode eventually recovered, but only after Codex saw and rejected a bad raw tool call. Repair mode removed that failed intermediate step.

## Interactive Smoke

Checked on 2026-05-09 with `scripts/run_codex_proxy_smoke.ps1`.

- Plain `codex exec` assistant-message streaming through Open Gate worked.
- A shell-tool prompt also worked end to end: Codex accepted the streamed `function_call`, ran the shell command, sent the tool output back through Open Gate, and received the final assistant answer.
- The tool prompt revealed one realistic model blemish: Qwen first emitted a nested PowerShell command rejected by Codex policy, then recovered with a simpler allowed command. This is now covered by `fixtures\regressions\qwen_nested_powershell_20260509.json`.
