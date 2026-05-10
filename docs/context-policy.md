# Context Policy

Open Gate `0.5.0` adds a context compiler for Codex traffic sent to open local models.

## Why

Codex can accumulate very large Responses histories during real coding work: assistant messages, tool calls, tool outputs, retries, screenshots, errors, and final answers. Frontier-hosted models usually tolerate that shape better. Local OpenAI-compatible servers can struggle in three different ways:

- native Responses item types may not be accepted by the upstream server;
- very large flattened histories slow each turn down;
- old failures can stay in context and cause the model to repeat the same bad tool route.

`--context-policy spoon` treats the Codex history as agent state, not plain chat text. It keeps the newest items exact, summarizes older items, and carries forward compact constraints from prior failures.

## Modes

| Mode | Behavior |
| --- | --- |
| `full` | Existing behavior. When flattening is needed, send the complete flattened transcript upstream. |
| `spoon` | Force list-shaped Responses input through a budgeted compiler. Older items are summarized, recent items stay exact, and failure constraints are injected. |

The default is still `full` so benchmarks remain comparable. Use `spoon` for long interactive Codex runs against vLLM or other local open-model servers.

## Run

```powershell
python -m open_gate `
  --host 127.0.0.1 `
  --port 8765 `
  --model Qwen3-Coder-Next `
  --upstream http://127.0.0.1:8001/v1 `
  --normalization-mode repair `
  --upstream-input-mode auto `
  --context-policy spoon `
  --context-max-chars 60000 `
  --context-recent-items 10 `
  --stream-heartbeat-seconds 5
```

The helper script exposes the same knobs:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\start_proxy.ps1 `
  -ContextPolicy spoon `
  -ContextMaxChars 60000 `
  -ContextRecentItems 10
```

## What The Model Sees

In `spoon` mode, Open Gate prepends a short digest:

- how many input items were summarized and how many recent items stayed exact;
- the original flattened size and the active character budget;
- available tool names;
- durable user constraints such as `Everything must be contained in index.html`;
- tool-use guardrails for exact schemas, smaller commands, and avoiding repeated failed routes;
- constraints inferred from earlier tool failures.

Examples of inferred constraints:

- `write_file` was unsupported, so use the advertised tools only;
- `apply_patch` is not available unless it appears in the advertised tool names;
- full HTML should be written to `index.html`, not echoed to stdout;
- Bash heredoc syntax such as `cat > file << EOF` is not valid in Windows PowerShell; Open Gate can repair simple cases into a PowerShell here-string plus `Set-Content`;
- Windows PowerShell rejected `&&`, so use `workdir`, `;`, or separate calls;
- `uv run playwright` failed to spawn, so do not retry the same executable blindly;
- shell-based web fetch hit `WinError 10013`, so continue from available context or choose a different route.

## Capture Fields

Proxy captures include these fields under `upstream.transform`:

| Field | Meaning |
| --- | --- |
| `context_policy` | `full` or `spoon`. |
| `original_flattened_chars` | Size of the complete flattened transcript before budget handling. |
| `flattened_chars` | Size sent upstream after compilation. |
| `summarized_input_items` | Number of older Responses input items summarized. |
| `exact_recent_items` | Number of newest input items kept exact. |
| `dropped_context_chars` | Difference between original and sent size. |
| `context_constraints` | Compact constraints inferred from earlier failures. |

`python -m open_gate.codex_report ... --summary-only` reports aggregate context metrics such as `spoon_context_requests`, `max_flattened_chars`, `max_original_flattened_chars`, and `dropped_context_chars`.

Large recent tool outputs are summarized even when the surrounding recent turn is kept exact. This prevents accidental stdout dumps, such as an entire HTML document printed by `echo`, from dominating the next model turn.

## Validation Target

For local Qwen3-Coder-Next, the current stress target is:

- finish the interactive Codex webpage prompt in under 7 minutes;
- return no leaked tool calls;
- return no invalid tool calls;
- return no command-quality issues;
- avoid repeated 120-second upstream timeout turns.

This is intentionally stricter than “the model eventually made a file.” The goal is to make local open models feel viable inside Codex, not just technically connected.
