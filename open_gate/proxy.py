from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .command_quality import repair_shell_arguments
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
    "sample",
    "example",
)


@dataclass
class ProxyResult:
    upstream_request: JsonObject
    upstream_status: int
    upstream_response: JsonObject
    normalized_response: JsonObject
    returned_response: JsonObject
    normalization: JsonObject


def forward_responses_request(
    request_body: JsonObject,
    upstream_base_url: str,
    api_key: str,
    timeout: float,
    normalization_mode: str = "repair",
) -> ProxyResult:
    if normalization_mode not in {"repair", "observe"}:
        raise ValueError(f"Unsupported normalization mode: {normalization_mode}")
    upstream_request = deepcopy(request_body)
    requested_stream = bool(upstream_request.get("stream"))
    upstream_request["stream"] = False
    status, upstream_response = post_json(upstream_base_url, "/responses", upstream_request, api_key, timeout)
    normalized_response, normalization = normalize_responses_response(upstream_response, request_body)
    returned_response = deepcopy(normalized_response if normalization_mode == "repair" else upstream_response)
    normalization["mode"] = normalization_mode
    normalization["returned"] = "normalized_response" if normalization_mode == "repair" else "upstream_response"
    if requested_stream:
        returned_response["streamed_by_open_gate"] = True
    return ProxyResult(
        upstream_request=upstream_request,
        upstream_status=status,
        upstream_response=upstream_response,
        normalized_response=normalized_response,
        returned_response=returned_response,
        normalization=normalization,
    )


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


def normalize_responses_response(response: JsonObject, original_request: JsonObject) -> tuple[JsonObject, JsonObject]:
    normalized = deepcopy(response)
    tools = original_request.get("tools") if isinstance(original_request.get("tools"), list) else []
    repairs = repair_structured_calls(normalized, tools)
    suppressed = suppress_structured_calls_if_blocked(normalized, original_request)
    text_items = collect_message_text_items(normalized)
    existing_calls = collect_existing_function_calls(normalized)
    promoted: list[ToolCall] = []
    stripped = 0
    invalid_calls: list[JsonObject] = []

    for item, content_part, text in text_items:
        report = analyze_text(text, tools)
        if report.tool_calls or report.leaks:
            stripped += 1
            content_part["text"] = report.cleaned_text
        for call in report.tool_calls:
            if call.valid:
                promoted.append(call)
            else:
                invalid_calls.append(call.to_json())

    should_promote = bool(promoted and not existing_calls and should_promote_tool_calls(original_request))
    if should_promote:
        output = normalized.setdefault("output", [])
        output[:] = [item for item in output if not is_empty_message(item)]
        for call in promoted:
            output.append(build_function_call_item(call))

    normalization = {
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "suppressed_structured_calls": suppressed,
        "structured_argument_repairs": repairs,
        "stripped_text_items": stripped,
        "existing_structured_calls": len(existing_calls),
        "promoted_tool_calls": [call.to_json() for call in promoted] if should_promote else [],
        "promotion_candidates": [call.to_json() for call in promoted],
        "invalid_tool_calls": invalid_calls,
        "promotion_blocked": bool(promoted and not should_promote),
        "promotion_block_reason": promotion_block_reason(original_request, existing_calls, promoted),
    }
    return normalized, normalization


def collect_message_text_items(response: JsonObject) -> list[tuple[JsonObject, JsonObject, str]]:
    out: list[tuple[JsonObject, JsonObject, str]] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("output_text", "text") and isinstance(part.get("text"), str):
                out.append((item, part, part["text"]))
    return out


def collect_existing_function_calls(response: JsonObject) -> list[JsonObject]:
    calls: list[JsonObject] = []
    for item in response.get("output") or []:
        if isinstance(item, dict) and item.get("type") in ("function_call", "custom_tool_call"):
            calls.append(item)
    return calls


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
    return {
        "id": f"resp_og_error_{uuid.uuid4().hex}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "failed",
        "model": request_body.get("model"),
        "error": {
            "message": "Upstream request failed",
            "type": "upstream_error",
            "code": upstream_status,
            "upstream": upstream_response.get("error", upstream_response),
        },
        "output": [],
    }
