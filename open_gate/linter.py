from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from html import unescape
from typing import Any


JsonObject = dict[str, Any]


@dataclass
class ToolSpec:
    name: str
    parameters: JsonObject = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    arguments: JsonObject
    source: str
    span: tuple[int, int]
    raw: str
    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> JsonObject:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "source": self.source,
            "span": list(self.span),
            "raw": self.raw,
            "valid": self.valid,
            "errors": self.errors,
        }


@dataclass
class LeakReport:
    input_chars: int
    cleaned_text: str
    tool_calls: list[ToolCall]
    leaks: list[str]
    errors: list[str]

    def to_json(self) -> JsonObject:
        return {
            "input_chars": self.input_chars,
            "cleaned_text": self.cleaned_text,
            "tool_calls": [call.to_json() for call in self.tool_calls],
            "leaks": self.leaks,
            "errors": self.errors,
        }


TOOL_CALL_TAG = r"t\s*o\s*o\s*l\s*_\s*c\s*a\s*l\s*l"
TOOL_CALLS_TAG = r"t\s*o\s*o\s*l\s*_\s*c\s*a\s*l\s*l\s*s"
ARG_KEY_TAG = r"a\s*r\s*g\s*_\s*k\s*e\s*y"
ARG_VALUE_TAG = r"a\s*r\s*g\s*_\s*v\s*a\s*l\s*u\s*e"
TOOL_TAG_RE = re.compile(rf"<\s*{TOOL_CALL_TAG}\s*>\s*(?P<body>.*?)\s*</\s*{TOOL_CALL_TAG}\s*>", re.IGNORECASE | re.DOTALL)
TOOL_CALLS_TAG_RE = re.compile(rf"<\s*{TOOL_CALLS_TAG}\s*>\s*(?P<body>.*?)\s*</\s*{TOOL_CALLS_TAG}\s*>", re.IGNORECASE | re.DOTALL)
GLM_ARG_RE = re.compile(
    rf"<\s*{ARG_KEY_TAG}\s*>\s*(?P<key>.*?)\s*</\s*{ARG_KEY_TAG}\s*>\s*<\s*{ARG_VALUE_TAG}\s*>\s*(?P<value>.*?)\s*</\s*{ARG_VALUE_TAG}\s*>",
    re.IGNORECASE | re.DOTALL,
)
GLM_NAME_RE = re.compile(r"<name>\s*(?P<name>[A-Za-z0-9_.:-]+)\s*</name>", re.IGNORECASE | re.DOTALL)
FUNCTION_TAG_RE = re.compile(
    r"<function=(?P<name>[A-Za-z0-9_.:-]+)>\s*(?P<body>.*?)\s*</function>",
    re.IGNORECASE | re.DOTALL,
)
RESPONSE_TAG_RE = re.compile(
    r"<response\b(?P<attrs>[^>]*)>\s*(?P<body>.*?)\s*</response>",
    re.IGNORECASE | re.DOTALL,
)
RESPONSE_TAG_LITERAL_RE = re.compile(r"</?response\b[^>]*>", re.IGNORECASE)
RECIPIENT_RE = re.compile(r"recipient_name\s*=\s*(?P<name>[A-Za-z0-9_.:-]+)", re.IGNORECASE)
BARE_RECIPIENT_RE = re.compile(
    r"^\s*recipient_name\s*=\s*(?P<name>[A-Za-z0-9_.:-]+)\s*(?P<body>.*)$",
    re.IGNORECASE | re.DOTALL,
)
FENCED_JSON_RE = re.compile(r"```(?:json|tool_code|tool_call)?\s*(?P<body>.*?)\s*```", re.IGNORECASE | re.DOTALL)
PY_CALL_RE = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)\s*\(")
RECIPIENT_ASSIGN_RE = re.compile(r"\brecipient_name\s*=\s*functions\.[A-Za-z0-9_.:-]+\b", re.IGNORECASE)
TO_FUNCTIONS_ASSIGN_RE = re.compile(r"\bto\s*=\s*functions\.[A-Za-z0-9_.:-]+\b", re.IGNORECASE)
FUNCTION_NAMESPACE_CALL_RE = re.compile(r"\b(?:functions|tools)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.IGNORECASE)
SUSPICIOUS_PATTERNS = {
    "tool_call_tag": re.compile(r"</?tool_calls?>", re.IGNORECASE),
    "function_tag": re.compile(r"<function=", re.IGNORECASE),
    "responses_recipient": re.compile(r"\brecipient_name\b|\bto=functions\.", re.IGNORECASE),
    "tool_namespace": re.compile(r"\b(?:functions|tools)\.[A-Za-z_][A-Za-z0-9_]*\s*\(", re.IGNORECASE),
}


def load_tool_specs(raw_tools: list[JsonObject] | JsonObject | None) -> dict[str, ToolSpec]:
    if raw_tools is None:
        return {}
    if isinstance(raw_tools, dict):
        raw_tools = raw_tools.get("tools", [])

    specs: dict[str, ToolSpec] = {}
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue

        name = None
        parameters: JsonObject = {}
        if tool.get("type") == "function":
            name = tool.get("name")
            parameters = tool.get("parameters") or {}
            function = tool.get("function")
            if isinstance(function, dict):
                name = name or function.get("name")
                parameters = parameters or function.get("parameters") or {}
        elif "name" in tool:
            name = tool.get("name")
            parameters = tool.get("parameters") or {}

        if isinstance(name, str) and name:
            specs[name] = ToolSpec(name=name, parameters=parameters)

    return specs


def analyze_text(text: str, tools: list[JsonObject] | JsonObject | None = None) -> LeakReport:
    specs = load_tool_specs(tools)
    calls: list[ToolCall] = []
    errors: list[str] = []
    suspicious_spans: list[tuple[int, int]] = []

    for match in TOOL_TAG_RE.finditer(text):
        suspicious_spans.append(match.span())
        parsed_calls = _calls_from_jsonish(match.group("body"), "xml_tool_call", match.span())
        if not parsed_calls:
            parsed_calls = _calls_from_glm_tool_call(match.group("body"), match.span())
        calls.extend(parsed_calls)

    for match in TOOL_CALLS_TAG_RE.finditer(text):
        suspicious_spans.append(match.span())
        calls.extend(_calls_from_jsonish(match.group("body"), "xml_tool_calls", match.span()))

    for match in FUNCTION_TAG_RE.finditer(text):
        suspicious_spans.append(match.span())
        args = _json_loads_relaxed(match.group("body"))
        if isinstance(args, dict):
            calls.append(ToolCall(match.group("name"), args, "xml_function", match.span(), match.group(0)))
        else:
            errors.append(f"Could not parse function tag arguments at {match.start()}.")

    for match in RESPONSE_TAG_RE.finditer(text):
        recipient = RECIPIENT_RE.search(match.group("attrs"))
        if recipient:
            suspicious_spans.append(match.span())
            name = recipient.group("name")
            if name.startswith("functions."):
                name = name.split(".", 1)[1]
            args = _response_body_to_args(match.group("body"))
            calls.append(ToolCall(name, args, "response_recipient_tag", match.span(), match.group(0)))

    bare_recipient = BARE_RECIPIENT_RE.match(text)
    if bare_recipient:
        suspicious_spans.append(bare_recipient.span())
        name = bare_recipient.group("name")
        if name.startswith("functions."):
            name = name.split(".", 1)[1]
        args = _response_body_to_args(bare_recipient.group("body"))
        calls.append(ToolCall(name, args, "bare_response_recipient", bare_recipient.span(), bare_recipient.group(0)))

    for match in FENCED_JSON_RE.finditer(text):
        parsed_calls = _calls_from_jsonish(match.group("body"), "fenced_json", match.span())
        if parsed_calls or _contains_raw_tool_syntax(match.group("body")):
            suspicious_spans.append(match.span())
        calls.extend(parsed_calls)

    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        calls.extend(_calls_from_jsonish(stripped, "raw_json", (0, len(text))))

    calls.extend(_extract_pythonic_calls(text))
    calls = _dedupe_calls(calls)

    for call in calls:
        _validate_call(call, specs)

    cleaned = _remove_spans(text, [*suspicious_spans, *[call.span for call in calls]])
    cleaned = _sanitize_residual_tool_syntax(cleaned).strip()
    leaks = [
        name
        for name, pattern in SUSPICIOUS_PATTERNS.items()
        if pattern.search(text)
    ]
    if calls and "parsed_tool_call" not in leaks:
        leaks.append("parsed_tool_call")

    return LeakReport(
        input_chars=len(text),
        cleaned_text=cleaned,
        tool_calls=calls,
        leaks=leaks,
        errors=errors,
    )


def _calls_from_jsonish(payload: str, source: str, outer_span: tuple[int, int]) -> list[ToolCall]:
    parsed = _json_loads_relaxed(payload)
    if parsed is None:
        return []
    calls: list[ToolCall] = []
    for item in _iter_tool_call_objects(parsed):
        name, args = _normalise_call_object(item)
        if name:
            raw = json.dumps(item, ensure_ascii=True, sort_keys=True)
            calls.append(ToolCall(name=name, arguments=args, source=source, span=outer_span, raw=raw))
    return calls


def _contains_raw_tool_syntax(payload: str) -> bool:
    return any(pattern.search(payload) for pattern in SUSPICIOUS_PATTERNS.values())


def _sanitize_residual_tool_syntax(text: str) -> str:
    cleaned = RESPONSE_TAG_LITERAL_RE.sub("", text)
    cleaned = RECIPIENT_ASSIGN_RE.sub("", cleaned)
    cleaned = TO_FUNCTIONS_ASSIGN_RE.sub("", cleaned)
    cleaned = re.sub(r"\brecipient_name\b", "recipient name", cleaned, flags=re.IGNORECASE)
    cleaned = FUNCTION_NAMESPACE_CALL_RE.sub(r"\1(", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def _calls_from_glm_tool_call(payload: str, outer_span: tuple[int, int]) -> list[ToolCall]:
    payload = payload.strip()
    first_arg = GLM_ARG_RE.search(payload)
    if not first_arg:
        return []

    name_match = GLM_NAME_RE.search(payload)
    if name_match:
        name = name_match.group("name").strip()
    else:
        name = re.sub(r"<.*?>", "", payload[: first_arg.start()]).strip()

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", name):
        return []
    if name.startswith("functions."):
        name = name.split(".", 1)[1]

    args: JsonObject = {}
    for arg_match in GLM_ARG_RE.finditer(payload):
        key = unescape(re.sub(r"<.*?>", "", arg_match.group("key")).strip())
        if not key:
            continue
        raw_value = unescape(arg_match.group("value").strip())
        args[key] = _parse_glm_arg_value(raw_value)

    if not args:
        return []
    return [ToolCall(name=name, arguments=args, source="glm_tool_call_tag", span=outer_span, raw=payload)]


def _parse_glm_arg_value(value: str) -> Any:
    parsed = _json_loads_relaxed(value)
    if parsed is not None:
        return parsed

    stripped = value.strip()
    if "\n" in stripped:
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if len(lines) > 1:
            return "\n".join(lines)
    return stripped


def _iter_tool_call_objects(value: Any) -> list[JsonObject]:
    if isinstance(value, list):
        out: list[JsonObject] = []
        for item in value:
            out.extend(_iter_tool_call_objects(item))
        return out
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("tool_calls"), list):
        return _iter_tool_call_objects(value["tool_calls"])
    if isinstance(value.get("calls"), list):
        return _iter_tool_call_objects(value["calls"])
    if isinstance(value.get("function"), dict):
        return [value]
    if any(key in value for key in ("name", "tool", "tool_name", "recipient_name")):
        return [value]
    return []


def _normalise_call_object(value: JsonObject) -> tuple[str | None, JsonObject]:
    function = value.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        args = function.get("arguments", {})
    else:
        name = value.get("name") or value.get("tool") or value.get("tool_name") or value.get("recipient_name")
        if any(key in value for key in ("arguments", "parameters", "args")):
            args = value.get("arguments", value.get("parameters", value.get("args", {})))
        else:
            args = {
                key: item
                for key, item in value.items()
                if key not in {"name", "tool", "tool_name", "recipient_name", "type", "id", "call_id"}
            }

    if not isinstance(name, str) or not name:
        return None, {}
    if name.startswith("functions."):
        name = name.split(".", 1)[1]
    if isinstance(args, str):
        loaded = _json_loads_relaxed(args)
        args = loaded if isinstance(loaded, dict) else {"value": args}
    if args is None:
        args = {}
    if not isinstance(args, dict):
        args = {"value": args}
    return name, args


def _extract_pythonic_calls(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    decoder = json.JSONDecoder()
    for match in PY_CALL_RE.finditer(text):
        name = match.group("name")
        start = match.end()
        while start < len(text) and text[start].isspace():
            start += 1
        if start >= len(text) or text[start] != "{":
            continue
        try:
            args, offset = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        end = start + offset
        while end < len(text) and text[end].isspace():
            end += 1
        if end >= len(text) or text[end] != ")":
            continue
        if name.startswith("functions."):
            name = name.split(".", 1)[1]
        if isinstance(args, dict):
            raw = text[match.start() : end + 1]
            calls.append(ToolCall(name=name, arguments=args, source="pythonic_call", span=(match.start(), end + 1), raw=raw))
    return calls


def _json_loads_relaxed(payload: str) -> Any:
    payload = payload.strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    if "\n" in payload:
        values = []
        for line in payload.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError:
                return None
        return values
    return None


def _response_body_to_args(payload: str) -> JsonObject:
    parsed = _json_loads_relaxed(payload)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {"command": parsed}
    return {"value": payload.strip()}


def _validate_call(call: ToolCall, specs: dict[str, ToolSpec]) -> None:
    if specs and call.name not in specs:
        call.valid = False
        call.errors.append(f"Unknown tool: {call.name}")
        return

    spec = specs.get(call.name)
    if not spec:
        return
    schema = spec.parameters or {}
    if schema.get("type") not in (None, "object"):
        return

    required = schema.get("required") or []
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in call.arguments:
                call.valid = False
                call.errors.append(f"Missing required argument: {key}")

    properties = schema.get("properties") or {}
    if isinstance(properties, dict):
        for key, value in call.arguments.items():
            expected = properties.get(key)
            if isinstance(expected, dict):
                type_name = expected.get("type")
                if type_name and not _matches_json_type(value, type_name):
                    call.valid = False
                    call.errors.append(f"Argument {key} expected {type_name}, got {type(value).__name__}")


def _matches_json_type(value: Any, type_name: str | list[str]) -> bool:
    if isinstance(type_name, list):
        return any(_matches_json_type(value, item) for item in type_name)
    checks = {
        "string": lambda v: isinstance(v, str),
        "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
        "null": lambda v: v is None,
    }
    checker = checks.get(type_name)
    return True if checker is None else checker(value)


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return text
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    pieces: list[str] = []
    last = 0
    for start, end in merged:
        pieces.append(text[last:start])
        last = end
    pieces.append(text[last:])
    return "".join(pieces)


def _dedupe_calls(calls: list[ToolCall]) -> list[ToolCall]:
    seen: set[tuple[int, int, str]] = set()
    unique: list[ToolCall] = []
    for call in calls:
        key = (call.span[0], call.span[1], call.name)
        if key not in seen:
            seen.add(key)
            unique.append(call)
    return unique
