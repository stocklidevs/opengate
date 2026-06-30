# Ornith-1.0-35B Compatibility

This note records the OpenGate validation status for `Ornith-1.0-35B`, served as the
uncensored NVFP4 build `AEON-7/Ornith-1.0-35B-AEON-Ultimate-Uncensored-NVFP4`
(base: `deepreinforce-ai/Ornith-1.0-35B`).

## Status

- Model repository: `AEON-7/Ornith-1.0-35B-AEON-Ultimate-Uncensored-NVFP4`
- Base model: `deepreinforce-ai/Ornith-1.0-35B` (MoE, 35B total / ~3B active, post-trained on Qwen 3.5, reasoning model, self-scaffolding agentic coder, 262K context)
- Served model name: `ornith`
- Server: vLLM via the `ghcr.io/aeon-7/aeon-vllm-ultimate` image on an ASUS GX10 (Blackwell GB10, NVFP4)
- OpenGate target version: `0.6.20`
- OpenGate mode: `repair`
- Upstream input mode: `auto`
- Context policy: `spoon`
- Validation status: **known-good for the live `software_build` app gate** — the first model in this lab to ship all three apps, plus a correct from-scratch Delaunay visualizer. Responses-native upstream.
- Validation date: `2026-06-28`

## vLLM Setup

Served through the AEON `aeon-vllm-ultimate` image, which bundles NVFP4 +
Gated-DeltaNet + DFlash speculative decoding support for Blackwell (GB10):

```bash
docker pull ghcr.io/aeon-7/aeon-vllm-ultimate:latest

# Main model (NVFP4)
huggingface-cli download AEON-7/Ornith-1.0-35B-AEON-Ultimate-Uncensored-NVFP4 \
  --local-dir ~/models/ornith-nvfp4

# DFlash drafter (recommended for Ornith)
huggingface-cli download AEON-7/AEON-DFlash-Qwen3.6-35B-A3B \
  --local-dir ~/models/ornith-dflash-drafter

docker run -d --name ornith \
  --gpus all --ipc=host --net=host \
  -e TORCH_CUDA_ARCH_LIST=12.1a \
  -e CUTE_DSL_ARCH=sm_121a \
  -e VLLM_USE_FLASHINFER_SAMPLER=1 \
  -v ~/models/ornith-nvfp4:/model:ro \
  -v ~/models/ornith-dflash-drafter:/drafter:ro \
  --entrypoint vllm \
  ghcr.io/aeon-7/aeon-vllm-ultimate:latest \
  serve /model --served-model-name ornith \
  --port 8000 \
  --quantization compressed-tensors \
  --speculative-config '{"method":"dflash","model":"/drafter","num_speculative_tokens":6}' \
  --gpu-memory-utilization 0.6 \
  --max-model-len 262144 \
  --max-num-seqs 16 \
  --max-num-batched-tokens 16384 \
  --mamba-cache-dtype float32 \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --enable-prefix-caching \
  --trust-remote-code
```

Key flags:

- `--quantization compressed-tensors` — required for the NVFP4 weights.
- `--tool-call-parser qwen3_coder` — Ornith's Qwen-3.5 base means it speaks the
  Qwen tool-call dialect OpenGate already handles, so adaptation is effectively
  zero. (`qwen3_xml` is the vLLM alternative; `qwen3_coder` was used here.)
- `--reasoning-parser qwen3` — Ornith is a reasoning model; the parser keeps its
  thinking out of the assistant content channel.
- `--speculative-config dflash` — the biggest speedup (~2.4x decode) using the
  paired DFlash drafter.
- `--gpu-memory-utilization 0.6`, `--max-num-seqs 16` — safe limits for the GB10
  unified memory with DFlash buffers; higher `max-num-seqs` can OOM.
- `--mamba-cache-dtype float32` — required by the Gated-DeltaNet hybrid attention.
- `--port 8000` — the container uses `--net=host`; point OpenGate's upstream at
  this port. (The default vLLM port is `8000`; add `--port` to match your setup.)

The container exposes an OpenAI-compatible `/v1` server (chat/completions and a
native `/v1/responses`) on the host network.

## OpenGate Setup

Use a local ignored `opengate.toml` with `model = "auto"` so OpenGate detects the
served vLLM model. Point `[upstream]` at the host and port serving Ornith (use the
GX10 host when OpenGate runs on a different machine):

```toml
[upstream]
scheme = "http"
host = "127.0.0.1"   # or the GX10 host when OpenGate runs elsewhere
port = 8000
path = "/v1"
model = "auto"
capability_probe = "auto"
capability_probe_timeout = 8

[proxy]
normalization_mode = "repair"
upstream_input_mode = "auto"
context_policy = "spoon"
upstream_max_output_tokens = 32768
```

`upstream_max_output_tokens` is raised from the `4096` default to give large
single-file builds (e.g. the Delaunay app) room to complete in one turn without
truncation. It did not bind in practice, but it removes the risk for big artifacts.

Expected startup behavior:

- `/v1/models` reports `ornith`.
- `/health` reports `model = ornith`, autodetected.
- Capability probing records native Responses support (see below).

## Serving Evidence

- `/v1/models`: `id = ornith`.
- OpenGate `/health`: `model = ornith`, `normalization_mode = repair`,
  `upstream_input_mode = auto`, `model_source = cli/config`.
