# Implementation Plan: Gemma-4-E4B-IT Adaptation

**Branch**: `002-gemma-4-e4b-it-adaptation` | **Date**: 2026-05-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-gemma-4-e4b-it-adaptation/spec.md`

## Summary

Establish a repeatable compatibility baseline for `Gemma-4-E4B-IT`, compare direct Gemma behavior against OpenGate observe/repair modes, classify failures, and publish the compatibility status. The approach is evidence-first: record serving facts, run direct raw benchmarks, run OpenGate observe/repair comparisons, inspect captures, and only implement repairs for validated protocol, parser, schema, or command-quality failures.

## Technical Context

**Language/Version**: Python 3.11+ project; PowerShell scripts for local Windows benchmark orchestration.

**Primary Dependencies**: OpenGate internal benchmark/proxy/regression modules, vLLM upstream endpoint, Codex CLI for live smoke.

**Storage**: Local files under `runs/`, `captures/`, `fixtures/regressions/`, `docs/`, and this `specs/` directory.

**Testing**: `uv run python -m unittest ...`, `uv run python -m open_gate.regression --pretty`, benchmark report summaries.

**Target Platform**: Windows-first OpenGate workspace talking to a Linux/home-lab vLLM server at `http://127.0.0.1:8001/v1`.

**Project Type**: Python CLI/proxy and benchmark harness.

**Performance Goals**: Benchmarks complete without harness timeouts for normal suites; live streamed requests receive heartbeat events when upstream generation is slow.

**Constraints**: Preserve public-safe docs; do not commit raw captures with secrets; do not add model-specific repair branches; do not add task-progress steering.

**Scale/Scope**: One model adaptation pass for `Gemma-4-E4B-IT`, covering synthetic benchmarks, proxy comparison, failure triage, live smoke readiness, and documentation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Model-Agnostic Repair**: PASS. The plan allows Gemma-specific documentation but only model-agnostic repair code.
- **Evidence Before Behavior Change**: PASS. Direct baselines and captures precede repair decisions.
- **Codex-Compatible Interfaces**: PASS. Repair acceptance is measured by Responses-shaped output and Codex-visible leak/invalid-call metrics.
- **Regression Fixtures From Real Captures**: PASS. Any new repair requires a capture-derived fixture.
- **Public-Safe Configuration**: PASS. Run outputs and captures remain ignored; docs must use sanitized endpoint/setup notes only.

## Project Structure

### Documentation (this feature)

```text
specs/002-gemma-4-e4b-it-adaptation/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- tasks.md
|-- checklists/
|   `-- requirements.md
`-- contracts/
    `-- benchmark-evidence.md
```

### Source Code (repository root)

```text
open_gate/
|-- benchmark.py
|-- proxy.py
|-- command_quality.py
|-- linter.py
|-- regression.py
`-- server.py

tests/
|-- test_benchmark.py
|-- test_command_quality.py
|-- test_linter.py
|-- test_proxy.py
|-- test_regression.py
`-- test_server.py

fixtures/
|-- benchmarks/
|-- codex_live/
`-- regressions/

docs/
|-- benchmark-notes.md
|-- live-codex-benchmark.md
|-- model-adaptation-checklist.md
`-- gemma-4-e4b-it.md

scripts/
|-- run_proxy_benchmark.ps1
`-- run_codex_live_benchmark.ps1
```

**Structure Decision**: Use the existing single Python package and benchmark harness. This feature starts with documentation and evidence; source/test changes are added only if captures prove model-agnostic repair needs.

## Phase 0: Research

Research decisions are captured in [research.md](research.md). Key decisions:

- Use the supplied vLLM command as the serving baseline.
- Treat `gemma4` parser plus the provided chat template as the parser/template pair under validation.
- Run the existing three direct synthetic suites first.
- Compare OpenGate observe and repair before proposing repairs.
- Classify failures into protocol, parser, schema, command-quality, and behavior buckets.

## Phase 1: Design And Contracts

Design artifacts:

- [data-model.md](data-model.md): evidence objects and relationships.
- [contracts/benchmark-evidence.md](contracts/benchmark-evidence.md): minimum evidence expected from each run.
- [quickstart.md](quickstart.md): concrete run order and commands.

### Post-Design Constitution Check

- **Model-Agnostic Repair**: PASS. The repair gate explicitly rejects model-name branching.
- **Evidence Before Behavior Change**: PASS. Report and capture paths are required before repair analysis.
- **Codex-Compatible Interfaces**: PASS. Evidence contract includes returned leaks, invalid calls, command-quality issues, live completion, and upstream schema-error status.
- **Regression Fixtures From Real Captures**: PASS. Tasks require capture-derived fixtures for any repair.
- **Public-Safe Configuration**: PASS. Quickstart keeps run artifacts under ignored paths and documentation under sanitized model notes.

## Implementation Phases

1. Prepare model note and OpenGate local config checks.
2. Run direct baselines and summarize reports.
3. Run OpenGate observe/repair comparisons and inspect captures.
4. Classify repair candidates and decide whether code changes are justified.
5. If justified, create capture-derived fixtures and implement model-agnostic repairs.
6. Rerun synthetic repair benchmarks to verify zero returned leaks and zero invalid calls.
7. Run live Codex smoke only after synthetic evidence is understood, then classify any protocol or behavior blocker separately.

## Complexity Tracking

No constitution violations are planned.
