# Model Adaptation Checklist

Use this checklist before declaring a new open coding model compatible with Codex through Open Gate.

## 1. Record Serving Facts

- Model name exposed to Codex.
- Base URL and API path.
- Serving stack and version, such as vLLM, llama.cpp, SGLang, LM Studio, or Ollama.
- Context length and request-body limits.
- Tool-calling flags, parser name, and known parser limitations.
- Exact start command or config file.

## 2. Verify Basic API Shape

- `GET /v1/models` returns the served model name.
- OpenGate launched with `model = "auto"` reports the same detected model in `/health`.
- A simple `/v1/responses` user prompt returns a Responses-shaped object.
- A simple streamed Codex request receives valid Responses SSE events.
- Open Gate captures have redacted sensitive headers.

## 3. Run Raw Baselines

- Synthetic direct benchmark against the model endpoint.
- Leakage-bait benchmark against the model endpoint.
- Serious tool stress benchmark against the model endpoint.
- Record strict success, text leaks, argument leaks, invalid tool calls, missed tool calls, and HTTP errors.

## 4. Run Open Gate Modes

- `observe`: records what Open Gate would fix while returning raw upstream output.
- `repair`: returns normalized output to Codex or benchmark callers.
- Compare returned leaks, invalid tool calls, command-quality issues, and policy blocks.
- Confirm no required fix depends on manually naming the model.

## 5. Run Live Codex Smoke

- Plain text prompt.
- One shell-tool prompt.
- One multi-turn prompt that sends tool output back through Open Gate.
- One no-tool documentation prompt.
- Confirm Codex reaches `turn.completed` without policy blocks.

## 6. Run Heartbeat Stress

- Use a prompt likely to produce a long upstream generation.
- Set `--stream-heartbeat-seconds` low for validation, such as `0.2` or `1`.
- Confirm `stream_heartbeats > 0`, `upstream_errors = 0`, and no Codex timeout. In `0.6.6+`, these heartbeats are Responses lifecycle events, not comment-only keepalives.
- Treat harness timeouts as stress observations, not known-good passes.

## 7. Triage Failures

- vLLM 400 on later turns: check `upstream_input_mode` and flattening.
- `599` socket errors: check sandbox or local-network access.
- Codex policy block: inspect `command_quality_issues`.
- Tool syntax in assistant text: inspect linter leaks and promotion candidates.
- Invalid structured calls: add focused schema repair only if it is model-agnostic.
- Silent streamed request: restart Open Gate and confirm version `0.3.0` or newer.

## 8. Publish Compatibility Notes

Create a model note under `docs\` with:

- Serving command.
- Codex profile or inline config.
- Open Gate command.
- Known-good run folder and report metrics.
- Stress observations.
- Required Open Gate modes or transforms.
- Known non-blocking warnings.

Current model notes:

- `docs\qwen3-coder-next.md` records the first known-good Qwen3-Coder-Next setup.
- `docs\qwen3-6-27b.md` prepares Qwen3.6-27B setup, benchmark commands, and result placeholders.
- `docs\deepseek-coder-v2-lite.md` records DeepSeek-Coder-V2-Lite setup, repaired synthetic/live protocol status, and the parked behavior-limited decision.
- `docs\gemma-4-e4b-it.md` records Gemma-4-E4B-IT setup, repair evidence, and the current live-smoke-clean decision.
- `docs\benchmark-notes.md` contains the cross-model adaptation scorecard.

## 9. Version And Evidence

- Bump the version for behavior changes.
- Update `CHANGELOG.md` and README badges for releases.
- Run `python -m unittest discover -s tests`.
- Run `python -m open_gate.regression --pretty`.
- Tag releases after the known-good evidence is recorded.
