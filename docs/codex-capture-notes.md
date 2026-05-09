# Codex Capture Notes

Captured on 2026-05-09 with:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Users\example\source\repos\open-gate\scripts\run_codex_capture_probe.ps1
```

Observed request shape:

- Codex calls `POST /v1/responses`.
- The request uses `stream: true`.
- The request body includes `model`, `input`, `tools`, `tool_choice`, `parallel_tool_calls`, `reasoning`, `text`, and `store`.
- For a simple prompt, `input` contained three messages: one `developer`, then two `user` messages.
- Tool choice was `"auto"`.
- The first captured tool name was `shell`, not `shell_command`.
- Codex sent ten tools in this environment: `shell`, `update_plan`, `request_user_input`, `web_search`, `view_image`, `spawn_agent`, `send_input`, `resume_agent`, `wait_agent`, and `close_agent`.

Implications for the proxy:

- The compatibility layer should target Responses streaming first.
- The parser should validate against Codex's actual `tools` array captured per request, because names and schemas differ from this ChatGPT session's tool names.
- The linter should handle built-in tools such as `web_search` that do not have a function-style `name`.
- A pass-through proxy should preserve Codex's input and tool schema exactly, then normalize only the backend model output.
