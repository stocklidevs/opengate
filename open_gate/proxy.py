from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .command_quality import (
    EMPTY_ARTIFACT_WRITE_DIAGNOSTIC,
    inspect_tool_calls,
    parse_shell_array_string,
    repair_shell_arguments,
)
from .linter import ToolCall, analyze_text, load_tool_specs


JsonObject = dict[str, Any]
NEGATIVE_TOOL_INTENT = (
    "without using tools",
    "without using any tools",
    "do not use tools",
    "don't use tools",
    "do not call",
    "don't call",
    "not execution",
    "not execute",
    "only documentation",
    "documentation, not execution",
)
CONTEXT_POLICIES = {"full", "spoon"}
INSTRUCTION_POLICIES = {"full", "auto", "digest"}
TOOL_SCHEMA_POLICIES = {"full", "auto", "compact"}
DEFAULT_CONTEXT_MAX_CHARS = 60000
DEFAULT_CONTEXT_RECENT_ITEMS = 10
DEFAULT_INSTRUCTION_DIGEST_THRESHOLD = 12000
DEFAULT_TOOL_SCHEMA_COMPACT_THRESHOLD = 16000
CONTEXT_OUTPUT_PREVIEW_CHARS = 900
CONTEXT_SUMMARY_PREVIEW_CHARS = 500
CONTEXT_RECENT_TOOL_OUTPUT_MAX_CHARS = 1600
TOOL_DESCRIPTION_MAX_CHARS = 220
SCHEMA_DESCRIPTION_MAX_CHARS = 120
IMPORTANT_OUTPUT_RE = re.compile(
    r"(error|failed|exception|traceback|timed out|timeout|not recognized|unsupported call|winerror|permission denied|"
    r"no such file|cannot find|failed to spawn)",
    re.IGNORECASE,
)
COMMAND_ISSUE_HINTS = {
    "windows_powershell_chain_operator": "Windows PowerShell does not accept &&; use ';', separate tool calls, or the workdir field.",
    "powershell_here_string_header": "PowerShell here-string headers need a real newline immediately after @' or @\".",
    "python_compound_statement_one_liner": "For multi-line Python, pipe a here-string to python - instead of packing def/async def/class after semicolons.",
    "uv_run_playwright_entrypoint": "Do not assume uv run playwright exists; verify tooling or use python -m playwright only when installed.",
    "relative_cd_without_workdir": "Use the shell tool workdir argument instead of inline relative cd commands.",
    "nested_relative_cd": "Do not cd into the same relative directory already selected as shell workdir.",
    "view_image_non_image_path": "view_image expects an image file path, not a directory or project root.",
    "skill_file_as_mcp_resource": "Codex skills are local instruction files, not MCP resources.",
    "html_echo_without_file_write": "Do not print a full HTML document to stdout; write the content to index.html.",
    "empty_artifact_write": "Do not create or truncate an empty target artifact; write the complete requested file content in one valid tool call.",
    "bash_heredoc_in_powershell": "Do not use Bash heredoc syntax in PowerShell; use a PowerShell here-string and Set-Content.",
    "unbounded_web_fetch": "Do not fetch or print a whole web page into context; use metadata, title, headings, or a small bounded excerpt.",
    "powershell_curl_unix_flags": "In PowerShell, curl is usually an Invoke-WebRequest alias; do not use Unix curl flags unless calling curl.exe explicitly.",
    "malformed_json_array_command": "Do not pass a malformed JSON command array as the PowerShell script; use a normal shell command array.",
    "split_powershell_command": "Pass one complete script string after powershell.exe -Command instead of splitting PowerShell parameters across the command array.",
    "direct_powershell_cmdlet": "Run PowerShell cmdlets through powershell.exe -Command; bare cmdlet names are not executable programs.",
}
REPEATED_URL_INSPECTION_DIAGNOSTIC = (
    "Open Gate blocked a repeated external URL inspection. Do not inspect the URL again; proceed from the prompt "
    "and create the requested artifact directly."
)
REPEATED_URL_ANSWER_DIAGNOSTIC = (
    "Open Gate blocked a repeated external URL inspection after a prior attempt. The URL could not be inspected "
    "in this run; answer from available context without more tool calls."
)
ARTIFACT_FIRST_DIAGNOSTIC = (
    "Open Gate blocked a non-productive inspection while the requested index.html artifact is still missing. "
    "Write the complete index.html file directly now."
)
HOSTED_WEB_SEARCH_UNSUPPORTED_DIAGNOSTIC = (
    "Open Gate blocked a hosted web_search call. Codex advertises web_search to hosted upstream models, "
    "but Codex CLI does not execute web_search when a local model returns it as a function call. "
    "Do not call web_search; use one bounded shell metadata request if shell is available, or proceed from the prompt."
)
TOOL_GUARDRAIL_MARKER = "Open Gate tool discipline:"
COMMON_UNAVAILABLE_TOOL_ALIASES = (
    "web_search",
    "browser",
    "browse",
    "fetch",
    "http",
    "read",
    "read_file",
    "write",
    "write_file",
    "edit",
    "apply_patch",
)
NATIVE_WEB_SEARCH_TOOL = "web_search"
WEB_TOOL_ALIASES = {"web_search", "browser", "browse", "fetch", "http", "web", "web_fetch"}
WEB_QUERY_ARGUMENT_KEYS = ("query", "q", "search_query", "url", "uri", "href", "target", "site", "website")
EXTERNAL_URL_RE = re.compile(r"https?://[^\s'\"<>)}\]]+", re.IGNORECASE)
SITE_QUERY_RE = re.compile(r"\bsite:(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?P<path>/[^\s'\"<>)}\]]*)?", re.IGNORECASE)
BARE_HOST_RE = re.compile(r"(?<![@\w.-])(?P<host>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(?P<path>/[^\s'\"<>)}\]]*)?")
ALLOWED_SPAWN_AGENT_TYPES = {"default", "explorer", "worker"}
SUBAGENT_INTENT_RE = re.compile(
    r"\b(sub-?agent|spawn(?:\s+an?|\s+multiple)?\s+agent|parallel\s+agent|delegate(?:\s+to)?\s+agent|"
    r"use\s+(?:multiple\s+)?agents|worker\s+agent|explorer\s+agent)\b",
    re.IGNORECASE,
)


@dataclass
class ProxyResult:
    upstream_request: JsonObject
    upstream_transform: JsonObject
    upstream_status: int
    upstream_response: JsonObject
    normalized_response: JsonObject
    returned_response: JsonObject
    normalization: JsonObject


@dataclass
class TextSlot:
    container: JsonObject
    key: str
    text: str
    allow_promotion: bool


@dataclass
class ContextCompileResult:
    text: str
    metadata: JsonObject


def forward_responses_request(
    request_body: JsonObject,
    upstream_base_url: str,
    api_key: str,
    timeout: float,
    normalization_mode: str = "repair",
    upstream_model: str | None = None,
    upstream_input_mode: str = "auto",
    context_policy: str = "full",
    context_max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
    context_recent_items: int = DEFAULT_CONTEXT_RECENT_ITEMS,
    instruction_policy: str = "auto",
    tool_schema_policy: str = "auto",
    upstream_capabilities: JsonObject | None = None,
) -> ProxyResult:
    if normalization_mode not in {"repair", "observe"}:
        raise ValueError(f"Unsupported normalization mode: {normalization_mode}")
    if upstream_input_mode not in {"auto", "native", "flatten"}:
        raise ValueError(f"Unsupported upstream input mode: {upstream_input_mode}")
    if context_policy not in CONTEXT_POLICIES:
        raise ValueError(f"Unsupported context policy: {context_policy}")
    if instruction_policy not in INSTRUCTION_POLICIES:
        raise ValueError(f"Unsupported instruction policy: {instruction_policy}")
    if tool_schema_policy not in TOOL_SCHEMA_POLICIES:
        raise ValueError(f"Unsupported tool schema policy: {tool_schema_policy}")
    upstream_request = deepcopy(request_body)
    requested_model = upstream_request.get("model")
    if upstream_model:
        upstream_request["model"] = upstream_model
    requested_stream = bool(upstream_request.get("stream"))
    upstream_request["stream"] = False
    upstream_transform = transform_upstream_request(
        upstream_request,
        upstream_input_mode,
        context_policy=context_policy,
        context_max_chars=context_max_chars,
        context_recent_items=context_recent_items,
        instruction_policy=instruction_policy,
        tool_schema_policy=tool_schema_policy,
        upstream_capabilities=upstream_capabilities,
    )
    upstream_transform["requested_model"] = requested_model
    upstream_transform["upstream_model"] = upstream_request.get("model")
    upstream_transform["model_overridden"] = bool(upstream_model and requested_model != upstream_model)
    status, upstream_response = post_json(upstream_base_url, "/responses", upstream_request, api_key, timeout)
    if should_retry_with_flattened_input(status, upstream_response, upstream_transform, upstream_input_mode):
        first_attempt = {
            "status": status,
            "request": upstream_request,
            "transform": upstream_transform,
            "response": upstream_response,
        }
        upstream_request = deepcopy(request_body)
        if upstream_model:
            upstream_request["model"] = upstream_model
        upstream_request["stream"] = False
        upstream_transform = transform_upstream_request(
            upstream_request,
            "flatten",
            context_policy=context_policy,
            context_max_chars=context_max_chars,
            context_recent_items=context_recent_items,
            instruction_policy=instruction_policy,
            tool_schema_policy=tool_schema_policy,
            upstream_capabilities=upstream_capabilities,
        )
        upstream_transform["retry_reason"] = "upstream_rejected_native_input"
        upstream_transform["first_attempt"] = {
            "status": first_attempt["status"],
            "transform": first_attempt["transform"],
            "response_error": first_attempt["response"].get("error"),
        }
        upstream_transform["requested_model"] = requested_model
        upstream_transform["upstream_model"] = upstream_request.get("model")
        upstream_transform["model_overridden"] = bool(upstream_model and requested_model != upstream_model)
        status, upstream_response = post_json(upstream_base_url, "/responses", upstream_request, api_key, timeout)
    normalized_response, normalization = normalize_responses_response(upstream_response, request_body)
    returned_response = deepcopy(normalized_response if normalization_mode == "repair" else upstream_response)
    normalization["mode"] = normalization_mode
    normalization["returned"] = "normalized_response" if normalization_mode == "repair" else "upstream_response"
    if requested_stream:
        returned_response["streamed_by_open_gate"] = True
    return ProxyResult(
        upstream_request=upstream_request,
        upstream_transform=upstream_transform,
        upstream_status=status,
        upstream_response=upstream_response,
        normalized_response=normalized_response,
        returned_response=returned_response,
        normalization=normalization,
    )


