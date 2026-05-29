# Contract: Benchmark And Repair Evidence

This contract defines the minimum evidence required before OpenGate repair work may begin for `DeepSeek-Coder-V2-Lite-Instruct`.

## Required Report Set

| Stage | Required Runs | Required Output |
| --- | ---: | --- |
| Direct smoke | 3 | `runs/deepseek_v2_lite_direct_smoke_r3.json` |
| Direct leak stress | 3 | `runs/deepseek_v2_lite_direct_leak_stress_r3.json` |
| Direct serious | 3 preferred, 1 minimum | `runs/deepseek_v2_lite_direct_serious_r3.json` or `_r1.json` |
| OpenGate observe/full | 1 minimum | `runs/deepseek_v2_lite_open_gate_observe_full_r1.json` |
| OpenGate repair/full | 3 preferred, 1 minimum | `runs/deepseek_v2_lite_open_gate_repair_full_r3.json` or `_r1.json` |
| OpenGate repair/spoon | 1 minimum | `runs/deepseek_v2_lite_open_gate_repair_spoon_r1.json` |

## Required Metrics

Each report summary must include:

- Strict success count and rate.
- Failure count and rate.
- Text leak count and rate.
- Reasoning leak count and rate.
- Argument leak count and rate.
- Missed tool-call count and rate.
- Invalid structured tool-call count and rate.
- Command-quality issue count and rate.
- HTTP error count and rate.
- Protocol incompatibility count and type, when present.

## Repair Candidate Admission

A repair candidate is admissible only when all fields are present:

- Failure classification: protocol, parser, schema, command-quality, or behavior.
- Evidence reference: report case ID, capture path, or fixture path.
- Upstream shape: concise description of what the model or vLLM returned.
- Codex-visible impact: what Codex would see without repair.
- Generalized repair shape: why the fix is not DeepSeek-name-specific.
- Decision: repair, document, defer, or reject.

## Compatibility Status

- `known-good`: repair mode meets acceptance gates and live smoke reaches meaningful model generation without upstream schema errors, Codex-visible leaks, invalid calls, or policy blocks.
- `repair-needed`: a model-agnostic repair candidate is accepted but not implemented.
- `synthetic-repaired`: accepted synthetic repair candidates are implemented and verified, but live Codex is not yet known-good.
- `protocol-blocked`: endpoint rejects required request shapes before meaningful model generation.
- `behavior-limited`: remaining failures are wrong-tool choice, planning loops, stalls, or task-progress drift.
