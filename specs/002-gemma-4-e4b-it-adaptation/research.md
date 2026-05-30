# Research: Gemma-4-E4B-IT Adaptation

## Decision: Use The Supplied vLLM Command As The Baseline

**Rationale**: The command specifies the model repository, served name, context length, tool parser, chat template, GPU memory target, and interactivity mode. Those are the key variables that affect tool-call compatibility.

**Alternatives considered**:

- Change parser/template before baseline: rejected because the user supplied the exact `gemma4` parser and template pair that must be validated first.
- Increase context length before baseline: rejected because the first pass should reflect the proposed serving configuration.

## Decision: Use Existing Benchmark Suites First

**Rationale**: `codex_shell_smoke.json`, `codex_tool_leak_stress.json`, and `qwen_serious_tool_stress.json` already produce comparable metrics across Qwen, GLM, Qwen3.6, DeepSeek, and now Gemma. The serious suite name is historical; the cases exercise generic Codex-style tool behavior.

**Alternatives considered**:

- Create a Gemma-specific suite first: rejected until raw failures show a missing category.
- Skip direct baselines and start through OpenGate: rejected because repair claims need a raw control group.

## Decision: Compare Observe And Repair Before Editing Code

**Rationale**: Observe mode records what OpenGate would normalize while returning upstream output. This separates raw Gemma behavior from OpenGate repair behavior and helps identify whether repair mode is hiding important upstream failure shapes.

**Alternatives considered**:

- Patch every observed failure immediately: rejected because Qwen3.6 and DeepSeek showed that some failures are behavior-only and should not become proxy repair logic.
- Treat HTTP errors as tool-call failures: rejected because protocol incompatibility must be reported separately.

## Decision: Keep Repair Scope Model-Agnostic

**Rationale**: OpenGate should adapt protocol, parse generic recoverable tool syntax, repair schemas, and quarantine command-quality failures. It should not contain Gemma-name branches or task-progress steering.

**Alternatives considered**:

- Add Gemma-specific behavior cleanup rules: rejected unless a later capture proves a general parser/schema/command-quality shape.
- Tune model behavior through OpenGate: rejected for this adaptation pass; behavior-only issues are documented and may park the model.