def transform_upstream_request(
    request_body: JsonObject,
    upstream_input_mode: str,
    context_policy: str = "full",
    context_max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
    context_recent_items: int = DEFAULT_CONTEXT_RECENT_ITEMS,
    instruction_policy: str = "auto",
    tool_schema_policy: str = "auto",
    upstream_capabilities: JsonObject | None = None,
) -> JsonObject:
    original_input = request_body.get("input")
    needs_flattening = needs_flattened_input(original_input)
    capability_reason = capability_flatten_reason(original_input, upstream_capabilities)
    tools = request_body.get("tools") if isinstance(request_body.get("tools"), list) else []
    context_forces_flatten = (
        upstream_input_mode == "auto" and context_policy == "spoon" and isinstance(original_input, list)
    )
    should_flatten = upstream_input_mode == "flatten" or (
        upstream_input_mode == "auto" and (needs_flattening or capability_reason or context_forces_flatten)
    )
    if not should_flatten:
        guardrail = inject_tool_guardrails(request_body, tools, upstream_capabilities=upstream_capabilities)
        diet = apply_request_diet(
            request_body,
            instruction_policy=instruction_policy,
            tool_schema_policy=tool_schema_policy,
        )
        return {
            "input_mode": "native",
            "reason": "compatible_input" if upstream_input_mode == "auto" else "forced_native",
            "context_policy": context_policy,
            "original_input_items": len(original_input) if isinstance(original_input, list) else None,
            **guardrail,
            **diet,
        }

    compiled = compile_responses_context(
        original_input,
        context_policy=context_policy,
        max_chars=context_max_chars,
        recent_items=context_recent_items,
        tools=tools,
    )
    request_body["input"] = compiled.text
    if context_policy == "spoon":
        guardrail = {"tool_guardrails_injected": False, "tool_guardrails_reason": "covered_by_spoon_header"}
    else:
        guardrail = inject_tool_guardrails(request_body, tools)
    diet = apply_request_diet(
        request_body,
        instruction_policy=instruction_policy,
        tool_schema_policy=tool_schema_policy,
    )
    reason = "forced_flatten"
    if upstream_input_mode == "auto":
        if needs_flattening:
            reason = "unsupported_responses_history"
        elif capability_reason:
            reason = capability_reason
        else:
            reason = "context_policy_spoon"
    return {
        "input_mode": "flattened",
        "reason": reason,
        "original_input_items": len(original_input) if isinstance(original_input, list) else None,
        **compiled.metadata,
        **guardrail,
        **diet,
    }


def inject_tool_guardrails(
    request_body: JsonObject,
    tools: list[JsonObject],
    upstream_capabilities: JsonObject | None = None,
) -> JsonObject:
    guardrail = build_tool_guardrail_text(tools)
    if not guardrail:
        return {"tool_guardrails_injected": False}
    input_value = request_body.get("input")
    if isinstance(input_value, str):
        if TOOL_GUARDRAIL_MARKER in input_value:
            return {"tool_guardrails_injected": False, "tool_guardrails_reason": "already_present"}
        request_body["input"] = f"{guardrail}\n\n{input_value}"
        return {"tool_guardrails_injected": True, "tool_guardrails_format": "text"}
    if isinstance(input_value, list):
        if any(isinstance(item, dict) and TOOL_GUARDRAIL_MARKER in flatten_input_item(item) for item in input_value):
            return {"tool_guardrails_injected": False, "tool_guardrails_reason": "already_present"}
        insert_at = leading_instruction_count(input_value)
        role = guardrail_message_role(upstream_capabilities)
        if role is None:
            if prepend_guardrail_to_first_user_message(input_value, guardrail):
                return {"tool_guardrails_injected": True, "tool_guardrails_format": "user_prefix"}
            request_body["input"] = f"{guardrail}\n\n{flatten_responses_input(input_value)}"
            return {"tool_guardrails_injected": True, "tool_guardrails_format": "flattened_fallback"}
        input_value.insert(
            insert_at,
            {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": guardrail}],
            },
        )
        return {"tool_guardrails_injected": True, "tool_guardrails_format": "message", "tool_guardrails_role": role}
    return {"tool_guardrails_injected": False, "tool_guardrails_reason": "unsupported_input"}


def guardrail_message_role(upstream_capabilities: JsonObject | None) -> str | None:
    if not isinstance(upstream_capabilities, dict):
        return "developer"
    if upstream_capabilities.get("supports_developer_role") is not False:
        return "developer"
    if upstream_capabilities.get("supports_system_role") is True:
        return "system"
    return None


def prepend_guardrail_to_first_user_message(input_items: list[Any], guardrail: str) -> bool:
    for item in input_items:
        if not isinstance(item, dict) or item.get("type") != "message" or item.get("role") != "user":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"input_text", "text"} and isinstance(part.get("text"), str):
                part["text"] = f"{guardrail}\n\n{part['text']}"
                return True
    return False


def leading_instruction_count(input_items: list[Any]) -> int:
    index = 0
    for item in input_items:
        if not isinstance(item, dict):
            break
        if item.get("type") != "message" or item.get("role") not in {"developer", "system"}:
            break
        index += 1
    return index


def build_tool_guardrail_text(tools: list[JsonObject]) -> str:
    tool_names = available_tool_names(tools)
    if not tool_names:
        return ""
    unavailable = [name for name in COMMON_UNAVAILABLE_TOOL_ALIASES if name not in tool_names]
    lines = [
        TOOL_GUARDRAIL_MARKER,
        f"- The only callable tools in this request are: {', '.join(tool_names)}.",
        "- If a tool name is not in that exact list, do not call it and do not print a raw tool-call tag for it.",
        "- Use structured tool calls only; never emit XML/JSON/function-call syntax as assistant text or reasoning.",
        "- Never create or truncate an empty target artifact as a placeholder; write the complete requested file when you call a tool.",
    ]
    if unavailable:
        lines.append(f"- These common aliases are unavailable here unless listed above: {', '.join(unavailable)}.")
    if "web_search" in tool_names and "shell" in tool_names:
        lines.append("- web_search is hosted by Codex; Open Gate converts URL lookups from web_search into bounded shell metadata fetches.")
    elif "web_search" in tool_names:
        lines.append("- web_search is hosted by Codex and may not execute as a local function call.")
    else:
        lines.append("- There is no web_search/browser tool here. For external URLs, make at most one small shell-based inspection if shell is listed; otherwise proceed from the prompt.")
    if "spawn_agent" in tool_names:
        lines.append("- spawn_agent is only for explicit user requests for subagents, delegation, or parallel agent work; otherwise do the work directly.")
        lines.append("- If spawn_agent is explicitly requested, agent_type must be one of: default, explorer, worker.")
    if "shell" in tool_names:
        lines.append("- When using shell on Windows, keep commands small and direct, and prefer the workdir argument over inline cd.")
    return "\n".join(lines)


