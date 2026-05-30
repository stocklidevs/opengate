# Data Model: Gemma-4-E4B-IT Adaptation

## ModelTarget

- `repository`: Hugging Face model repository, expected `google/gemma-4-E4B-it`.
- `served_model_name`: vLLM served model name, expected `Gemma-4-E4B-IT`.
- `endpoint`: OpenAI-compatible base URL, expected `http://127.0.0.1:8001/v1`.
- `max_model_len`: Context length configured at serve time, expected `16384`.
- `tool_parser`: vLLM tool-call parser name, expected `gemma4`.
- `chat_template`: Template path used by vLLM, expected `$HOME/vllm-templates/tool_chat_template_gemma4.jinja`.
- `performance_mode`: vLLM performance mode, expected `interactivity`.

Validation rules:

- `served_model_name` must match `/v1/models` before benchmark results are interpreted.
- Serving facts must be recorded in `docs/gemma-4-e4b-it.md`.

## BenchmarkReport

- `path`: Local report path under `runs/`.
- `suite`: Benchmark suite path.
- `mode`: `direct`, `observe`, or `repair`.
- `context_policy`: `full`, `spoon`, or not applicable.
- `runs`: Number of benchmark repetitions.
- `strict_successes`: Count and rate.
- `text_leaks`: Count and rate.
- `reasoning_leaks`: Count and rate.
- `argument_leaks`: Count and rate.
- `missed_tool_calls`: Count and rate.
- `invalid_tool_calls`: Count and rate.
- `command_quality_issues`: Count and rate.
- `http_errors`: Count and rate.
- `protocol_incompatibilities`: Structured protocol error classifications when present.

Validation rules:

- Direct reports must exist before OpenGate repair claims.
- Observe reports may contain returned leaks; repair reports should drive returned leaks and invalid calls toward zero.

## Capture

- `path`: Local capture path under a run capture directory.
- `case_id`: Benchmark or live smoke case.
- `upstream_status`: HTTP status or transport error.
- `normalization_summary`: OpenGate normalization telemetry.
- `failure_shape`: Parser, schema, protocol, command-quality, or behavior evidence.

Validation rules:

- Any accepted repair candidate must cite at least one capture or benchmark row.
- Raw captures must remain ignored if they contain sensitive request context.

## RepairCandidate

- `classification`: `protocol`, `parser`, `schema`, `command-quality`, or `behavior`.
- `evidence`: Report path, capture path, and relevant case id.
- `generalized_shape`: Model-agnostic description of the failure.
- `expected_normalization`: What OpenGate should return after repair.
- `decision`: `implement`, `document-only`, or `reject`.

Validation rules:

- `behavior` candidates cannot become OpenGate task-steering repairs.
- `implement` candidates require a model-agnostic shape and evidence.

## CompatibilityNote

- `path`: Public documentation path, expected `docs/gemma-4-e4b-it.md`.
- `serving_facts`: ModelTarget summary.
- `reports`: BenchmarkReport list.
- `repair_candidates`: RepairCandidate list.
- `live_status`: Live Codex smoke status.
- `compatibility_status`: `known-good`, `repair-needed`, `synthetic-repaired`, `protocol-blocked`, or `behavior-limited`.

Validation rules:

- Note must include enough command detail to reproduce.
- Note must avoid private credentials and raw sensitive captures.
