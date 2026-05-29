<!--
Sync Impact Report
Version change: template -> 1.0.0
Modified principles:
- template principle 1 -> Model-Agnostic Repair
- template principle 2 -> Evidence Before Behavior Change
- template principle 3 -> Codex-Compatible Interfaces
- template principle 4 -> Regression Fixtures From Real Captures
- template principle 5 -> Public-Safe Configuration
Added sections:
- Model Adaptation Workflow
- Quality Gates
Removed sections:
- Placeholder template text
Templates requiring updates:
- .specify/templates/spec-template.md: checked, no change required
- .specify/templates/plan-template.md: checked, no change required
- .specify/templates/tasks-template.md: checked, no change required
Follow-up TODOs: none
-->
# OpenGate Constitution

## Core Principles

### I. Model-Agnostic Repair

OpenGate MUST repair transport, protocol, tool-call, schema, and command-quality
failures in ways that do not depend on hard-coding a specific model name. Model
notes may describe model-specific observations, but production repair logic MUST
generalize from a captured failure shape.

### II. Evidence Before Behavior Change

Every behavior change MUST be backed by direct evidence: a benchmark report,
captured upstream response, live Codex report, or regression fixture. Raw model
baselines MUST be recorded before OpenGate repair claims are made, and failures
MUST be classified before code is changed.

### III. Codex-Compatible Interfaces

OpenGate MUST preserve Codex-facing Responses API compatibility. Repair mode
MUST return valid Responses-shaped output, avoid assistant-text tool leaks, and
avoid returning structured calls that Codex policy or schema validation will
reject. Streamed requests MUST receive valid Responses lifecycle events while
OpenGate waits for slower local backends.

### IV. Regression Fixtures From Real Captures

New repairs MUST include focused regression coverage derived from real captures
whenever practical. Fixtures MUST assert the externally visible behavior:
remaining text leaks, invalid tool calls, command-quality issues, and normalized
tool-call output. Synthetic tests may cover smaller parser or helper behavior,
but they do not replace capture-based evidence for a new failure family.

### V. Public-Safe Configuration

The repository MUST stay public friendly. Machine-specific endpoints, API keys,
captures, logs, and run outputs belong in ignored local files or sanitized docs.
Committed examples MUST be safe to share and MUST avoid private credentials,
absolute local secrets, or non-redacted request headers.

## Model Adaptation Workflow

Each new model adaptation MUST follow this order:

1. Record serving facts, including model name, endpoint, context length, parser,
   chat template, and exact launch command.
2. Verify endpoint identity and OpenGate health metadata.
3. Run direct raw baselines before proxy repair comparisons.
4. Run OpenGate observe and repair comparisons.
5. Classify failures as protocol, parser, schema, command-quality, or behavior.
6. Add model-agnostic repairs only for validated protocol, parser, schema, or
   command-quality failures.
7. Document behavior-only limitations without adding task-steering logic.

## Quality Gates

Plans MUST state the verification commands that prove the work. For model
adaptation work, the minimum gates are direct benchmark reports, OpenGate repair
reports, regression replay, focused unit tests for any changed code, and a live
Codex smoke before compatibility is called known-good.

## Governance

This constitution governs Spec Kit plans, tasks, and implementation reviews for
OpenGate. Amendments require a documented rationale, an updated version line,
and a Sync Impact Report explaining affected principles and templates.

Versioning follows semantic versioning:

- MAJOR for principle removals or incompatible governance changes.
- MINOR for new principles or materially expanded requirements.
- PATCH for wording clarifications that do not change requirements.

Every implementation plan MUST include a Constitution Check. Any violation MUST
be justified in the plan before implementation begins.

**Version**: 1.0.0 | **Ratified**: 2026-05-28 | **Last Amended**: 2026-05-28