def apply_request_diet(
    request_body: JsonObject,
    instruction_policy: str = "auto",
    tool_schema_policy: str = "auto",
) -> JsonObject:
    metadata: JsonObject = {
        "instruction_policy": instruction_policy,
        "tool_schema_policy": tool_schema_policy,
        "instruction_diet_applied": False,
        "tool_schema_diet_applied": False,
    }

    instructions = request_body.get("instructions")
    if isinstance(instructions, str):
        metadata["instructions_original_chars"] = len(instructions)
        should_digest = instruction_policy == "digest" or (
            instruction_policy == "auto" and len(instructions) > DEFAULT_INSTRUCTION_DIGEST_THRESHOLD
        )
        if should_digest:
            request_body["instructions"] = build_instruction_digest(instructions)
            metadata["instruction_diet_applied"] = True
        metadata["instructions_sent_chars"] = len(request_body.get("instructions") or "")

    tools = request_body.get("tools")
    if isinstance(tools, list):
        original_tools_chars = json_size(tools)
        metadata["tools_original_chars"] = original_tools_chars
        should_compact = tool_schema_policy == "compact" or (
            tool_schema_policy == "auto" and original_tools_chars > DEFAULT_TOOL_SCHEMA_COMPACT_THRESHOLD
        )
        if should_compact:
            request_body["tools"] = compact_tool_schemas(tools)
            metadata["tool_schema_diet_applied"] = True
        metadata["tools_sent_chars"] = json_size(request_body.get("tools"))

    metadata["upstream_body_chars"] = json_size(request_body)
    return metadata


def build_instruction_digest(_instructions: str) -> str:
    return "\n".join(
        [
            "Open Gate instruction digest:",
            "- You are a concise coding agent running inside Codex CLI.",
            "- Follow the latest user task, developer messages, environment context, and tool schemas.",
            "- Use only structured tool calls with advertised tool names and exact argument shapes.",
            "- Never print raw tool-call XML, JSON tool_calls arrays, recipient_name syntax, or function-call text.",
            "- Prefer small direct steps, update plans only when useful, and avoid loops after failures.",
            "- Respect sandbox and approval information in the request context.",
            "- Do not call spawn_agent unless the user explicitly asked for subagents, delegation, or parallel agent work.",
            "- When creating files, write the requested artifact directly instead of dumping large content to stdout.",
            "- Never create or truncate an empty target artifact as a placeholder.",
        ]
    )


def compact_tool_schemas(tools: list[Any]) -> list[Any]:
    return [compact_tool_schema(tool) for tool in tools]


def compact_tool_schema(tool: Any) -> Any:
    if not isinstance(tool, dict):
        return tool
    compacted: JsonObject = {}
    for key in ("type", "name", "strict"):
        if key in tool:
            compacted[key] = deepcopy(tool[key])
    if isinstance(tool.get("description"), str):
        compacted["description"] = compact_one_line(tool["description"], TOOL_DESCRIPTION_MAX_CHARS)
    if "parameters" in tool:
        compacted["parameters"] = compact_json_schema(tool.get("parameters"))
    if isinstance(tool.get("function"), dict):
        compacted["function"] = compact_tool_schema(tool["function"])
    for key, value in tool.items():
        if key not in compacted and key not in {"description", "parameters", "function"}:
            if key in {"required", "additionalProperties", "enum"}:
                compacted[key] = deepcopy(value)
    return compacted


def compact_json_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [compact_json_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return deepcopy(schema)
    compacted: JsonObject = {}
    preferred = (
        "type",
        "required",
        "additionalProperties",
        "enum",
        "const",
        "default",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "format",
    )
    for key in preferred:
        if key in schema:
            compacted[key] = deepcopy(schema[key])
    if isinstance(schema.get("description"), str):
        compacted["description"] = compact_one_line(schema["description"], SCHEMA_DESCRIPTION_MAX_CHARS)
    if isinstance(schema.get("properties"), dict):
        compacted["properties"] = {
            str(key): compact_json_schema(value) for key, value in schema["properties"].items()
        }
    for key in ("items", "oneOf", "anyOf", "allOf"):
        if key in schema:
            compacted[key] = compact_json_schema(schema[key])
    return compacted


def json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str))


def needs_flattened_input(input_value: Any) -> bool:
    if not isinstance(input_value, list):
        return False
    for item in input_value:
        if not isinstance(item, dict):
            return True
        item_type = item.get("type")
        if item_type != "message":
            return True
        role = item.get("role")
        if role not in {"developer", "system", "user"}:
            return True
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") not in {"input_text", "text"}:
                return True
    return False


def capability_flatten_reason(input_value: Any, upstream_capabilities: JsonObject | None) -> str | None:
    if not isinstance(input_value, list) or not isinstance(upstream_capabilities, dict):
        return None
    if upstream_capabilities.get("requires_flattened_input") is True:
        return "capability_requires_flattened_input"
    for item in input_value:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            if upstream_capabilities.get("supports_native_tool_history") is False:
                return "capability_rejects_native_tool_history"
            continue
        role = item.get("role")
        if role == "developer" and upstream_capabilities.get("supports_developer_role") is False:
            return "capability_rejects_developer_role"
        if role == "system" and upstream_capabilities.get("supports_system_role") is False:
            return "capability_rejects_system_role"
    return None


def should_retry_with_flattened_input(
    status: int,
    upstream_response: JsonObject,
    upstream_transform: JsonObject,
    upstream_input_mode: str,
) -> bool:
    if upstream_input_mode != "auto" or status < 400:
        return False
    if upstream_transform.get("input_mode") != "native":
        return False
    message = upstream_error_message(upstream_response).lower()
    markers = (
        "unexpected message role",
        "unsupported message role",
        "unsupported role",
        "invalid role",
        "function_call",
        "function_call_output",
    )
    return any(marker in message for marker in markers)


