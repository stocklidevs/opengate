# Data Model: DeepSeek-Coder-V2-Lite Adaptation

## ModelTarget

- `repository`: Hugging Face model repository.
- `served_model_name`: Model name exposed by vLLM and OpenGate.
- `base_url`: Upstream API root.
- `context_length`: Configured maximum model length.
- `tool_parser`: vLLM tool-call parser name.
- `chat_template`: Template path or identifier used for tool prompting.
- `launch_command`: Sanitized serving command.

Validation rules:

- `served_model_name` must match `/v1/models` before benchmark results are interpreted.
- `base_url` must not contain private credentials.

## BenchmarkReport

- `suite`: Benchmark suite path.
- `mode`: `direct`, `observe`, or `repair`.
- `context_policy`: `none`, `full`, or `spoon`.
- `runs`: Number of suite repetitions.
- `output_path`: Report path under `runs/`.
- `strict_successes`: Count and rate.
- `text_leaks`: Count and rate.
- `reasoning_leaks`: Count and rate.
- `argument_leaks`: Count and rate.
- `missed_tool_calls`: Count and rate.
- `invalid_tool_calls`: Count and rate.
- `command_quality_issues`: Count and rate.
- `http_errors`: Count and rate.

Validation rules:

- Direct reports must exist before proxy reports are interpreted as improvements.
- HTTP errors must be kept separate from model leakage metrics.

## Capture

- `path`: Capture file path under an ignored run/capture directory.
- `request_shape`: Native, flattened, or retried upstream request shape.
- `upstream_output_shape`: Structured call, text leak, mixed output, empty output, or error.
- `normalization_summary`: OpenGate normalization report fields.
- `redaction_status`: Confirmation that sensitive headers are redacted.

Validation rules:

- Captures used for fixtures must be sanitized.
- Captures used for repair decisions must include both request and upstream response context.

## RepairCandidate

- `classification`: `protocol`, `parser`, `schema`, `command-quality`, or `behavior`.
- `evidence`: Report row, capture path, or fixture path.
- `expected_repair`: What OpenGate should change, if anything.
- `model_agnostic_shape`: Description of the generalized failure shape.
- `decision`: `repair`, `document`, `defer`, or `reject`.

Validation rules:

- `behavior` candidates cannot become OpenGate task-steering repairs.
- `repair` candidates require model-agnostic shape and evidence.

## CompatibilityNote

- `path`: Public documentation path, expected `docs/deepseek-coder-v2-lite.md`.
- `serving_facts`: ModelTarget summary.
- `reports`: BenchmarkReport list.
- `repair_candidates`: RepairCandidate list.
- `live_status`: Live Codex smoke status.
- `compatibility_status`: `known-good`, `repair-needed`, `synthetic-repaired`, `protocol-blocked`, or `behavior-limited`.

Validation rules:

- Note must include enough command detail to reproduce.
- Note must avoid private credentials and raw sensitive captures.
