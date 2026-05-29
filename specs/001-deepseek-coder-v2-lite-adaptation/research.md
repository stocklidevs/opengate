# Research: DeepSeek-Coder-V2-Lite Adaptation

## Decision: Use The Supplied vLLM Command As The Baseline

**Rationale**: The command specifies the model repository, served name, context length, tool parser, chat template, MoE backend, and interactivity mode. Those are the key variables that affect tool-call compatibility.

**Alternatives considered**:

- Use a simpler vLLM launch without custom template: rejected because the user supplied a specific DeepSeek tool template and parser pair that must be validated together.
- Change context length before baseline: rejected because raw baseline should reflect the proposed serving configuration.

## Decision: Start With Existing Synthetic Suites

**Rationale**: `codex_shell_smoke.json`, `codex_tool_leak_stress.json`, and `qwen_serious_tool_stress.json` already produce comparable metrics across Qwen and GLM. The serious suite name is historical; the cases exercise generic Codex-style tool behavior.

**Alternatives considered**:

- Create a DeepSeek-specific suite first: rejected until raw failures show a missing category.
- Skip smoke and run only serious stress: rejected because smoke isolates basic parser/API shape before adversarial prompts.

## Decision: Compare Observe Before Repair Interpretation

**Rationale**: Observe mode records what OpenGate would normalize while returning upstream output. This separates raw DeepSeek behavior from OpenGate repair behavior and helps identify whether repair mode is hiding important upstream failure shapes.

**Alternatives considered**:

- Run repair only: rejected because it makes repair opportunities harder to explain.
- Run direct only: rejected because the goal includes analyzing what OpenGate has to repair.

## Decision: Classify Failures Before Code Changes

**Rationale**: OpenGate should repair protocol adaptation, parser/text tool syntax, schema mismatch, and command-quality failures. It should not steer task progress, suppress legitimate planning solely because an artifact is pending, or add model-name branches.

**Alternatives considered**:

- Patch every observed failure immediately: rejected because prior Qwen3.6 work showed that task steering crosses OpenGate's boundary.
- Treat HTTP errors as tool-call failures: rejected because protocol incompatibility must be reported separately.

## Decision: Defer Live Codex Until Synthetic Output Is Understood

**Rationale**: Live Codex runs are more expensive to interpret. Synthetic benchmark reports and proxy captures provide a smaller loop for identifying parser and schema failures first.

**Alternatives considered**:

- Start with live software-build runs: rejected because behavior-only drift can obscure transport and parser problems.