def upstream_error_message(response: JsonObject) -> str:
    error = response.get("error") if isinstance(response, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    return json.dumps(response, ensure_ascii=True, default=str)


def flatten_responses_input(input_value: Any) -> str:
    if isinstance(input_value, str):
        return input_value
    if not isinstance(input_value, list):
        return flatten_content(input_value)

    blocks: list[str] = []
    for item in input_value:
        if isinstance(item, dict):
            block = flatten_input_item(item)
        else:
            block = str(item)
        if block.strip():
            blocks.append(block.strip())
    return "\n\n".join(blocks)


def compile_responses_context(
    input_value: Any,
    context_policy: str = "full",
    max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
    recent_items: int = DEFAULT_CONTEXT_RECENT_ITEMS,
    tools: list[JsonObject] | None = None,
) -> ContextCompileResult:
    original = flatten_responses_input(input_value)
    if context_policy == "full" or not isinstance(input_value, list):
        return ContextCompileResult(
            text=original,
            metadata={
                "context_policy": context_policy,
                "original_flattened_chars": len(original),
                "flattened_chars": len(original),
                "summarized_input_items": 0,
                "exact_recent_items": len(input_value) if isinstance(input_value, list) else None,
                "dropped_context_chars": 0,
            },
        )

    return compile_spoon_context(
        input_value,
        original_flattened=original,
        max_chars=max_chars,
        recent_items=recent_items,
        tools=tools or [],
    )


def compile_spoon_context(
    items: list[Any],
    original_flattened: str,
    max_chars: int,
    recent_items: int,
    tools: list[JsonObject],
) -> ContextCompileResult:
    max_chars = max(4000, int(max_chars))
    recent_items = max(1, int(recent_items))
    exact_blocks = [
        spoon_recent_block(index, item, flatten_input_item(item) if isinstance(item, dict) else str(item))
        for index, item in enumerate(items)
    ]
    recent_count = min(recent_items, len(exact_blocks))
    older_count = max(0, len(exact_blocks) - recent_count)
    older_items = items[:older_count]
    older_blocks = exact_blocks[:older_count]
    recent_blocks = exact_blocks[older_count:]
    constraints = extract_context_constraints(items)
    user_constraints = extract_user_constraints(items)
    header = build_spoon_header(
        item_count=len(items),
        older_count=older_count,
        recent_count=recent_count,
        original_chars=len(original_flattened),
        max_chars=max_chars,
        tools=tools,
        user_constraints=user_constraints,
        constraints=constraints,
    )

    section_overhead = len("\n\nSummarized earlier context:\n\nRecent exact context:\n")
    summary_limit = min(max(1200, max_chars // 4), max(0, max_chars - len(header) - section_overhead - 1200))
    summary_text = fit_forward_blocks(
        [summarize_input_item(index, item, block) for index, (item, block) in enumerate(zip(older_items, older_blocks))],
        summary_limit,
    )
    recent_limit = max_chars - len(header) - len(summary_text) - section_overhead
    if recent_limit < 1200 and summary_text:
        summary_text = fit_forward_blocks(summary_text.split("\n\n"), max(0, len(summary_text) + recent_limit - 1200))
        recent_limit = max_chars - len(header) - len(summary_text) - section_overhead
    recent_text = fit_recent_blocks(recent_blocks, max(1200, recent_limit))

    parts = [header]
    if summary_text.strip():
        parts.append("Summarized earlier context:\n" + summary_text.strip())
    if recent_text.strip():
        parts.append("Recent exact context:\n" + recent_text.strip())
    text = "\n\n".join(part.strip() for part in parts if part.strip())
    if len(text) > max_chars:
        text = truncate_middle(text, max_chars)

    return ContextCompileResult(
        text=text,
        metadata={
            "context_policy": "spoon",
            "context_max_chars": max_chars,
            "context_recent_items": recent_items,
            "original_flattened_chars": len(original_flattened),
            "flattened_chars": len(text),
            "summarized_input_items": older_count,
            "exact_recent_items": recent_count,
            "dropped_context_chars": max(0, len(original_flattened) - len(text)),
            "user_constraints": user_constraints,
            "context_constraints": constraints,
        },
    )


def build_spoon_header(
    item_count: int,
    older_count: int,
    recent_count: int,
    original_chars: int,
    max_chars: int,
    tools: list[JsonObject],
    user_constraints: list[str],
    constraints: list[str],
) -> str:
    tool_names = available_tool_names(tools)
    unavailable = [name for name in COMMON_UNAVAILABLE_TOOL_ALIASES if name not in tool_names]
    lines = [
        "Open Gate context digest:",
        f"- Policy: spoon; original items={item_count}; summarized earlier items={older_count}; exact recent items={recent_count}.",
        f"- Original flattened size={original_chars} chars; budget={max_chars} chars.",
        "- Use only the provided tool schemas and exact argument shapes. If a tool name is not listed below, do not call it.",
        "- Use structured tool calls only; never emit XML/JSON/function-call syntax as assistant text or reasoning.",
        "- Prefer small targeted tool calls. For file changes, use compact shell commands unless an edit-specific tool is explicitly listed.",
        "- For external URLs, make at most one lightweight inspection attempt; if unavailable, proceed from the prompt instead of researching in loops.",
        "- For web page inspection, fetch only metadata, title, headings, or a small bounded excerpt; do not print full HTML into context.",
        "- If site access, network access, or a dependency failed earlier, adapt from available context instead of repeating the same failing route.",
    ]
    if tool_names:
        lines.append(f"- Available tool names include: {', '.join(tool_names[:24])}.")
        if unavailable:
            lines.append(f"- These common aliases are unavailable here unless listed above: {', '.join(unavailable)}.")
        if "web_search" in tool_names and "shell" in tool_names:
            lines.append("- web_search is hosted by Codex; Open Gate converts URL lookups from web_search into bounded shell metadata fetches.")
        elif "web_search" in tool_names:
            lines.append("- web_search is hosted by Codex and may not execute as a local function call.")
        else:
            lines.append("- There is no web_search/browser tool here. For external URLs, use at most one small shell-based inspection if shell is listed; otherwise proceed from the prompt.")
        if "spawn_agent" in tool_names:
            lines.append("- spawn_agent is only for explicit user requests for subagents, delegation, or parallel agent work; otherwise do the work directly.")
            lines.append("- If spawn_agent is explicitly requested, agent_type must be one of: default, explorer, worker.")
        if "apply_patch" not in tool_names:
            lines.append("- apply_patch is not available in this Codex session; do not call it.")
        if "write" not in tool_names:
            lines.append("- write and write_file are not available in this Codex session; do not call them.")
        if "read" not in tool_names:
            lines.append("- read and read_file are not available in this Codex session; use shell Get-Content when file inspection is needed.")
        if "view_image" in tool_names:
            lines.append("- view_image is only for local image files such as .png/.jpg/.webp, not directories, project roots, URLs, or webpages.")
        if "shell" in tool_names:
            lines.append("- shell commands run on Windows PowerShell here; use the workdir argument instead of inline relative cd when possible.")
            lines.append("- To create index.html with shell, write to index.html; do not echo the full HTML document to stdout.")
            lines.append("- If the task requires one index.html file, write the complete final file instead of creating or truncating an empty placeholder first.")
            lines.append("- Do not use Bash heredoc syntax like cat > file << EOF in PowerShell; use a PowerShell here-string with Set-Content.")
    if user_constraints:
        lines.append("Durable user constraints:")
        lines.append("- Treat these as hard requirements for the final artifact.")
        lines.extend(f"- {constraint}" for constraint in user_constraints[:12])
    if constraints:
        lines.append("Known constraints from prior tool/tool-call failures:")
        lines.extend(f"- {constraint}" for constraint in constraints[:12])
    return "\n".join(lines)


def available_tool_names(tools: list[JsonObject]) -> list[str]:
    try:
        names = sorted(load_tool_specs(tools).keys())
    except Exception:  # pragma: no cover - defensive against malformed tool schemas.
        names = []
    return names


def summarize_input_item(index: int, item: Any, exact_block: str) -> str:
    if not isinstance(item, dict):
        return f"[{index}] item chars={len(exact_block)}: {compact_one_line(exact_block, CONTEXT_SUMMARY_PREVIEW_CHARS)}"

    item_type = item.get("type") or "item"
    if item_type == "message":
        role = item.get("role") or "message"
        text = flatten_content(item.get("content"))
        return f"[{index}] message role={role} chars={len(text)}: {compact_one_line(text, CONTEXT_SUMMARY_PREVIEW_CHARS)}"

    if item_type in {"function_call", "custom_tool_call"}:
        name = item.get("name") or "tool"
        call_id = item.get("call_id") or ""
        args = item.get("arguments") or "{}"
        summary = compact_one_line(args, CONTEXT_SUMMARY_PREVIEW_CHARS)
        issue_names = sorted({issue["issue"] for issue in inspect_tool_calls([source_call(item, index)]) if issue.get("issue")})
        issue_text = f"; command issues={', '.join(issue_names)}" if issue_names else ""
        return f"[{index}] assistant tool call {name} {call_id} args_chars={len(str(args))}{issue_text}: {summary}"

    if item_type in {"function_call_output", "custom_tool_call_output"}:
        call_id = item.get("call_id") or ""
        output = flatten_content(item.get("output"))
        preview = important_output_preview(output)
        return f"[{index}] tool output {call_id} chars={len(output)}:\n{preview}"

    return f"[{index}] {item_type} chars={len(exact_block)}: {compact_one_line(exact_block, CONTEXT_SUMMARY_PREVIEW_CHARS)}"


def spoon_recent_block(index: int, item: Any, exact_block: str) -> str:
    if not isinstance(item, dict) or item.get("type") not in {"function_call_output", "custom_tool_call_output"}:
        return exact_block
    output = flatten_content(item.get("output"))
    if len(output) <= CONTEXT_RECENT_TOOL_OUTPUT_MAX_CHARS:
        return exact_block
    return summarize_input_item(index, item, exact_block)


def source_call(item: JsonObject, index: int) -> JsonObject:
    copied = deepcopy(item)
    copied["source"] = f"input[{index}]"
    return copied


def extract_context_constraints(items: list[Any]) -> list[str]:
    constraints: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in {"function_call", "custom_tool_call"}:
            for issue in inspect_tool_calls([source_call(item, index)]):
                hint = COMMAND_ISSUE_HINTS.get(str(issue.get("issue")))
                if hint:
                    constraints.append(hint)
        if item_type in {"function_call_output", "custom_tool_call_output"}:
            constraints.extend(constraints_from_tool_output(flatten_content(item.get("output"))))
    return dedupe_keep_order(constraints)


def extract_user_constraints(items: list[Any]) -> list[str]:
    constraints: list[str] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "message" or item.get("role") != "user":
            continue
        text = flatten_content(item.get("content"))
        for line in text.splitlines():
            cleaned = re.sub(r"\s+", " ", line.strip(" -\t")).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if is_durable_user_constraint(lowered):
                constraints.append(truncate_middle(cleaned, 180))
    return dedupe_keep_order(constraints)


def is_durable_user_constraint(lowered_line: str) -> bool:
    if "://" in lowered_line and len(lowered_line) > 90:
        return False
    markers = (
        "goal:",
        "everything must",
        "must be",
        "no frameworks",
        "choose one",
        "one theme",
        "include ",
        "add at least",
        "make it",
        "keep performance",
        "responsive",
        "smooth",
        "contained in index.html",
    )
    return any(marker in lowered_line for marker in markers)


def constraints_from_tool_output(output: str) -> list[str]:
    lowered = output.lower()
    constraints: list[str] = []
    for tool_name in re.findall(r"unsupported call:\s*([A-Za-z_][A-Za-z0-9_]*)", output):
        constraints.append(f"Tool {tool_name!r} was unsupported in this Codex session; choose from the advertised tool schemas.")
    if "winerror 10013" in lowered:
        constraints.append("Shell/web socket access hit WinError 10013; avoid repeated shell-based web fetch attempts.")
    if "failed to spawn: playwright" in lowered or "playwright" in lowered and "not recognized" in lowered:
        constraints.append("The Playwright executable was unavailable; avoid retrying the same playwright command unless the dependency is installed.")
    if "timed out" in lowered or "timeout" in lowered:
        constraints.append("A previous operation timed out; keep the next tool call smaller and more direct.")
    if "unbounded_web_fetch" in lowered or "whole web page" in lowered:
        constraints.append("Avoid fetching or printing a whole web page; use metadata, title, headings, or a small bounded excerpt.")
    if "repeated external url inspection" in lowered or "do not inspect the url again" in lowered:
        constraints.append("External URL inspection was already attempted; do not call shell for that URL again.")
    if "open gate blocked an empty file write" in lowered or "empty_artifact_write" in lowered:
        constraints.append("Do not create or truncate empty artifact files; write the complete requested file content in one valid tool call.")
    if "not recognized as the name of" in lowered:
        constraints.append("A shell command was not recognized; verify commands before relying on them.")
    return constraints


def important_output_preview(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    important = [line for line in lines if IMPORTANT_OUTPUT_RE.search(line)]
    if important:
        return truncate_middle("\n".join(important[:8]), CONTEXT_OUTPUT_PREVIEW_CHARS)
    if len(lines) <= 6:
        return truncate_middle("\n".join(lines), CONTEXT_OUTPUT_PREVIEW_CHARS)
    return truncate_middle("\n".join([*lines[:3], "...", *lines[-3:]]), CONTEXT_OUTPUT_PREVIEW_CHARS)


def fit_forward_blocks(blocks: list[str], limit: int) -> str:
    if limit <= 0:
        return ""
    kept: list[str] = []
    used = 0
    for block in blocks:
        cleaned = block.strip()
        if not cleaned:
            continue
        needed = len(cleaned) + (2 if kept else 0)
        if used + needed <= limit:
            kept.append(cleaned)
            used += needed
            continue
        remaining = limit - used - (2 if kept else 0)
        if remaining > 160:
            kept.append(truncate_middle(cleaned, remaining))
        break
    return "\n\n".join(kept)


def fit_recent_blocks(blocks: list[str], limit: int) -> str:
    if limit <= 0:
        return ""
    kept_reversed: list[str] = []
    used = 0
    for block in reversed(blocks):
        cleaned = block.strip()
        if not cleaned:
            continue
        needed = len(cleaned) + (2 if kept_reversed else 0)
        if used + needed <= limit:
            kept_reversed.append(cleaned)
            used += needed
            continue
        remaining = limit - used - (2 if kept_reversed else 0)
        if remaining > 240:
            kept_reversed.append(truncate_middle(cleaned, remaining))
        break
    return "\n\n".join(reversed(kept_reversed))


def compact_one_line(text: Any, limit: int) -> str:
    return truncate_middle(re.sub(r"\s+", " ", str(text)).strip(), limit)


def truncate_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 32:
        return text[:limit]
    marker = f"\n[... omitted {len(text) - limit} chars ...]\n"
    if len(marker) >= limit:
        return text[:limit]
    head = (limit - len(marker)) // 2
    tail = limit - len(marker) - head
    return text[:head] + marker + text[-tail:]


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def flatten_input_item(item: JsonObject) -> str:
    item_type = item.get("type")
    if item_type == "message":
        role = item.get("role") or "message"
        return f"{role}:\n{flatten_content(item.get('content'))}"
    if item_type in {"function_call", "custom_tool_call"}:
        name = item.get("name") or "tool"
        call_id = item.get("call_id") or ""
        arguments = item.get("arguments") or "{}"
        return f"assistant tool call {name} {call_id}:\n{arguments}"
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        call_id = item.get("call_id") or ""
        return f"tool output {call_id}:\n{flatten_content(item.get('output'))}"
    return f"{item_type or 'item'}:\n{json.dumps(item, ensure_ascii=True, separators=(',', ':'))}"


def post_json(base_url: str, path: str, body: JsonObject, api_key: str, timeout: float) -> tuple[int, JsonObject]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    raw = json.dumps(body, ensure_ascii=True).encode("utf-8")
    request = Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload) if payload else {}
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: JsonObject = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            parsed = {"error": {"message": payload}}
        return exc.code, parsed
    except URLError as exc:
        return 599, {"error": {"message": f"Connection failed: {exc.reason}", "type": "upstream_connection_error"}}
    except TimeoutError as exc:
        message = str(exc) or "timed out"
        return 599, {"error": {"message": message, "type": "TimeoutError"}}


def normalize_responses_response(response: JsonObject, original_request: JsonObject) -> tuple[JsonObject, JsonObject]:
    normalized = deepcopy(response)
    tools = original_request.get("tools") if isinstance(original_request.get("tools"), list) else []
    upstream_command_quality_issues = inspect_tool_calls(collect_existing_function_calls(normalized))
    repairs = repair_structured_calls(normalized, tools)
    web_tool_alias_repairs = route_web_tool_aliases(normalized, original_request, tools)
    suppressed = suppress_structured_calls_if_blocked(normalized, original_request)
    policy_suppressed = suppress_policy_blocked_structured_calls(normalized, original_request, tools)
    command_quality_suppressed = suppress_command_quality_blocked_structured_calls(normalized, tools)
    text_slots = collect_response_text_slots(normalized)
    existing_calls = collect_existing_function_calls(normalized)
    promoted: list[ToolCall] = []
    stripped = 0
    invalid_calls: list[JsonObject] = []
    text_candidate_repairs: list[JsonObject] = []
    seen_candidates: set[str] = set()
    seen_invalid: set[str] = set()

    for slot in text_slots:
        report = analyze_text(slot.text, tools)
        if report.tool_calls or report.leaks:
            stripped += 1
            slot.container[slot.key] = report.cleaned_text
        if not slot.allow_promotion:
            continue
        for call in report.tool_calls:
            repaired_call, candidate_repairs = repair_text_tool_call_candidate(call, tools)
            if candidate_repairs:
                text_candidate_repairs.extend(candidate_repairs)
            repaired_call, web_tool_alias_repair = route_web_tool_alias_candidate(repaired_call, original_request, tools)
            if web_tool_alias_repair:
                text_candidate_repairs.append(web_tool_alias_repair)
            policy_errors = policy_tool_call_errors(repaired_call.name, repaired_call.arguments, original_request)
            if policy_errors:
                repaired_call.valid = False
                repaired_call.errors.extend(policy_errors)
            quarantined_call, quarantine_repair = quarantine_command_quality_tool_call(repaired_call, tools)
            if quarantine_repair:
                repaired_call = quarantined_call
                text_candidate_repairs.append(quarantine_repair)
            else:
                command_quality_errors = blocking_command_quality_errors(repaired_call)
                if command_quality_errors:
                    repaired_call.valid = False
                    repaired_call.errors.extend(command_quality_errors)
            if repaired_call.valid:
                key = tool_call_candidate_key(repaired_call)
                if key not in seen_candidates:
                    seen_candidates.add(key)
                    promoted.append(repaired_call)
            else:
                key = tool_call_candidate_key(repaired_call)
                if key not in seen_invalid:
                    seen_invalid.add(key)
                    invalid_calls.append(repaired_call.to_json())

    should_promote = bool(promoted and not existing_calls and should_promote_tool_calls(original_request))
    if should_promote:
        output = normalized.setdefault("output", [])
        output[:] = [item for item in output if not is_empty_message(item)]
        for call in promoted:
            output.append(build_function_call_item(call))
        repairs.extend(repair_structured_calls(normalized, tools))
    removed_reasoning_items = 0
    if has_empty_artifact_quarantine([*repairs, *text_candidate_repairs]):
        removed_reasoning_items = remove_reasoning_items(normalized)
    actionable_output_repair = None
    if not suppressed and not policy_suppressed and isinstance(normalized.get("output"), list):
        actionable_output_repair = ensure_actionable_output(normalized, tools)
    normalized_command_quality_issues = inspect_tool_calls(collect_existing_function_calls(normalized))

    normalization = {
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "suppressed_structured_calls": suppressed,
        "policy_suppressed_structured_calls": policy_suppressed,
        "command_quality_suppressed_structured_calls": command_quality_suppressed,
        "structured_argument_repairs": repairs,
        "web_tool_alias_repairs": web_tool_alias_repairs,
        "text_tool_call_repairs": text_candidate_repairs,
        "upstream_command_quality_issues": upstream_command_quality_issues,
        "normalized_command_quality_issues": normalized_command_quality_issues,
        "actionable_output_repair": actionable_output_repair,
        "reasoning_items_removed": removed_reasoning_items,
        "stripped_text_items": stripped,
        "existing_structured_calls": len(existing_calls),
        "promoted_tool_calls": [call.to_json() for call in promoted] if should_promote else [],
        "promotion_candidates": [call.to_json() for call in promoted],
        "invalid_tool_calls": invalid_calls,
        "promotion_blocked": bool(promoted and not should_promote),
        "promotion_block_reason": promotion_block_reason(original_request, existing_calls, promoted),
    }
    return normalized, normalization


def collect_response_text_slots(response: JsonObject) -> list[TextSlot]:
    out: list[TextSlot] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type not in ("message", "reasoning"):
            continue
        allow_promotion = item_type == "message"
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("output_text", "reasoning_text", "text") and isinstance(part.get("text"), str):
                out.append(TextSlot(part, "text", part["text"], allow_promotion=allow_promotion))
    if isinstance(response.get("output_text"), str):
        out.append(TextSlot(response, "output_text", response["output_text"], allow_promotion=True))
    return out


def repair_text_tool_call_candidate(call: ToolCall, tools: list[JsonObject]) -> tuple[ToolCall, list[JsonObject]]:
    temp = {"output": [build_function_call_item(call)]}
    repairs = repair_structured_calls(temp, tools)
    if not repairs:
        return call, []

    repaired_call = ToolCall(
        name=call.name,
        arguments=parse_function_call_arguments(temp["output"][0]),
        source=call.source,
        span=call.span,
        raw=call.raw,
    )
    validated = analyze_text(json.dumps({"tool": repaired_call.name, "arguments": repaired_call.arguments}), tools)
    if validated.tool_calls:
        repaired_call.valid = validated.tool_calls[0].valid
        repaired_call.errors = list(validated.tool_calls[0].errors)
    return repaired_call, [{"source": call.source, **repair} for repair in repairs]


def parse_function_call_arguments(call: JsonObject) -> JsonObject:
    arguments = call.get("arguments")
    if not isinstance(arguments, str):
        return {}
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def tool_call_candidate_key(call: ToolCall) -> str:
    try:
        args = json.dumps(call.arguments, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        args = repr(call.arguments)
    return f"{call.name}\0{args}"


def collect_existing_function_calls(response: JsonObject) -> list[JsonObject]:
    calls: list[JsonObject] = []
    for item in response.get("output") or []:
        if isinstance(item, dict) and item.get("type") in ("function_call", "custom_tool_call"):
            calls.append(item)
    return calls


def route_web_tool_aliases(response: JsonObject, request_body: JsonObject, tools: list[JsonObject]) -> list[JsonObject]:
    target = web_alias_shell_tool_name(tools)
    if target is None:
        return []
    output = response.get("output")
    if not isinstance(output, list):
        return []

    repairs: list[JsonObject] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") not in ("function_call", "custom_tool_call"):
            continue
        repair = route_web_tool_alias_item(item, request_body, tools, target)
        if repair is not None:
            repairs.append(repair)
    return repairs


def route_web_tool_alias_item(
    item: JsonObject,
    request_body: JsonObject,
    tools: list[JsonObject],
    target: str,
) -> JsonObject | None:
    name = item.get("name")
    if not isinstance(name, str):
        return None
    arguments = parse_function_call_arguments(item)
    route_reason = web_tool_route_reason(name, arguments)
    if route_reason is None:
        return None
    query = web_search_query_from_call(name, arguments, request_body)
    if query is None:
        return None

    before = deepcopy(arguments)
    after = shell_web_metadata_arguments(query)
    if name == target and before == after:
        return None

    item["type"] = "function_call"
    item["name"] = target
    item["arguments"] = json.dumps(after, ensure_ascii=True, separators=(",", ":"))
    return {
        "source": "responses_structured",
        "tool": name,
        "before": before,
        "after_tool": target,
        "after": after,
        "reason": route_reason,
    }


def route_web_tool_alias_candidate(
    call: ToolCall,
    request_body: JsonObject,
    tools: list[JsonObject],
) -> tuple[ToolCall, JsonObject | None]:
    target = web_alias_shell_tool_name(tools)
    if target is None:
        return call, None
    route_reason = web_tool_route_reason(call.name, call.arguments)
    if route_reason is None:
        return call, None
    query = web_search_query_from_call(call.name, call.arguments, request_body)
    if query is None:
        return call, None

    after = shell_web_metadata_arguments(query)
    routed = ToolCall(
        name=target,
        arguments=after,
        source=call.source,
        span=call.span,
        raw=call.raw,
        valid=True,
        errors=[],
    )
    return routed, {
        "source": call.source,
        "tool": call.name,
        "before": call.arguments,
        "after_tool": target,
        "after": after,
        "reason": route_reason,
    }


def web_alias_shell_tool_name(tools: list[JsonObject]) -> str | None:
    return "shell" if "shell" in load_tool_specs(tools) else None


def web_tool_route_reason(name: str, arguments: JsonObject) -> str | None:
    if name in WEB_TOOL_ALIASES:
        return "hosted_web_tool_to_shell_metadata"
    return None


def shell_call_is_web_inspection(arguments: JsonObject) -> bool:
    script = shell_script_text(arguments).lower()
    if not script:
        return False
    return bool(
        re.search(
            r"\b(invoke-webrequest|invoke-restmethod|curl(?:\.exe)?|wget|irm|iwr|webrequest|httpclient)\b",
            script,
        )
    )


def web_search_query_from_call(name: str, arguments: JsonObject, request_body: JsonObject) -> str | None:
    for key in WEB_QUERY_ARGUMENT_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return clean_web_query(value)
        if isinstance(value, list):
            joined = " ".join(str(item) for item in value if item is not None).strip()
            if joined:
                return clean_web_query(joined)

    argument_text = shell_script_text(arguments) if name == "shell" else json.dumps(arguments, ensure_ascii=True, default=str)
    url = first_external_url(argument_text)
    if url:
        return url

    user_text = latest_user_text(request_body) or all_user_text(request_body)
    url = first_external_url(user_text)
    if url:
        return url

    fallback = compact_one_line(user_text, 240)
    return fallback or None


def clean_web_query(value: str) -> str:
    cleaned = value.strip().strip("'\"")
    url = first_external_url(cleaned)
    return url or cleaned


def first_external_url(text: str) -> str | None:
    match = EXTERNAL_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;\\")


def shell_web_metadata_arguments(query: str) -> JsonObject:
    url = web_query_url(query)
    if not url:
        diagnostic = (
            "Open Gate cannot emulate keyword web_search with a local shell call because no URL was provided. "
            "Proceed from the prompt or ask for a URL."
        )
        return {"command": ["powershell.exe", "-Command", "Write-Output " + powershell_quote(diagnostic)]}

    script = (
        "$ErrorActionPreference='Stop';"
        f"$uri={powershell_quote(url)};"
        "$tmp=[System.IO.Path]::GetTempFileName();"
        "try{"
        "$response=Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 3 -OutFile $tmp -PassThru;"
        "$bytes=[System.IO.File]::ReadAllBytes($tmp);"
        "$count=[Math]::Min($bytes.Length,4096);"
        "$sample=[System.Text.Encoding]::UTF8.GetString($bytes,0,$count);"
        "$title='';"
        "if($sample -match '<title[^>]*>\\s*(.*?)\\s*</title>'){$title=($Matches[1] -replace '\\s+',' ').Trim()};"
        "[ordered]@{url=$uri;status=$response.StatusCode;content_type=$response.Headers['Content-Type'];title=$title;excerpt=$sample}|ConvertTo-Json -Compress"
        "}catch{"
        "Write-Output ('Open Gate bounded web metadata fetch failed: '+$_.Exception.Message)"
        "}finally{"
        "Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue"
        "}"
    )
    return {"command": ["powershell.exe", "-Command", script]}


def web_query_url(query: str) -> str | None:
    url = first_external_url(query)
    if url:
        return url
    site_match = SITE_QUERY_RE.search(query)
    if site_match:
        return url_from_host_match(site_match)
    host_match = BARE_HOST_RE.search(query)
    if host_match:
        return url_from_host_match(host_match)
    return None


def url_from_host_match(match: re.Match[str]) -> str:
    host = match.group("host").rstrip(".,;")
    path = (match.group("path") or "/").rstrip(".,;\\")
    if not path.startswith("/"):
        path = "/" + path
    return f"https://{host}{path}"


def repair_structured_calls(response: JsonObject, tools: list[JsonObject]) -> list[JsonObject]:
    specs = load_tool_specs(tools)
    repairs: list[JsonObject] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") not in ("function_call", "custom_tool_call"):
            continue
        name = item.get("name")
        if not isinstance(name, str) or name not in specs:
            continue
        try:
            args = json.loads(item.get("arguments") or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(args, dict):
            continue
        original = deepcopy(args)
        schema = specs[name].parameters or {}
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, prop in properties.items():
                if not isinstance(prop, dict) or key not in args:
                    continue
                if prop.get("type") == "array" and isinstance(args[key], str):
                    args[key] = coerce_string_to_array_argument(name, key, args[key])
            if schema.get("additionalProperties") is False:
                args = {key: value for key, value in args.items() if key in properties}
        if name == "shell":
            shell_repaired = repair_shell_arguments(args)
            if shell_repaired is not None:
                args = shell_repaired
        if args != original:
            item["arguments"] = json.dumps(args, ensure_ascii=True, separators=(",", ":"))
            repairs.append({"tool": name, "before": original, "after": args})
    return repairs


def coerce_string_to_array_argument(tool_name: str, key: str, value: str) -> list[str]:
    if tool_name == "shell" and key == "command":
        parsed = parse_shell_array_string(value)
        if parsed is not None:
            return parsed
        return ["powershell.exe", "-Command", value]
    return [value]


def suppress_structured_calls_if_blocked(response: JsonObject, request_body: JsonObject) -> list[JsonObject]:
    if should_promote_tool_calls(request_body):
        return []
    tool_choice = request_body.get("tool_choice", "auto")
    if tool_choice not in ("auto", None):
        return []
    output = response.get("output")
    if not isinstance(output, list):
        return []
    suppressed: list[JsonObject] = []
    kept: list[JsonObject] = []
    for item in output:
        if isinstance(item, dict) and item.get("type") in ("function_call", "custom_tool_call"):
            suppressed.append(item)
        else:
            kept.append(item)
    if suppressed:
        response["output"] = kept
    return suppressed


def suppress_policy_blocked_structured_calls(
    response: JsonObject, request_body: JsonObject, tools: list[JsonObject]
) -> list[JsonObject]:
    output = response.get("output")
    if not isinstance(output, list):
        return []
    suppressed: list[JsonObject] = []
    kept: list[JsonObject] = []
    for item in output:
        if isinstance(item, dict) and item.get("type") in ("function_call", "custom_tool_call"):
            errors = policy_tool_call_errors(item.get("name"), parse_function_call_arguments(item), request_body)
            if errors:
                copied = deepcopy(item)
                copied["policy_errors"] = errors
                quarantine = quarantine_policy_blocked_call(item, errors, tools, request_body)
                if quarantine is not None:
                    copied["quarantined_as"] = quarantine
                    kept.append(quarantine)
                suppressed.append(copied)
                continue
        kept.append(item)
    if suppressed:
        response["output"] = kept
    return suppressed


def quarantine_policy_blocked_call(
    item: JsonObject, errors: list[str], tools: list[JsonObject], request_body: JsonObject
) -> JsonObject | None:
    if item.get("name") != "shell":
        return None
    diagnostic = None
    if any("external URL inspection already attempted" in error for error in errors):
        if not request_requires_index_artifact(request_body):
            return build_assistant_message(REPEATED_URL_ANSWER_DIAGNOSTIC)
        diagnostic = REPEATED_URL_INSPECTION_DIAGNOSTIC
    elif any("artifact creation is pending" in error for error in errors):
        diagnostic = ARTIFACT_FIRST_DIAGNOSTIC
    if diagnostic is None:
        return None
    arguments = parse_function_call_arguments(item)
    call = diagnostic_tool_call(
        diagnostic,
        tools,
        source="open_gate_policy_guard",
        raw=json.dumps(item, ensure_ascii=True),
        shell_arguments=arguments,
    )
    if call is None:
        return None
    return build_function_call_item(call)


def build_assistant_message(text: str) -> JsonObject:
    return {
        "id": f"msg_og_{uuid.uuid4().hex}",
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def suppress_command_quality_blocked_structured_calls(response: JsonObject, tools: list[JsonObject]) -> list[JsonObject]:
    output = response.get("output")
    if not isinstance(output, list):
        return []
    suppressed: list[JsonObject] = []
    kept: list[JsonObject] = []
    for item in output:
        if isinstance(item, dict) and item.get("type") in ("function_call", "custom_tool_call"):
            errors = [issue for issue in inspect_tool_calls([item]) if issue.get("severity") == "error"]
            if errors:
                copied = deepcopy(item)
                copied["command_quality_errors"] = errors
                quarantine = quarantine_structured_command_quality_call(item, errors, tools)
                if quarantine is not None:
                    copied["quarantined_as"] = quarantine
                    kept.append(quarantine)
                suppressed.append(copied)
                continue
        kept.append(item)
    if suppressed:
        response["output"] = kept
        if not any("quarantined_as" in item for item in suppressed):
            append_command_quality_suppression_message(response, suppressed)
    return suppressed


def quarantine_structured_command_quality_call(
    item: JsonObject, errors: list[JsonObject], tools: list[JsonObject]
) -> JsonObject | None:
    name = item.get("name")
    if name != "shell":
        return None
    arguments = parse_function_call_arguments(item)
    issue_names = dedupe_keep_order([str(issue.get("issue")) for issue in errors if issue.get("issue")])
    diagnostic = command_quality_diagnostic_text(issue_names)
    quarantined = diagnostic_tool_call(
        diagnostic,
        tools,
        source="responses_structured",
        raw=json.dumps(item, ensure_ascii=True),
        shell_arguments=arguments,
    )
    if quarantined is None:
        return None
    return build_function_call_item(quarantined)


def append_command_quality_suppression_message(response: JsonObject, suppressed: list[JsonObject]) -> None:
    output = response.setdefault("output", [])
    if not isinstance(output, list) or has_visible_or_callable_output(output):
        return
    issue_names = dedupe_keep_order(
        [
            str(issue.get("issue"))
            for item in suppressed
            for issue in item.get("command_quality_errors", [])
            if issue.get("issue")
        ]
    )
    issue_text = ", ".join(issue_names[:4]) or "command_quality"
    output.append(
        {
            "id": f"msg_og_suppressed_{uuid.uuid4().hex}",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": f"Open Gate suppressed an invalid tool call ({issue_text}). Continue with a smaller valid structured tool call.",
                    "annotations": [],
                }
            ],
        }
    )


def has_visible_or_callable_output(output: list[Any]) -> bool:
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") in ("function_call", "custom_tool_call"):
            return True
        if item.get("type") == "message" and not is_empty_message(item):
            return True
    return False


def has_tool(tools: list[JsonObject], name: str) -> bool:
    return name in load_tool_specs(tools)


def diagnostic_tool_call(
    diagnostic: str,
    tools: list[JsonObject],
    source: str,
    raw: str = "",
    shell_arguments: JsonObject | None = None,
) -> ToolCall | None:
    if has_tool(tools, "shell"):
        return ToolCall(
            name="shell",
            arguments={
                **(shell_arguments or {}),
                "command": ["powershell.exe", "-Command", "Write-Output " + powershell_quote(diagnostic)],
            },
            source=source,
            span=(0, 0),
            raw=raw,
            valid=True,
            errors=[],
        )
    return None


ACTIONABLE_OUTPUT_DIAGNOSTIC = (
    "Open Gate detected a model response with reasoning only and no tool call or final message. "
    "Continue with a direct valid structured tool call now; if creating a file, write the complete requested artifact."
)


def ensure_actionable_output(response: JsonObject, tools: list[JsonObject]) -> JsonObject | None:
    output = response.get("output")
    if not isinstance(output, list):
        output = []
        response["output"] = output
    if has_visible_or_callable_output(output):
        return None

    call = diagnostic_tool_call(
        ACTIONABLE_OUTPUT_DIAGNOSTIC,
        tools,
        source="open_gate_actionable_output_guard",
    )
    if call is None:
        message = {
            "id": f"msg_og_actionable_{uuid.uuid4().hex}",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": ACTIONABLE_OUTPUT_DIAGNOSTIC, "annotations": []}],
        }
        output.append(message)
        return {"type": "diagnostic_message", "reason": "no_visible_or_callable_output", "added": message}

    item = build_function_call_item(call)
    output.append(item)
    return {"type": "diagnostic_tool_call", "reason": "no_visible_or_callable_output", "tool": call.name, "added": item}


def has_empty_artifact_quarantine(repairs: list[JsonObject]) -> bool:
    return any(EMPTY_ARTIFACT_WRITE_DIAGNOSTIC in json.dumps(repair, ensure_ascii=True, default=str) for repair in repairs)


def remove_reasoning_items(response: JsonObject) -> int:
    output = response.get("output")
    if not isinstance(output, list):
        return 0
    kept = [item for item in output if not (isinstance(item, dict) and item.get("type") == "reasoning")]
    removed = len(output) - len(kept)
    if removed:
        response["output"] = kept
    return removed


def policy_tool_call_errors(name: Any, arguments: JsonObject, request_body: JsonObject) -> list[str]:
    errors: list[str] = []
    if name == "shell" and shell_arguments_contain_external_url(arguments) and has_prior_external_url_shell_call(request_body):
        errors.append("external URL inspection already attempted; proceed from the prompt instead of fetching again")
    if name == "shell" and should_block_artifact_delay_shell_call(arguments, request_body):
        errors.append("artifact creation is pending; write the requested index.html directly instead of inspecting")
    if name == "spawn_agent":
        if not has_explicit_subagent_intent(request_body):
            errors.append("spawn_agent requires an explicit user request for subagents, delegation, or parallel agent work")
        agent_type = arguments.get("agent_type")
        if agent_type is not None and agent_type not in ALLOWED_SPAWN_AGENT_TYPES:
            errors.append("spawn_agent agent_type must be one of: default, explorer, worker")
    return errors


def has_prior_external_url_shell_call(request_body: JsonObject) -> bool:
    input_items = request_body.get("input")
    if not isinstance(input_items, list):
        return False
    for item in input_items:
        if not isinstance(item, dict) or item.get("type") not in {"function_call", "custom_tool_call"}:
            continue
        if item.get("name") == "shell" and shell_arguments_contain_external_url(parse_function_call_arguments(item)):
            return True
    return False


def shell_arguments_contain_external_url(arguments: JsonObject) -> bool:
    try:
        text = json.dumps(arguments, ensure_ascii=True, default=str)
    except TypeError:
        text = repr(arguments)
    return bool(re.search(r"https?://", text, re.IGNORECASE))


def should_block_artifact_delay_shell_call(arguments: JsonObject, request_body: JsonObject) -> bool:
    if not request_requires_index_artifact(request_body):
        return False
    if has_prior_artifact_write_call(request_body):
        return False
    if not has_prior_web_or_policy_failure(request_body):
        return False
    script = shell_script_text(arguments)
    if not script:
        return False
    if re.search(r"\b(set-content|out-file|writealltext|appendalltext|new-item)\b", script, re.IGNORECASE):
        return False
    return bool(re.search(r"\b(get-childitem|dir|ls|test-path|get-content|measure-object)\b", script, re.IGNORECASE))


def request_requires_index_artifact(request_body: JsonObject) -> bool:
    text = all_user_text(request_body).lower()
    return "index.html" in text and bool(re.search(r"\b(build|create|write|contained|single)\b", text))


def has_prior_artifact_write_call(request_body: JsonObject) -> bool:
    input_items = request_body.get("input")
    if not isinstance(input_items, list):
        return False
    for item in input_items:
        if not isinstance(item, dict) or item.get("type") not in {"function_call", "custom_tool_call"}:
            continue
        if item.get("name") != "shell":
            continue
        script = shell_script_text(parse_function_call_arguments(item))
        if "index.html" in script.lower() and re.search(
            r"\b(set-content|out-file|writealltext|appendalltext)\b", script, re.IGNORECASE
        ):
            return True
    return False


def has_prior_web_or_policy_failure(request_body: JsonObject) -> bool:
    input_items = request_body.get("input")
    if not isinstance(input_items, list):
        return False
    for item in input_items:
        if not isinstance(item, dict):
            continue
        text = flatten_input_item(item).lower()
        if any(
            marker in text
            for marker in (
                "open gate blocked",
                "unable to connect",
                "remote server",
                "do not retry",
                "web_fetch",
                "external url inspection",
            )
        ):
            return True
    return False


def shell_script_text(arguments: JsonObject) -> str:
    command = arguments.get("command")
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        return " ".join(part for part in command if isinstance(part, str))
    return ""


def blocking_command_quality_errors(call: ToolCall) -> list[str]:
    issues = command_quality_error_issues(call)
    errors: list[str] = []
    for issue in issues:
        issue_name = issue.get("issue") or "command_quality"
        message = issue.get("message") or "The tool call has an unrepaired command-quality issue."
        errors.append(f"Command quality issue {issue_name}: {message}")
    return errors


def quarantine_command_quality_tool_call(call: ToolCall, tools: list[JsonObject]) -> tuple[ToolCall, JsonObject | None]:
    if call.name != "shell":
        return call, None
    issues = command_quality_error_issues(call)
    if not issues:
        return call, None
    issue_names = dedupe_keep_order([str(issue.get("issue")) for issue in issues if issue.get("issue")])
    diagnostic = command_quality_diagnostic_text(issue_names)
    quarantined = diagnostic_tool_call(
        diagnostic,
        tools,
        source=call.source,
        raw=call.raw,
        shell_arguments=call.arguments,
    )
    if quarantined is None:
        return call, None
    return quarantined, {
        "source": call.source,
        "tool": call.name,
        "before": call.arguments,
        "after": quarantined.arguments,
        "quarantined_command_quality_issues": issues,
    }


def command_quality_error_issues(call: ToolCall) -> list[JsonObject]:
    return [issue for issue in inspect_tool_calls([build_function_call_item(call)]) if issue.get("severity") == "error"]


def command_quality_diagnostic_text(issue_names: list[str]) -> str:
    issue_text = ", ".join(issue_names[:4]) or "command_quality"
    if "unbounded_web_fetch" in issue_names or "powershell_curl_unix_flags" in issue_names:
        return (
            f"Open Gate blocked an invalid shell command ({issue_text}). "
            "Do not retry that route; proceed from the prompt and create the requested artifact directly."
        )
    return (
        f"Open Gate blocked an invalid shell command ({issue_text}). "
        "Continue with a smaller valid structured tool call."
    )


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def has_explicit_subagent_intent(request_body: JsonObject) -> bool:
    return bool(SUBAGENT_INTENT_RE.search(all_user_text(request_body)))


def should_promote_tool_calls(request_body: JsonObject) -> bool:
    tool_choice = request_body.get("tool_choice", "auto")
    if tool_choice == "none":
        return False
    user_text = latest_user_text(request_body).lower()
    return not any(phrase in user_text for phrase in NEGATIVE_TOOL_INTENT)


def promotion_block_reason(request_body: JsonObject, existing_calls: list[JsonObject], candidates: list[ToolCall]) -> str | None:
    if not candidates:
        return None
    if existing_calls:
        return "existing_structured_calls"
    if not should_promote_tool_calls(request_body):
        return "negative_tool_intent"
    return None


def latest_user_text(request_body: JsonObject) -> str:
    input_value = request_body.get("input")
    if isinstance(input_value, str):
        return input_value
    if not isinstance(input_value, list):
        return ""
    for item in reversed(input_value):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        return flatten_content(item.get("content"))
    return ""


def all_user_text(request_body: JsonObject) -> str:
    input_value = request_body.get("input")
    if isinstance(input_value, str):
        return input_value
    if not isinstance(input_value, list):
        return ""
    texts: list[str] = []
    for item in input_value:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        texts.append(flatten_content(item.get("content")))
    return "\n".join(texts)


def flatten_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten_content(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        return "\n".join(flatten_content(item) for item in value.values())
    return ""


def is_empty_message(item: JsonObject) -> bool:
    if item.get("type") != "message":
        return False
    content = item.get("content")
    if not isinstance(content, list):
        return True
    for part in content:
        if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip():
            return False
    return True


def build_function_call_item(call: ToolCall) -> JsonObject:
    call_id = f"call_og_{uuid.uuid4().hex}"
    return {
        "id": f"fc_og_{uuid.uuid4().hex}",
        "type": "function_call",
        "status": "completed",
        "call_id": call_id,
        "name": call.name,
        "arguments": json.dumps(call.arguments, ensure_ascii=True, separators=(",", ":")),
    }


def build_proxy_error_response(request_body: JsonObject, upstream_status: int, upstream_response: JsonObject) -> JsonObject:
    upstream_error = upstream_response.get("error", upstream_response)
    message = "Open Gate upstream request failed"
    if isinstance(upstream_error, dict) and isinstance(upstream_error.get("message"), str):
        message = upstream_error["message"]
    return {
        "id": f"resp_og_error_{uuid.uuid4().hex}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": request_body.get("model"),
        "error": None,
        "output": [
            {
                "id": f"msg_og_error_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            f"Open Gate upstream error {upstream_status}: {message}. "
                            "Do not retry the same route; continue with a smaller, more direct action."
                        ),
                        "annotations": [],
                    }
                ],
            }
        ],
    }
