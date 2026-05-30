# Contract: Benchmark Evidence

This contract defines the minimum evidence required before OpenGate repair work may begin for `Gemma-4-E4B-IT`.

## Required Serving Evidence

- Model repository and served model name.
- vLLM version.
- `/v1/models` response summary.
- OpenGate `/health` summary with autodetected model.
- Full sanitized vLLM serve command.

## Required Direct Reports

Each direct report must include:

- Suite path.
- Run count.
- Strict success count and rate.
- Text leak count and rate.
- Reasoning leak count and rate.
- Missed tool-call count and rate.
- Invalid structured tool-call count and rate.
- Command-quality issue count and rate.
- HTTP and protocol error count and rate.

Required suites:

- `fixtures/benchmarks/codex_shell_smoke.json`
- `fixtures/benchmarks/codex_tool_leak_stress.json`
- `fixtures/benchmarks/qwen_serious_tool_stress.json`

## Required OpenGate Reports

- At least one `observe/full` serious report.
- At least one `repair/full` serious report.
- At least one `repair/spoon` serious report when long context or live Codex compatibility matters.

Each OpenGate report must include returned leak, invalid-call, command-quality, and protocol metrics.

## Required Repair Candidate Evidence

For every accepted repair candidate:

- Failure classification.
- Report path and case id.
- Capture path when available.
- Generalized repair shape: why the fix is not Gemma-name-specific.
- Expected normalized output.
- Regression fixture plan or file path.

## Compatibility Status Values

- `known-good`: repair mode meets acceptance gates and live smoke reaches meaningful model generation without upstream schema errors, Codex-visible leaks, invalid calls, command-quality issues, or policy blocks.
- `repair-needed`: a model-agnostic repair candidate is accepted but not implemented.
- `synthetic-repaired`: accepted synthetic repair candidates are implemented and verified, but live Codex is not yet known-good.
- `protocol-blocked`: endpoint rejects required request shapes before meaningful model generation.
- `behavior-limited`: remaining failures are wrong-tool choice, planning loops, stalls, no-tool answer artifacts, or task-progress drift.
