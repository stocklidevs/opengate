# CSVQL Next Experiments

This checklist tracks the next CSVQL experiment cells after the first confirmed local pass:

`Qwen3.6-27B-Q8_0` GGUF, llama.cpp, Qwen Code `0.19.5`, 262k context, full CSVQL pass on 2026-07-05.

The goal is to isolate which part of the winning cell mattered most: model family, quantization fidelity, serving stack, harness, context budget, or wall-clock budget.

Latest learning: the confirmed pass reproduced through both Qwen Code and OG/Codex only for `Qwen3.6-27B-Q8_0` so far. The newest Q8_0 coder-flavored cell, `Qwen3-Coder-30B-A3B-Instruct`, deployed cleanly at 128k but failed by fabricating work. The 35B question is still open, and external reports now also point at a possible Qwen3.6-35B NVFP4 weakness versus GGUF in agentic workflows. Treat experiment 2 as the clean isolation test for that suspicion.

## Common Acceptance Gate

Each experiment should be marked complete only after an independent verifier, outside the model's own self-report, confirms:

- [ ] `python -m compileall -q csvql run_csvql.py`
- [ ] `python -m pytest -q`
- [ ] Manual query 1: NYC customer filter
- [ ] Manual query 2: descending name order with `LIMIT 2`
- [ ] Manual query 3: join, filter, and order by amount
- [ ] Manual query 4: grouped city aggregates
- [ ] `python run_csvql.py ...` entry point
- [ ] Result documented in `docs/benchmark-notes.md`
- [ ] Result documented in `docs/live-codex-benchmark.md`
- [ ] Model-specific note updated or created under `docs/`

Use the public challenge prompt and expected outputs from `docs/csvql-local-agent-challenge.md`.

## Experiment Queue

- [x] **1. Current Qwen winner through OG/Codex**

  Target: `Qwen3.6-27B-Q8_0` GGUF, served by llama.cpp, routed through OpenGate and Codex instead of Qwen Code.

  Purpose: isolate harness effect. The same model, quantization, and llama.cpp server already passed with Qwen Code. This run tests whether OpenGate/Codex can also carry the winning model to completion.

  Suggested setup:

  - Server: llama.cpp OpenAI-compatible endpoint, same Q8_0 GGUF as the passing run.
  - OpenGate: `repair`, `upstream_input_mode = auto`, `context_policy = spoon` unless testing full context deliberately.
  - Codex live suite: `fixtures\codex_live\csvql_only.json`.
  - Wall-clock: no 120-minute cutoff; use a long guard comparable to the Qwen Code pass.

  Evidence fields:

  - Run folder: `runs\codex-live\20260705-144755-qwen36_27b_q8_0_262k_ogcodex_csvql_writefile-repair`
  - Run folder: `runs\codex-live\20260705-145052-qwen36_27b_q8_0_262k_ogcodex_csvql_writefile_flatten-repair`
  - Run folder: `runs\codex-live\20260705-151104-qwen36_27b_q8_0_262k_ogcodex_csvql_flatten_no_writefile-repair`
  - Run folder: `runs\codex-live\20260705-153826-qwen36_27b_q8_0_262k_ogcodex_csvql_flatten_no_writefile_r2-repair`
  - Context window: `262144`
  - Wall clock: native failure in about 26s; flattened write-file attempt stopped after a repeat loop; first flattened no-write-file attempt was aborted prematurely; completed r2 rerun took `3192.153` seconds, about 53m12s.
  - Commands: native Responses first, then forced `-UpstreamInputMode flatten`; clean reruns used `-DisableWriteFileTool` to override repo config and force shell-only operation.
  - Files landed: completed r2 run landed 12 non-cache files, including `csvql/parser.py`, `csvql/engine.py`, `csvql/cli.py`, `run_csvql.py`, fixtures, README, and `tests/test_csvql.py`.
  - Independent verifier: `python -m compileall -q csvql run_csvql.py` passed with `PYTHONPYCACHEPREFIX` redirected around a local Windows `__pycache__` ACL issue; `python -B -m pytest -q` returned `30 passed in 0.19s`; all four manual queries exited 0 with the expected rows; `python run_csvql.py ...` returned the same NYC rows as `python -m csvql`.
  - Verdict: Passed. The same Qwen/Q8_0/llama.cpp cell that passed under Qwen Code also completed through OpenGate/Codex once the transcript was flattened, write-file injection was disabled, and the run was allowed enough wall-clock time.

  Attempt notes:

  - Native OpenGate/Codex failed before model work because llama.cpp's Qwen chat template rejected Codex's native message ordering: `System message must be at the beginning`.
  - Forced flattened input fixed the Jinja failure.
  - With `write_file` injection active, Qwen repeatedly wrote `csvql/__init__.py`; the translated history came back through Codex as `shell`, and the model kept deciding to "switch" to `write_file`.
  - The first no-write-file attempt was stopped too early while remote decoding was still active, so it is not a valid failure verdict.
  - The clean r2 rerun completed 39 proxy exchanges with zero upstream errors, zero returned leaks, zero returned invalid tool calls, and three structured argument repairs. It built tests, fixed failures, and independently passed the challenge queries.
  - The benchmark runner now has `-UpstreamInputMode` and `-DisableWriteFileTool` so future variants can make these settings explicit instead of inheriting `opengate.toml`.

