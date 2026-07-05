# CSVQL Next Experiments

This checklist tracks the next CSVQL experiment cells after the first confirmed local pass:

`Qwen3.6-27B-Q8_0` GGUF, llama.cpp, Qwen Code `0.19.5`, 262k context, full CSVQL pass on 2026-07-05.

The goal is to isolate which part of the winning cell mattered most: model family, quantization fidelity, serving stack, harness, context budget, or wall-clock budget.

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

  Purpose: isolate Qwen3.6 model-size/architecture effect under the same high-fidelity GGUF plus Qwen Code pattern. Earlier Qwen3.6-35B-A3B FP8-style runs came close but failed correctness.

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

- [ ] **3. Qwen3-Coder-30B-A3B-Instruct-GGUF Q8_0 through Qwen Code**

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

- [ ] **4. GLM-4.5-Air-GGUF Q8_0 through OG/Codex**

  Target: `GLM-4.5-Air` GGUF at `Q8_0`, likely from `unsloth/GLM-4.5-Air-GGUF`.

  Purpose: retest GLM under the high-fidelity GGUF hypothesis, but keep the OpenGate/Codex harness because the earlier GLM live CSVQL failures were observed there.

  Risk: the Q8_0 listing is about 117 GB, with larger 8-bit variants around 128 GB. This is close to the GX10 memory cliff before KV cache. Start with a conservative context window and record deployment failure separately from CSVQL failure if the server cannot expose a usable endpoint.

  Suggested setup:

  - Server: llama.cpp if it can load the model and expose an OpenAI-compatible endpoint.
  - OpenGate: `repair`, `upstream_input_mode = auto`, `context_policy = spoon`.
  - Codex live suite: `fixtures\codex_live\csvql_only.json`.
  - Context: begin with 32k or 64k to avoid confusing deployment pressure with model behavior.
  - Wall-clock: long guard, but stop early if the server is memory-bound before generation.

  Evidence fields:

  - Run folder:
  - Context window:
  - Wall clock:
  - Server memory result:
  - Commands:
  - Files landed:
  - Independent verifier:
  - Verdict:

## Status Legend

- `Pending`: not started.
- `Running`: model/harness process is active.
- `Verifier`: model run ended and independent checks are in progress.
- `Passed`: all common acceptance gates passed.
- `Failed`: model produced artifacts but the independent verifier failed.
- `Blocked`: deployment, memory, protocol, or harness setup prevented a valid CSVQL attempt.
