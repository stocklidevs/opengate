from __future__ import annotations

from copy import deepcopy
import json
import re
import shlex
from typing import Any


JsonObject = dict[str, Any]

POWERSHELL_COMMAND_FLAGS = {"-command", "-c", "/command", "/c"}
POWERSHELL_EXE_RE = re.compile(r"(?:^|[\\/])(?:powershell|pwsh)(?:\.exe)?$", re.IGNORECASE)
WINDOWS_POWERSHELL_EXE_RE = re.compile(r"(?:^|[\\/])powershell(?:\.exe)?$", re.IGNORECASE)
IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def inspect_tool_calls(calls: list[Any]) -> list[JsonObject]:
    issues: list[JsonObject] = []
    for call in calls:
        name = call_name(call)
        arguments = call_arguments(call)
        if name == "shell":
            issues.extend(inspect_shell_arguments(arguments, source=call_source(call)))
        elif name == "view_image":
            issues.extend(inspect_view_image_arguments(arguments, source=call_source(call)))
        elif name == "read_mcp_resource":
            issues.extend(inspect_read_mcp_resource_arguments(arguments, source=call_source(call)))
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

    if is_powershell_command_vector(command) and len(command) >= 3:
        script = command[2]
        issues.extend(inspect_powershell_script(script, arguments, command, source))
    return issues


def inspect_powershell_script(script: str, arguments: JsonObject, command: list[str], source: str = "") -> list[JsonObject]:
    issues: list[JsonObject] = []
    if is_windows_powershell_executable(command[0]) and contains_powershell_chain_operator(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "windows_powershell_chain_operator",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "Windows PowerShell does not support the && chain operator; use ';', split commands, or run under pwsh.",
            }
        )

    if contains_bad_here_string_header(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "powershell_here_string_header",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "PowerShell here-string headers must be followed immediately by a real newline, not escaped `n text.",
            }
        )

    if contains_python_compound_one_liner(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "python_compound_statement_one_liner",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "Python compound statements such as async def/def/class cannot be safely packed after semicolons in python -c.",
            }
        )

    if contains_uv_run_playwright(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "uv_run_playwright_entrypoint",
                "severity": "warning",
                "source": source,
                "command": command,
                "message": "uv run playwright assumes the Playwright console script is already installed; python -m playwright or installing the package first is more reliable.",
            }
        )

    workdir = arguments.get("workdir")
    for target in relative_cd_targets(script):
        if isinstance(workdir, str) and path_last_segment(workdir).lower() == path_last_segment(target).lower():
            issues.append(
                {
                    "tool": "shell",
                    "issue": "nested_relative_cd",
                    "severity": "error",
                    "source": source,
                    "command": command,
                    "workdir": workdir,
                    "cd_target": target,
                    "message": "The command changes into the same relative directory already selected as workdir.",
                }
            )
        elif not isinstance(workdir, str) or not workdir:
            issues.append(
                {
                    "tool": "shell",
                    "issue": "relative_cd_without_workdir",
                    "severity": "warning",
                    "source": source,
                    "command": command,
                    "cd_target": target,
                    "message": "Prefer the shell tool's workdir argument over an inline relative cd command.",
                }
            )
    return issues


def inspect_view_image_arguments(arguments: JsonObject, source: str = "") -> list[JsonObject]:
    path = arguments.get("path")
    if path is None:
        return [
            {
                "tool": "view_image",
                "issue": "missing_path",
                "severity": "error",
                "source": source,
                "message": "The view_image call has no path argument.",
            }
        ]
    if not isinstance(path, str):
        return [
            {
                "tool": "view_image",
                "issue": "invalid_path_type",
                "severity": "error",
                "source": source,
                "path": path,
                "message": "The view_image path must be a string.",
            }
        ]
    if image_extension(path) not in IMAGE_EXTENSIONS:
        return [
            {
                "tool": "view_image",
                "issue": "view_image_non_image_path",
                "severity": "warning",
                "source": source,
                "path": path,
                "message": "view_image expects an image file path; this path has no known image extension.",
            }
        ]
    return []


def inspect_read_mcp_resource_arguments(arguments: JsonObject, source: str = "") -> list[JsonObject]:
    server = arguments.get("server")
    uri = arguments.get("uri")
    uri_text = uri if isinstance(uri, str) else ""
    server_text = server if isinstance(server, str) else ""
    if "skill" in server_text.lower() or ".codex/skills" in uri_text.lower().replace("\\", "/"):
        return [
            {
                "tool": "read_mcp_resource",
                "issue": "skill_file_as_mcp_resource",
                "severity": "warning",
                "source": source,
                "server": server,
                "uri": uri,
                "message": "Codex skills are local instruction files, not guaranteed MCP resources; use listed MCP resources only.",
            }
        ]
    return []


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
    inner_script = extract_json_array_powershell_script(command[2]) or extract_nested_powershell_script(command[2])
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


def extract_json_array_powershell_script(value: str) -> str | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or any(not isinstance(part, str) for part in parsed):
        return None
    if not is_powershell_command_vector(parsed) or len(parsed) < 3:
        return None
    return " ".join(parsed[2:]).strip()


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


def is_windows_powershell_executable(value: str) -> bool:
    return bool(WINDOWS_POWERSHELL_EXE_RE.search(value.strip().strip("\"'")))


def contains_powershell_chain_operator(script: str) -> bool:
    return bool(re.search(r"(?<!&)&&(?!&)", script))


def contains_bad_here_string_header(script: str) -> bool:
    return bool(re.search(r"@['\"]`n\S", script))


def contains_python_compound_one_liner(script: str) -> bool:
    if not re.search(r"\b(?:python|python3|py)(?:\.exe)?\s+-c\b", script, re.IGNORECASE):
        return False
    return bool(re.search(r";\s*(?:async\s+def|def|class|for|while|if|with|try)\b", script))


def contains_uv_run_playwright(script: str) -> bool:
    return bool(re.search(r"\buv\s+run\s+playwright\b", script, re.IGNORECASE))


def relative_cd_targets(script: str) -> list[str]:
    targets: list[str] = []
    pattern = re.compile(r"(?:^|[;&|])\s*(?:cd|Set-Location)\s+(?P<target>\"[^\"]+\"|'[^']+'|[^;&|]+)", re.IGNORECASE)
    for match in pattern.finditer(script):
        target = strip_outer_quotes(match.group("target").strip())
        if is_relative_user_path(target):
            targets.append(target)
    return targets


def is_relative_user_path(value: str) -> bool:
    if not value or value in {".", ".."}:
        return False
    lowered = value.lower()
    if lowered.startswith(("-", "$", "~", "/", "\\")):
        return False
    if re.match(r"^[a-z]:", lowered):
        return False
    if value.startswith("."):
        return False
    return True


def path_last_segment(value: str) -> str:
    cleaned = strip_outer_quotes(value.rstrip("\\/"))
    if not cleaned:
        return ""
    return re.split(r"[\\/]", cleaned)[-1]


def image_extension(path: str) -> str:
    last = path_last_segment(path)
    if "." not in last:
        return ""
    return "." + last.rsplit(".", 1)[1].lower()


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