- [ ] **2. Qwen3.6-35B-A3B-GGUF Q8_0 through Qwen Code**

  Target: `ggml-org/Qwen3.6-35B-A3B-GGUF:Q8_0`.

  Purpose: isolate Qwen3.6 model-size/architecture effect under the same high-fidelity GGUF plus Qwen Code pattern. Earlier Qwen3.6-35B-A3B FP8/NVFP4-style runs came close but failed correctness, and outside agentic-workflow reports now suggest the 35B NVFP4 path may underperform the 35B GGUF path.

  Suggested setup:

  - Server: llama.cpp OpenAI-compatible endpoint.
  - Quantization: `Q8_0`, about 36.9 GB model file.
  - Harness: Qwen Code `0.19.5` or later, OpenAI provider.
  - Prompt delivery: full CSVQL prompt via stdin with `--prompt ""`.
  - Wall-clock: start with an 8-hour guard.

  Evidence fields:

  - Run folder:
  - Context window:
  - Wall clock:
  - Qwen Code tool calls:
  - Files landed:
  - Independent verifier:
  - Verdict:

- [ ] **3. Qwen3-Coder-30B-A3B-Instruct-GGUF Q8_0**

  Target: `Qwen3-Coder-30B-A3B-Instruct` GGUF at `Q8_0`, for example `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q8_0` or another verified Q8_0 repo.

  Purpose: test whether a purpose-built Qwen coder model at high-fidelity Q8_0 beats the general Qwen3.6-27B result. This is separate from the earlier Qwen3-Coder-Next run, which failed the CSVQL contract even through Qwen Code at 128k.

  Suggested setup:

  - Server: llama.cpp OpenAI-compatible endpoint.
  - Quantization: `Q8_0`, about 32.5 GB for the Unsloth GGUF listing.
  - Harness: Qwen Code `0.19.5` or later, OpenAI provider.
  - Prompt delivery: full CSVQL prompt via stdin with `--prompt ""`.
  - Wall-clock: start with an 8-hour guard.

  Evidence fields:

  - Run folder:
  - Context window:
  - Wall clock:
  - Qwen Code tool calls:
  - Files landed:
  - Independent verifier:
  - Verdict:

  OG/Codex 128k subcell:

  - Run folder: `runs\codex-live\20260705-182317-qwen3coder30b_a3b_q8_0_128k_ogcodex_csvql_flatten_no_writefile-repair`
  - Context window: `131072`
  - Wall clock: `1170.566` seconds, about 19m31s.
  - Server memory result: Q8_0 loaded successfully in llama.cpp; 30.53B/A3B MoE, 49/49 layers offloaded, about 30 GiB CUDA model buffer, about 6.4 GiB q8_0 KV cache at 128k.
  - Commands: forced flattened input with `-UpstreamInputMode flatten`, `-ContextPolicy full`, and `-DisableWriteFileTool`.
  - Files landed: zero files; only `csvql/` and `csvql/csvql/` directories.
  - Independent verifier: `python -B -m compileall -q csvql run_csvql.py` failed because `run_csvql.py` did not exist.
  - Verdict: Failed for the OG/Codex 128k subcell. The model fabricated a completed tool transcript and final success report without creating artifacts. The Qwen Code variant remains untested.

  Attempt notes:

  - The run completed from the Codex harness perspective with zero upstream errors and zero returned invalid tool calls.
  - The model generated fake `assistant tool call shell ...` transcript text containing pretend file writes and pretend test/manual-query outputs.
  - OpenGate recorded text leaks and promotion candidates, but did not promote the fake transcript because real structured calls were already present.
  - Detailed notes are in `docs\qwen3-coder-30b-a3b-instruct-gguf.md`.

