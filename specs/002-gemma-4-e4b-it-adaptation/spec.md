# Feature Specification: Gemma-4-E4B-IT Adaptation

**Feature Branch**: `002-gemma-4-e4b-it-adaptation`

**Created**: 2026-05-29

**Status**: Implemented; live smoke is clean, larger software-build gate is not passed

**Input**: User description: "Establish baseline and analyze what has to be repaired for `google/gemma-4-E4B-it` served as `Gemma-4-E4B-IT` through vLLM with the `gemma4` tool parser and Gemma 4 tool chat template."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Establish Raw Gemma Baselines (Priority: P1)

As an OpenGate maintainer, I need recorded raw benchmark results for the Gemma-4-E4B-IT endpoint before any OpenGate repair claims are made.

**Why this priority**: Raw baselines are the control group for every repair decision and prevent confusing model behavior with proxy behavior.

**Independent Test**: Can be tested by running the direct benchmark suite set against the vLLM endpoint and confirming reports exist with strict success, leak, invalid-call, missed-call, command-quality, and HTTP-error metrics.

**Acceptance Scenarios**:

1. **Given** the Gemma endpoint is serving the requested model, **When** the direct smoke benchmark runs, **Then** a report records basic tool-call compatibility metrics.
2. **Given** the direct smoke report exists, **When** leak-stress and serious-tool-stress benchmarks run, **Then** reports capture leakage, schema, missed-tool, over-eager, and transport behavior.
3. **Given** any direct benchmark returns HTTP or validation errors, **When** the report is summarized, **Then** errors are classified separately from model tool-call behavior.

---

### User Story 2 - Compare OpenGate Observe And Repair (Priority: P2)

As an OpenGate maintainer, I need observe and repair runs that show what OpenGate would fix and what Codex would actually receive.

**Why this priority**: The comparison separates upstream Gemma behavior from OpenGate behavior and avoids adding repairs for failures that are only model behavior.

**Independent Test**: Can be tested by running OpenGate proxy benchmarks in observe and repair modes and comparing returned leaks, invalid calls, command-quality issues, protocol adaptation, and captured normalization reports.

**Acceptance Scenarios**:

1. **Given** raw baselines are recorded, **When** OpenGate runs in observe mode, **Then** captures show normalization opportunities while raw upstream output is preserved.
2. **Given** observe mode identifies repairable failures, **When** repair mode runs, **Then** returned output is Responses-shaped and contains no Codex-visible tool syntax leaks.
3. **Given** a failure remains after repair, **When** it is reviewed, **Then** it is classified before any code change is proposed.

---

### User Story 3 - Publish Gemma Compatibility Status (Priority: P3)

As an OpenGate maintainer, I need a public-friendly model note that explains the Gemma setup, baseline scores, repair requirements, and any limitations.

**Why this priority**: Public compatibility notes let future runs reproduce the result and clarify whether failures belong to OpenGate or to model/task behavior.

**Independent Test**: Can be tested by reviewing the model note and confirming it includes serving facts, report paths, run metrics, capture-derived repair candidates, acceptance status, and next actions.

**Acceptance Scenarios**:

1. **Given** benchmark and repair runs are complete, **When** the model note is updated, **Then** it records the serving command and report paths without private credentials.
2. **Given** repair candidates are found, **When** they are documented, **Then** each candidate is tied to a capture or report row and classified as protocol, parser, schema, command-quality, or behavior.
3. **Given** a failure is behavior-only, **When** compatibility status is published, **Then** it is documented as a limitation without adding task-steering repair logic.

---

### Edge Cases

- The vLLM endpoint may reject Codex-style roles, native tool history, MCP namespace tools, or tool output items before generation.
- The Gemma parser may emit structured tool calls, text tool syntax, both, or neither depending on suite category.
- The Gemma 4 chat template may support tool calls for chat completions but produce different Responses-shaped behavior through vLLM.
- Long generations may trigger harness or socket timeouts despite heartbeat events.
- A failed direct baseline may be a protocol incompatibility rather than evidence that the model cannot call tools.
- Some failures may be behavior-only, such as wrong tool choice, planning loops, no-tool preamble text, or task-progress drift; these must not become OpenGate task steering.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The adaptation MUST record the exact Gemma serving facts: model repository, served model name, endpoint, context length, vLLM flags, parser, chat template, and performance mode.
- **FR-002**: The adaptation MUST verify endpoint identity through `/v1/models` and OpenGate `/health` before benchmark interpretation.
- **FR-003**: The adaptation MUST run direct raw baselines for the smoke, leak-stress, and serious tool-stress benchmark suites before OpenGate repair claims.
- **FR-004**: The adaptation MUST run OpenGate observe and repair comparisons, including full context and spoon context where relevant.
- **FR-005**: The adaptation MUST summarize each report with strict successes, text leaks, reasoning leaks, argument leaks, missed tool calls, invalid tool calls, command-quality issues, and HTTP errors.
- **FR-006**: The adaptation MUST classify failures as protocol, parser, schema, command-quality, or behavior before proposing code changes.
- **FR-007**: Any new repair MUST be model-agnostic and backed by a real capture or benchmark failure shape.
- **FR-008**: Behavior-only failures MUST be documented as limitations or prompt/model observations, not fixed through artifact pressure or task-steering logic.
- **FR-009**: The adaptation MUST produce a public-friendly Gemma model note with setup, commands, report paths, score tables, repair candidates, and compatibility status.
- **FR-010**: The adaptation MUST define and run a live Codex smoke gate before the model is marked known-good.
- **FR-011**: If live Codex smoke completes only by returning upstream schema errors, the adaptation MUST classify that separately from a known-good live pass.
- **FR-012**: If a larger live software-build gate is run, the adaptation MUST record task completion, upstream errors, command executions, generated artifacts, and whether the result changes the compatibility status.

### Key Entities *(include if feature involves data)*

- **Model Target**: The served Gemma model configuration, including repository, served name, endpoint, context window, parser, template, and launch flags.
- **Benchmark Report**: A direct or proxied suite run with metrics, suite name, mode, context policy, output path, and pass/fail interpretation.
- **Capture**: A redacted OpenGate request/response artifact used to reproduce and inspect an upstream or normalized failure shape.
- **Repair Candidate**: A classified failure shape that may justify OpenGate changes if it is model-agnostic and capture-backed.
- **Compatibility Note**: The public documentation artifact that records setup, evidence, analysis, and current status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Direct raw reports exist for all three benchmark suites, with every requested metric present.
- **SC-002**: OpenGate observe and repair reports exist for the serious suite with at least one full-context comparison and one spoon-context comparison.
- **SC-003**: Every failed case selected for follow-up has a documented failure classification and evidence reference.
- **SC-004**: No OpenGate code repair is proposed without a model-agnostic failure statement and a capture or benchmark reference.
- **SC-005**: The Gemma model note contains enough setup detail for another maintainer to reproduce the endpoint and benchmark sequence.
- **SC-006**: The final compatibility status distinguishes known-good, smoke-clean, repair-needed, synthetic-repaired, protocol-blocked, and behavior-limited outcomes.

## Assumptions

- The vLLM endpoint will be reachable at `http://127.0.0.1:8001/v1` when benchmark execution begins.
- OpenGate will use `model = "auto"` for local config so the served model name can be detected from `/v1/models`.
- Existing benchmark suites are sufficient for the first compatibility pass, even though `qwen_serious_tool_stress.json` has a Qwen-oriented name.
- The initial work is planning and evidence collection; production repair changes happen only after baseline results identify a repeatable model-agnostic failure.