- OpenGate capability probe: `supports_responses_user_input = true`,
  `supports_developer_role = true`, `supports_system_role = true`,
  `supports_native_tool_history = true`, `requires_flattened_input = false`, with no
  probe errors.
- **Responses-native (verified).** A capture confirms OpenGate sent a
  Responses-shaped upstream body (`input` / `instructions` / `tools` / `reasoning` /
  `max_output_tokens`, no `messages`) and received `object: "response"`; OpenGate
  did **not** flatten to `/v1/chat/completions`. This is uncommon for local vLLM
  (Qwen3.6-27B was parked for failing native Responses) and means OpenGate's
  protocol-translation job is a no-op for Ornith — its remaining value is
  command-quality repair and capture/measurement.

## Live Codex App-Build Results

Judged by independent execution of the produced workspace, never the model's
self-report. Suite: `fixtures/codex_live/software_build.json`. Mode: `repair`,
`spoon`, `workspace-write`, GX10.

| Run | Cell | Turns | Cmd exec | CQ (upstream -> returned) | Leaks | App outcome |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `ornith_expense_cli_gx10-repair` (x3) | `expense_cli` | 3/3 | 21 | 19 -> 0 | 0 | shipped (verified totals + `--category`) |
| `ornith_software_build_suite-repair` (x1) | all 3 apps | 3/3 | 36 | 27 -> 0 | 0 | **3/3 shipped** |

Suite verification:

- `expense_cli` — totals + per-category run correctly.
- `incident_log_triage` — level counts, top errors, `--json` valid output,
  `--since` filters (a future-date filter returns zero rows).
- `habit_tracker_web` — a real 4.8 KB single-file app with localStorage, an add
  button + function, complete/streak/delete, and a 7-day grid (not a placeholder).

Speed: `expense_cli` averaged ~88 s/run, roughly 3-4x faster than Qwen3-Coder-Next
on the same cell (MoE ~3B active + DFlash). Channel discipline held across every
run (all command-quality issues repaired, zero returned, zero leaks); the uncensored
fine-tune did not regress tool discipline relative to base Qwen.

## Repair vs Observe (near-passthrough)

Because Ornith is Responses-native, `observe` mode is effectively pass-through:
OpenGate translates nothing, it only declines to repair. This isolates the value
of the command-quality layer. `expense_cli` x3
(`ornith_expense_cli_gx10_observe-observe`):

| Mode | Turns | CQ returned | Invalid returned | Clean rate | Per-run time | Outcome |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `repair` | 3/3 | 0 (of 19) | 0 | high | ~88 s | 3/3 clean ships |
| `observe` | 2/3 | 33 (of 33) | 28 | 0.49 | 77 / 320 / 916 s (1 timeout) | 2/3 ship (messy), 1 fail |

Without repair, 33 command-quality issues and 28 invalid calls reach Codex, half
the captures are dirty, and the model thrashes against its own malformed commands
until one run hits the timeout. The capable model still recovers 2/3 via Codex's
retry loop, but reliability falls from 3/3 and latency variance explodes. So even
for a Responses-native model, OpenGate's command-quality repair earns its keep as a
reliability/latency gate, not a translator.

## Hard-Task Probe (Delaunay Visualizer)

A non-suite stress task through `repair`: a single-file, framework-free web app
that builds a Delaunay triangulation of N random points, animated step by step
(`ornith_delaunay_viz-repair`).

- One turn, 836 s, channel clean (13 command-quality issues repaired -> 0, 0
  leaks), output complete (the 16384 cap held; it did not truncate).
- **Algorithm independently verified correct.** Ornith wrote a real Bowyer-Watson
  triangulator (super-triangle, in-circumcircle determinant, boundary
  re-triangulation, cleanup). Running its actual code in node on n=20/50/100/200
  and checking the empty-circumcircle property with an independent
  circumcenter/radius method found **0 violations across ~97k checks**.
- It included step animation, a stats panel with live Delaunay validity, an inline
  self-check, and click-to-add. It missed two required UI controls (an N-points
  input — hardcoded to 30 — and a speed control).

Failure mode: incompleteness, not incorrectness. The hard, easy-to-fake geometry
was correct; only two trivial UI knobs were skipped.

## Compatibility State

Current state: **known-good for the live `software_build` app gate** and a hard
single-file build, through OpenGate `repair`.

- Zero protocol/parser adaptation was needed (Qwen-family `qwen3_coder` dialect).
- Channel discipline held across every run (all command-quality issues repaired,
  zero returned).
- Responses-native upstream, so OpenGate adds reliability/latency value rather than
  translation.
- Fast: ~3-4x Qwen on the shared cell from the MoE + DFlash.

Caveats: this is the **uncensored** NVFP4 variant; the full-suite and hard-task
runs were single-sample (`Runs 1`); the three repeated runs of a cell shared one
workspace, so the verified artifact is the final run's. A `Runs 3` per-isolated
re-run would firm up the suite numbers.

## Report Files

- expense_cli repair: `runs/codex-live/20260628-213642-ornith_expense_cli_gx10-repair`
- expense_cli observe: `runs/codex-live/20260628-223858-ornith_expense_cli_gx10_observe-observe`
- full suite: `runs/codex-live/20260628-214405-ornith_software_build_suite-repair`
- Delaunay hard task: `runs/codex-live/20260628-231828-ornith_delaunay_viz-repair`

(Run bundles live under the gitignored `runs/`; metrics are summarized in
`docs/benchmark-notes.md`.)