- [ ] **4. GLM-4.5-Air-GGUF through OG/Codex**

  Target: `GLM-4.5-Air` GGUF, likely from `unsloth/GLM-4.5-Air-GGUF`. The original high-fidelity target remains `Q8_0`; the first feasibility run used `UD-Q4_K_XL` because Q8_0 is close to the GX10 memory cliff before KV cache.

  Purpose: retest GLM under the high-fidelity GGUF hypothesis, but keep the OpenGate/Codex harness because the earlier GLM live CSVQL failures were observed there.

  Risk: the Q8_0 listing is about 117 GB, with larger 8-bit variants around 128 GB. This is close to the GX10 memory cliff before KV cache. Start with a conservative context window and record deployment failure separately from CSVQL failure if the server cannot expose a usable endpoint.

  Suggested setup:

  - Server: llama.cpp if it can load the model and expose an OpenAI-compatible endpoint.
  - OpenGate: `repair`, `upstream_input_mode = auto`, `context_policy = spoon`.
  - Codex live suite: `fixtures\codex_live\csvql_only.json`.
  - Context: begin with 32k or 64k to avoid confusing deployment pressure with model behavior.
  - Wall-clock: long guard, but stop early if the server is memory-bound before generation.

  Evidence fields:

  - Run folder: `runs\codex-live\20260705-172631-glm45air_udq4xl_64k_ogcodex_csvql_flatten_no_writefile-repair`
  - Run folder: `runs\codex-live\20260705-173954-glm45air_udq4xl_64k_ogcodex_csvql_auto_no_writefile_r2-repair`
  - Context window: `65536`
  - Wall clock: forced-flatten run took `518.578` seconds; auto/native retry took `1313.724` seconds, about 21m54s.
  - Server memory result: `UD-Q4_K_XL` loaded successfully in llama.cpp; 63.06 GiB GGUF, 48/48 layers offloaded, about 62 GiB CUDA model buffer, about 6.1 GiB q8_0 KV cache at 64k. Q8_0 was not loaded in this pass.
  - Commands: forced-flatten run used `-UpstreamInputMode flatten`, `-ContextPolicy full`, `-DisableWriteFileTool`; retry used `-UpstreamInputMode auto`, `-ContextPolicy full`, `-DisableWriteFileTool`.
  - Files landed: forced-flatten run landed two broken nested files; auto/native retry landed zero app files.
  - Independent verifier: forced-flatten `compileall` failed on invalid bytes in `csvql/__init__.py`, invalid syntax in `csvql/engine.py`, and missing `run_csvql.py`; auto/native `compileall` failed because `csvql` and `run_csvql.py` did not exist.
  - Verdict: Failed for the `UD-Q4_K_XL` feasibility subcell. The model/server can run on the GX10, but OG/Codex did not get a usable CSVQL app. Q8_0 remains a separate deployment-risk target, not a passed or behavior-measured cell.

  Attempt notes:

  - The forced-flatten run reached artifact attempts, but GLM wrote brittle PowerShell file commands and corrupt Python.
  - The forced-flatten run ended with a llama.cpp 500 after the flattened transcript exposed a raw `<tool_call>request_plugin_install...</tool_call>` block from an earlier GLM turn.
  - The auto/native retry avoided that upstream parser error and had zero returned leaks, invalid calls, or command-quality issues, but the model drifted into a 16k-token search for Codex skill files and produced no app files.
  - Detailed notes are in `docs\glm-4-5-air-gguf.md`.

## Status Legend

- `Pending`: not started.
- `Running`: model/harness process is active.
- `Verifier`: model run ended and independent checks are in progress.
- `Passed`: all common acceptance gates passed.
- `Failed`: model produced artifacts but the independent verifier failed.
- `Blocked`: deployment, memory, protocol, or harness setup prevented a valid CSVQL attempt.
