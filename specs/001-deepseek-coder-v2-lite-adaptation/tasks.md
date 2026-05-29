# Tasks: DeepSeek-Coder-V2-Lite Adaptation

**Input**: Design documents from `specs/001-deepseek-coder-v2-lite-adaptation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/benchmark-evidence.md`, `quickstart.md`

**Tests**: This task list is evidence-first. Code tests are only required if a later task accepts a model-agnostic repair candidate.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare documentation and confirm endpoint identity.

- [X] T001 Create `docs/deepseek-coder-v2-lite.md` with serving facts and the supplied vLLM command.
- [X] T002 Confirm `/v1/models` returns `DeepSeek-Coder-V2-Lite-Instruct`.
- [X] T003 Confirm OpenGate `/health` autodetects `DeepSeek-Coder-V2-Lite-Instruct` with local `model = "auto"`.
- [X] T004 Record vLLM version and any startup warnings relevant to `deepseek_v3`, chat template loading, MoE backend, or context length.

---

## Phase 2: Raw Baselines (P1)

**Goal**: Record direct model behavior before OpenGate repairs.

**Independent Test**: Direct reports exist and summarize required metrics.

- [X] T005 [P] Run direct smoke benchmark and write `runs/deepseek_v2_lite_direct_smoke_r3.json`.
- [X] T006 [P] Run direct leak-stress benchmark and write `runs/deepseek_v2_lite_direct_leak_stress_r3.json`.
- [X] T007 Run direct serious benchmark and write `runs/deepseek_v2_lite_direct_serious_r3.json` or a documented `_r1` partial if timeout occurs.
- [X] T008 Summarize direct reports with `open_gate.summarize_report`.
- [X] T009 Update `docs/deepseek-coder-v2-lite.md` with direct baseline metrics and interpretation.

---

## Phase 3: OpenGate Comparisons (P2)

**Goal**: Measure what OpenGate observes and repairs.

**Independent Test**: Proxy reports exist and capture returned leaks, invalid calls, command-quality issues, and HTTP/protocol behavior.

- [X] T010 Run OpenGate `observe/full` serious benchmark and write `runs/deepseek_v2_lite_open_gate_observe_full_r1.json`.
- [X] T011 Run OpenGate `repair/full` serious benchmark and write `runs/deepseek_v2_lite_open_gate_repair_full_r3.json` or a documented `_r1` partial if timeout occurs.
- [X] T012 Run OpenGate `repair/spoon` serious benchmark and write `runs/deepseek_v2_lite_open_gate_repair_spoon_r1.json`.
- [X] T013 Summarize proxy reports and compare against direct serious results.
- [X] T014 Inspect proxy captures for every failed or repaired case selected for follow-up.

---

## Phase 4: Repair Analysis (P2)

**Goal**: Decide whether OpenGate needs code changes and what evidence supports them.

**Independent Test**: Every selected failure has a classification and decision.

- [X] T015 Classify selected failures as protocol, parser, schema, command-quality, or behavior.
- [X] T016 Reject behavior-only candidates from OpenGate repair scope and document them as limitations.
- [X] T017 For each accepted repair candidate, write a model-agnostic failure shape and expected normalized output.
- [X] T018 For each accepted repair candidate, create or plan a capture-derived regression fixture under `fixtures/regressions/`.
- [X] T019 Decide whether source changes are needed in `open_gate/proxy.py`, `open_gate/linter.py`, `open_gate/command_quality.py`, or related tests.

---

## Phase 5: Accepted Repair Implementation (P1)

**Goal**: Implement the capture-backed parser/schema/actionable-output repairs accepted in Phase 4.

**Independent Test**: Focused unit tests and regression fixtures pass, and repaired synthetic proxy reports show zero returned leaks and zero invalid calls.

- [X] T020 Add failing linter and proxy tests for DeepSeek-v3 delimiter blocks, partial markers, `function.parameters`, no-tool diagnostic suppression, and residual `<tool_call>` tag text.
- [X] T021 Implement DeepSeek/vLLM delimiter extraction and partial marker stripping in `open_gate/linter.py` without model-name branching.
- [X] T022 Treat JSON `function.parameters` as arguments when `function.arguments` is absent.
- [X] T023 Gate actionable-output fallback in `open_gate/proxy.py` so negative-tool-intent prompts do not receive synthesized diagnostic tool calls.
- [X] T024 Add capture-derived regression fixtures under `fixtures/regressions/` for each accepted repair shape.
- [X] T025 Verify focused unit tests, linter/proxy/regression tests, and regression replay.
- [X] T026 Rerun OpenGate `repair/full` and `repair/spoon` synthetic benchmarks after the parser repairs.

---

## Phase 6: Live Smoke And Publication (P3)

**Goal**: Publish compatibility status with evidence.

**Independent Test**: The DeepSeek note contains setup, reports, repair decisions, and live status.

- [X] T027 Run live Codex smoke after synthetic triage and accepted repairs.
- [X] T028 Summarize live Codex captures with `open_gate.codex_report`.
- [X] T029 Update `docs/deepseek-coder-v2-lite.md` with live smoke status and final compatibility state.
- [X] T030 Update `docs/benchmark-notes.md` raw model comparison table with DeepSeek rows.
- [X] T031 Update README model-adaptation references when DeepSeek reaches a useful synthetic-repaired or protocol-blocked milestone.
- [X] T032 Document the protocol-blocked namespace-tool schema result.

---

## Phase 7: Live Namespace Protocol Repair (P1)

**Goal**: Repair the live Codex namespace schema blocker and classify any remaining live smoke failures.

**Independent Test**: A workspace-write live smoke reaches upstream generation without schema errors and returns no Codex-visible leaks, invalid calls, or command-quality issues.

- [X] T033 Add a failing request-diet test proving compacted namespace schemas must preserve nested child tools.
- [X] T034 Preserve nested `tools` recursively when compacting tool schemas for vLLM request size.
- [X] T035 Verify a captured live Codex request still includes nested `mcp__node_repl__` child tools after compaction.
- [X] T036 Rerun live smoke and confirm the namespace HTTP 400 blocker is gone.
- [X] T037 Add a failing command-quality test for direct PowerShell alias executables such as `dir`.
- [X] T038 Repair bare PowerShell aliases through the existing direct-cmdlet wrapper path.
- [X] T039 Rerun workspace-write live smoke and classify the remaining no-tool/documentation preamble as behavior-limited.
- [X] T040 Update DeepSeek, benchmark, README, linter, and Speckit docs with the new status.

---

## Dependencies & Execution Order

- Phase 1 must complete before interpreting benchmark results.
- Phase 2 must complete before OpenGate improvement claims.
- Phase 3 must complete before repair analysis.
- Phase 4 must complete before any code changes.
- Phase 5 should run only after Phase 4 accepts model-agnostic, capture-backed repair candidates.
- Phase 6 should run only after synthetic repair status is understood.
- Phase 7 should run only after the initial live smoke identifies a concrete protocol or command-quality blocker.

## Parallel Opportunities

- T005 and T006 can run in parallel if the vLLM server has enough capacity.
- Report summarization can run independently per completed report.
- Capture inspection can be split by failure class after T015.
- T033 and T037 can be developed independently once the two live failure shapes are captured.
