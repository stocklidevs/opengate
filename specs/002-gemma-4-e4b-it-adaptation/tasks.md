# Tasks: Gemma-4-E4B-IT Adaptation

**Input**: Design documents from `specs/002-gemma-4-e4b-it-adaptation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/benchmark-evidence.md`, `quickstart.md`

**Tests**: This task list is evidence-first. Code tests are only required if a later task accepts a model-agnostic repair candidate.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare documentation and confirm endpoint identity.

- [X] T001 Create `docs/gemma-4-e4b-it.md` with serving facts and the supplied vLLM command.
- [X] T002 Confirm `/v1/models` returns `Gemma-4-E4B-IT`.
- [X] T003 Confirm OpenGate `/health` autodetects `Gemma-4-E4B-IT` with local `model = "auto"`.
- [X] T004 Record vLLM version and any startup warnings relevant to `gemma4`, chat template loading, or context length in `docs/gemma-4-e4b-it.md`.

---

## Phase 2: Raw Baselines (P1)

**Goal**: Record direct model behavior before OpenGate repairs.

**Independent Test**: Direct reports exist and summarize required metrics.

- [X] T005 [P] [US1] Run direct smoke benchmark and write `runs/gemma4_e4b_it_direct_smoke_r3.json`.
- [X] T006 [P] [US1] Run direct leak-stress benchmark and write `runs/gemma4_e4b_it_direct_leak_stress_r3.json`.
- [X] T007 [US1] Run direct serious benchmark and write `runs/gemma4_e4b_it_direct_serious_r3.json` or a documented `_r1` partial if timeout occurs.
- [X] T008 [US1] Summarize direct reports with `open_gate.summarize_report`.
- [X] T009 [US1] Update `docs/gemma-4-e4b-it.md` with direct baseline metrics and interpretation.

---

## Phase 3: OpenGate Comparisons (P2)

**Goal**: Measure what OpenGate observes and repairs.

**Independent Test**: Proxy reports exist and capture returned leaks, invalid calls, command-quality issues, and HTTP/protocol behavior.

- [X] T010 [P] [US2] Run OpenGate `observe/full` serious benchmark and write `runs/gemma4_e4b_it_open_gate_observe_full_r1.json`.
- [X] T011 [US2] Run OpenGate `repair/full` serious benchmark and write `runs/gemma4_e4b_it_open_gate_repair_full_r3.json` or a documented `_r1` partial if timeout occurs.
- [X] T012 [US2] Run OpenGate `repair/spoon` serious benchmark and write `runs/gemma4_e4b_it_open_gate_repair_spoon_r1.json`.
- [X] T013 [US2] Summarize proxy reports and compare against direct serious results.
- [X] T014 [US2] Inspect proxy captures for every failed or repaired case selected for follow-up.

---

## Phase 4: Repair Analysis (P2)

**Goal**: Decide whether OpenGate needs code changes and what evidence supports them.

**Independent Test**: Every selected failure has a classification and decision.

- [X] T015 [US2] Classify selected failures as protocol, parser, schema, command-quality, or behavior in `docs/gemma-4-e4b-it.md`.
- [X] T016 [US2] Reject behavior-only candidates from OpenGate repair scope and document them as limitations.
- [X] T017 [US2] For each accepted repair candidate, write a model-agnostic failure shape and expected normalized output.
- [X] T018 [US2] For each accepted repair candidate, create or plan a capture-derived regression fixture under `fixtures/regressions/`.
- [X] T019 [US2] Decide whether source changes are needed in `open_gate/proxy.py`, `open_gate/linter.py`, `open_gate/command_quality.py`, or related tests.

---

## Phase 5: Conditional Repair Implementation (P1 If Needed)

**Goal**: Implement only capture-backed parser/schema/protocol/command-quality repairs accepted in Phase 4.

**Independent Test**: Focused unit tests and regression fixtures pass, and repaired synthetic proxy reports show zero returned leaks and zero invalid calls.

- [X] T020 [US2] Add failing focused tests for each accepted Gemma failure shape in `tests/test_linter.py`, `tests/test_proxy.py`, or `tests/test_command_quality.py`.
- [X] T021 [US2] Implement accepted model-agnostic repairs in the relevant `open_gate/` modules.
- [X] T022 [US2] Add capture-derived regression fixtures under `fixtures/regressions/` for each accepted repair shape.
- [X] T023 [US2] Verify focused unit tests, linter/proxy/regression tests, and regression replay.
- [X] T024 [US2] Rerun OpenGate `repair/full` and `repair/spoon` synthetic benchmarks after any repair changes.

---

## Phase 6: Live Smoke And Publication (P3)

**Goal**: Publish compatibility status with evidence.

**Independent Test**: The Gemma note contains setup, reports, repair decisions, live status, and final compatibility state.

- [X] T025 [US3] Run live Codex smoke after synthetic triage and accepted repairs.
- [X] T026 [US3] Summarize live Codex captures with `open_gate.codex_report`.
- [X] T027 [US3] Update `docs/gemma-4-e4b-it.md` with live smoke status and final compatibility state.
- [X] T028 [US3] Update `docs/benchmark-notes.md` raw model comparison and model adaptation scorecard with Gemma rows.
- [X] T029 [US3] Update README model-adaptation references when Gemma reaches a useful repaired, protocol-blocked, behavior-limited, or known-good milestone.
- [X] T030 [US3] Record final decision: known-good, repair-needed, synthetic-repaired, protocol-blocked, or behavior-limited.

---

## Phase 7: Larger Live Software-Build Probe (Follow-Up)

**Goal**: Check whether the smoke-clean Gemma path holds under a write-heavy Codex build workload.

**Independent Test**: The software-build run is summarized with command executions, generated artifacts, upstream errors, and updated compatibility status.

- [X] T031 Run `fixtures/codex_live/software_build.json` against Gemma through OpenGate `repair/spoon`.
- [X] T032 Classify the raw Gemma pipe-style unavailable skill-call shape as parser/output-format and add a regression fixture.
- [X] T033 Classify Codex transcript-style `assistant tool call ...` text as parser/output-format and add a regression fixture.
- [X] T034 Implement model-agnostic parser repairs for accepted pipe/transcript shapes and verify focused tests.
- [X] T035 Rerun the software-build load after repairs and record the result as smoke-clean only, not broadly known-good, because the larger run hit upstream errors/timeouts and produced no artifacts.

---

## Dependencies & Execution Order

- Phase 1 must complete before interpreting benchmark results.
- Phase 2 must complete before OpenGate improvement claims.
- Phase 3 must complete before repair analysis.
- Phase 4 must complete before any code changes.
- Phase 5 runs only if Phase 4 accepts model-agnostic, capture-backed repair candidates.
- Phase 6 runs after synthetic repair status is understood.
- Phase 7 is a post-smoke confidence gate and may downgrade a smoke-clean decision if larger live workloads fail.

## Parallel Opportunities

- T005 and T006 can run in parallel if the vLLM server has enough capacity.
- T010 can run independently after direct serious baseline exists.
- Report summarization can run independently per completed report.
- Capture inspection can be split by failure class after T015.
- Conditional tests and fixtures in T020 and T022 can be developed in parallel once accepted failure shapes are identified.

## Implementation Strategy

1. MVP: Complete Phase 1 and Phase 2 to establish whether Gemma has a usable raw baseline.
2. Increment 2: Complete Phase 3 and Phase 4 to decide whether OpenGate repair is needed.
3. Increment 3: Complete Phase 5 only for real proxy-layer failures.
4. Increment 4: Complete Phase 6 to publish live status and update the cross-model scorecard.
