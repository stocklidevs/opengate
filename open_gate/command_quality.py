from __future__ import annotations

from copy import deepcopy
import json
import re
import shlex
from typing import Any


JsonObject = dict[str, Any]

POWERSHELL_COMMAND_FLAGS = {"-command", "-c", "/command", "/c"}
POWERSHELL_EXE_RE = re.compile(r"(?:^|[\\/])(?:powershell|pwsh)(?:\.exe)?$", re.IGNORECASE)


def inspect_tool_calls(calls: list[Any]) -> list[JsonObject]:
    issues: list[JsonObject] = []
    for call in calls:
        name = call_name(call)
        arguments = call_arguments(call)
        if name == "shell":
            issues.extend(inspect_shell_arguments(arguments, source=call_source(call)))
    return issues


def inspect_shell_arguments(arguments: JsonObject, source: str = "") -> list[JsonObject]:
    command = arguments.get("command")
    if command is None:
        return [
            {
                "tool": "shell",
                "issue": "missing_command",
                "severity": "error",
                "source": source,
                "message": "The shell call has no command argument.",
            }
        ]

    if isinstance(command, str):
        repaired = ["powershell.exe", "-Command", command]
        nested = repair_shell_command_argument(repaired)
        return [
            {
                "tool": "shell",
                "issue": "string_command",
                "severity": "warning",
                "source": source,
                "repairable": True,
                "command": command,
                "repaired_command": nested or repaired,
                "message": "The shell command should be a CreateProcessW-style argument array.",
            }
        ]

    if not isinstance(command, list):
        return [
            {
                "tool": "shell",
                "issue": "invalid_command_type",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "The shell command is neither a string nor an array.",
            }
        ]

    issues: list[JsonObject] = []
    if not command:
        issues.append(
            {
                "tool": "shell",
                "issue": "empty_command",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "The shell command array is empty.",
            }
        )

    if any(not isinstance(part, str) for part in command):
        issues.append(
            {
                "tool": "shell",
                "issue": "non_string_command_part",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "Every shell command array item must be a string.",
            }
        )
        return issues

    repaired = repair_shell_command_argument(command)
    if repaired is not None:
        issues.append(
            {
                "tool": "shell",
                "issue": "nested_powershell",
                "severity": "warning",
                "source": source,
                "repairable": True,
                "command": command,
                "repaired_command": repaired,
                "message": "The shell command wraps powershell.exe inside an outer powershell.exe -Command.",
            }
        )
    return issues


def repair_shell_arguments(arguments: JsonObject) -> JsonObject | None:
    command = arguments.get("command")
    repaired_command = repair_shell_command_argument(command)
    if repaired_command is None:
        return None
    repaired = deepcopy(arguments)
    repaired["command"] = repaired_command
    return repaired


def repair_shell_command_argument(command: Any) -> list[str] | None:
    if isinstance(command, str):
        return None
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return None

    nested_from_array = collapse_nested_powershell_array(command)
    if nested_from_array is not None:
        return nested_from_array

    if not is_powershell_command_vector(command) or len(command) < 3:
        return None
    inner_script = extract_nested_powershell_script(command[2])
    if inner_script is None:
        return None
    return [*command[:2], inner_script, *command[3:]]


def collapse_nested_powershell_array(command: list[str]) -> list[str] | None:
    if not is_powershell_command_vector(command) or len(command) < 5:
        return None
    nested = command[2:]
    if not is_powershell_command_vector(nested):
        return None
    return [*command[:2], " ".join(nested[2:]).strip()]


def is_powershell_command_vector(command: list[str]) -> bool:
    if len(command) < 2:
        return False
    return is_powershell_executable(command[0]) and command[1].lower() in POWERSHELL_COMMAND_FLAGS


def extract_nested_powershell_script(value: str) -> str | None:
    tokens = split_command_line(value)
    if len(tokens) >= 3 and is_powershell_executable(tokens[0]):
        command_index = first_command_flag_index(tokens)
        if command_index is not None and command_index + 1 < len(tokens):
            return " ".join(tokens[command_index + 1 :]).strip()

    match = re.match(
        r"^\s*(?:&\s*)?(?:\"(?P<double>[^\"]+)\"|'(?P<single>[^']+)'|(?P<bare>\S+))\s+(?P<rest>.*)$",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    exe = match.group("double") or match.group("single") or match.group("bare")
    if not is_powershell_executable(exe):
        return None
    rest = match.group("rest").strip()
    for flag in POWERSHELL_COMMAND_FLAGS:
        pattern = re.compile(rf"(?i)(?:^|\s){re.escape(flag)}(?:\s+|:)(?P<script>.*)$", re.DOTALL)
        flag_match = pattern.search(rest)
        if flag_match:
            return strip_outer_quotes(flag_match.group("script").strip())
    return None


def split_command_line(value: str) -> list[str]:
    for posix in (True, False):
        try:
            return [strip_outer_quotes(item) for item in shlex.split(value, posix=posix)]
        except ValueError:
            continue
    return []


def first_command_flag_index(tokens: list[str]) -> int | None:
    for index, token in enumerate(tokens[1:], start=1):
        if token.lower() in POWERSHELL_COMMAND_FLAGS:
            return index
    return None


def is_powershell_executable(value: str) -> bool:
    return bool(POWERSHELL_EXE_RE.search(value.strip().strip("\"'")))


def strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def call_name(call: Any) -> str | None:
    if isinstance(call, dict):
        name = call.get("name")
        return name if isinstance(name, str) else None
    name = getattr(call, "name", None)
    return name if isinstance(name, str) else None


def call_source(call: Any) -> str:
    if isinstance(call, dict):
        source = call.get("source")
        return source if isinstance(source, str) else ""
    source = getattr(call, "source", "")
    return source if isinstance(source, str) else ""


def call_arguments(call: Any) -> JsonObject:
    if isinstance(call, dict):
        arguments = call.get("arguments", {})
    else:
        arguments = getattr(call, "arguments", {})
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {"value": arguments}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": arguments}
