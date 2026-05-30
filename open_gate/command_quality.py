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
SHELL_EXE_RE = re.compile(r"(?:^|[\\/])(?:powershell|pwsh|cmd)(?:\.exe)?$", re.IGNORECASE)
SHELL_METADATA_KEYS = {"justification", "prefix_rule", "sandbox_permissions"}
POWERSHELL_CMDLET_VERBS = {
    "add",
    "clear",
    "compare",
    "convert",
    "convertfrom",
    "convertto",
    "copy",
    "debug",
    "disable",
    "enable",
    "enter",
    "exit",
    "export",
    "find",
    "format",
    "get",
    "group",
    "import",
    "invoke",
    "join",
    "measure",
    "move",
    "new",
    "out",
    "pop",
    "push",
    "read",
    "receive",
    "remove",
    "rename",
    "resolve",
    "restart",
    "resume",
    "select",
    "send",
    "set",
    "show",
    "sort",
    "split",
    "start",
    "stop",
    "suspend",
    "tee",
    "test",
    "trace",
    "wait",
    "where",
    "write",
}
POWERSHELL_ALIAS_COMMANDS = {
    "cat",
    "cd",
    "chdir",
    "cls",
    "copy",
    "cp",
    "del",
    "dir",
    "echo",
    "erase",
    "gc",
    "gci",
    "gi",
    "ls",
    "md",
    "measure",
    "mi",
    "move",
    "mv",
    "ni",
    "pwd",
    "rd",
    "ren",
    "rm",
    "rmdir",
    "sc",
    "select",
    "sls",
    "sort",
    "type",
    "where",
}
POWERSHELL_OPERATOR_TOKENS = {"|", ">", ">>", "2>", "2>>", "2>&1", "<", ";", "&&", "||"}
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
ARTIFACT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".cxx",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".htm",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".md",
    ".mjs",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
EMPTY_ARTIFACT_WRITE_DIAGNOSTIC = (
    "Open Gate blocked an empty file write. Write the complete requested artifact content in one valid tool call "
    "instead of truncating or creating an empty placeholder first."
)


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
        repaired = parse_shell_array_string(command) or ["powershell.exe", "-Command", command]
        nested = repair_shell_command_argument(repaired)
        issues = [
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
        effective = nested or repaired
        if looks_like_executable_only_shell_command(effective):
            issues.append(executable_only_shell_command_issue(effective, arguments, source))
        return issues

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

    if len(command) == 1 and looks_like_embedded_json_command_array_item(command[0]):
        issues.append(
            {
                "tool": "shell",
                "issue": "malformed_embedded_json_command_array",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "The shell command array contains escaped JSON fragments instead of executable arguments.",
            }
        )

    if looks_like_executable_only_shell_command(command):
        issues.append(executable_only_shell_command_issue(command, arguments, source))

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

    repaired = repair_split_powershell_command(command)
    if repaired is not None:
        issues.append(
            {
                "tool": "shell",
                "issue": "split_powershell_command",
                "severity": "warning",
                "source": source,
                "repairable": True,
                "command": command,
                "repaired_command": repaired,
                "message": "PowerShell -Command should receive one script string; extra array items should be joined into that script.",
            }
        )

    repaired = repair_direct_powershell_cmdlet(command)
    if repaired is not None:
        issues.append(
            {
                "tool": "shell",
                "issue": "direct_powershell_cmdlet",
                "severity": "warning",
                "source": source,
                "repairable": True,
                "command": command,
                "repaired_command": repaired,
                "message": "PowerShell cmdlets and aliases such as dir, Get-ChildItem, Set-Content, or Write-Host must run through powershell.exe -Command.",
            }
        )

    effective_command = repair_direct_powershell_cmdlet(command) or repair_split_powershell_command(command) or command
    if is_powershell_command_vector(effective_command) and len(effective_command) >= 3:
        script = effective_command[2]
        issues.extend(inspect_powershell_script(script, arguments, effective_command, source))
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

    if contains_bash_heredoc(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "bash_heredoc_in_powershell",
                "severity": "error",
                "source": source,
                "repairable": True,
                "command": command,
                "message": "Windows PowerShell does not support Bash heredoc syntax such as cat > file << EOF.",
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

    if contains_malformed_powershell_here_string(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "malformed_powershell_here_string",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "The command contains malformed PowerShell here-string syntax for file content.",
            }
        )

    if convert_bare_here_string_to_set_content(script) is not None:
        issues.append(
            {
                "tool": "shell",
                "issue": "bare_here_string_file_write",
                "severity": "error",
                "source": source,
                "repairable": True,
                "command": command,
                "message": "The command contains file content in a PowerShell here-string but omitted the Set-Content cmdlet.",
            }
        )

    if looks_like_malformed_json_array_command(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "malformed_json_array_command",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "The PowerShell script looks like a malformed JSON command array instead of an executable script.",
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

    if contains_html_echo_without_file_write(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "html_echo_without_file_write",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "The command appears to print an HTML document to stdout instead of writing the requested HTML file.",
            }
        )

    empty_write_targets = empty_artifact_write_targets(script)
    if empty_write_targets:
        issues.append(
            {
                "tool": "shell",
                "issue": "empty_artifact_write",
                "severity": "error",
                "source": source,
                "repairable": True,
                "command": command,
                "targets": empty_write_targets,
                "message": "The command creates or truncates a requested artifact to empty content instead of writing the finished file.",
            }
        )

    if contains_unbounded_web_fetch(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "unbounded_web_fetch",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "The command appears to fetch and print a whole web page; prefer bounded metadata or a small excerpt.",
            }
        )

    if contains_powershell_curl_unix_flags(script):
        issues.append(
            {
                "tool": "shell",
                "issue": "powershell_curl_unix_flags",
                "severity": "error",
                "source": source,
                "command": command,
                "message": "PowerShell aliases curl to Invoke-WebRequest; Unix curl flags such as -s, -m, or --head are unreliable here.",
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
    repaired = deepcopy(arguments)
    command = repaired.get("command")
    changed = False

    repaired_command = repair_shell_command_argument(command)
    if repaired_command is not None:
        repaired["command"] = repaired_command
        command = repaired_command
        changed = True

    repaired_command = repair_split_powershell_command(command)
    if repaired_command is not None:
        repaired["command"] = repaired_command
        command = repaired_command
        changed = True

    repaired_command = repair_direct_powershell_cmdlet(command)
    if repaired_command is not None:
        repaired["command"] = repaired_command
        command = repaired_command
        changed = True

    repaired_command = repair_bad_here_string_command(command)
    if repaired_command is not None:
        repaired["command"] = repaired_command
        changed = True
        command = repaired_command

    repaired_command = repair_bare_here_string_file_write_command(command)
    if repaired_command is not None:
        repaired["command"] = repaired_command
        changed = True
        command = repaired_command

    repaired_command = repair_bash_heredoc_command(command)
    if repaired_command is not None:
        repaired["command"] = repaired_command
        changed = True
        command = repaired_command

    repaired_command = repair_empty_artifact_write_command(command)
    if repaired_command is not None:
        repaired["command"] = repaired_command
        changed = True

    if not changed:
        return None
    return repaired


def repair_shell_command_argument(command: Any) -> list[str] | None:
    if isinstance(command, str):
        return parse_shell_array_string(command)
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


def repair_bad_here_string_command(command: Any) -> list[str] | None:
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return None
    if not is_powershell_command_vector(command) or len(command) < 3:
        return None
    script = command[2]
    if not contains_bad_here_string_header(script):
        return None
    repaired_script = script.replace("`r", "\r").replace("`n", "\n")
    if repaired_script == script:
        return None
    return [*command[:2], repaired_script, *command[3:]]


def repair_bare_here_string_file_write_command(command: Any) -> list[str] | None:
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return None
    if not is_powershell_command_vector(command) or len(command) < 3:
        return None
    repaired_script = convert_bare_here_string_to_set_content(command[2])
    if repaired_script is None:
        return None
    return [*command[:2], repaired_script, *command[3:]]


def repair_bash_heredoc_command(command: Any) -> list[str] | None:
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return None
    if not is_powershell_command_vector(command) or len(command) < 3:
        return None
    repaired_script = convert_bash_heredoc_to_powershell(command[2])
    if repaired_script is None:
        return None
    return [*command[:2], repaired_script, *command[3:]]


def repair_empty_artifact_write_command(command: Any) -> list[str] | None:
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return None
    if not is_powershell_command_vector(command) or len(command) < 3:
        return None
    if not empty_artifact_write_targets(command[2]):
        return None
    diagnostic = "Write-Output " + quote_powershell_token(EMPTY_ARTIFACT_WRITE_DIAGNOSTIC)
    return [*command[:2], diagnostic, *command[3:]]


def repair_split_powershell_command(command: Any) -> list[str] | None:
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return None
    if not is_powershell_command_vector(command) or len(command) <= 3:
        return None
    return [command[0], command[1], join_powershell_command_tokens(command[2:])]


def repair_direct_powershell_cmdlet(command: Any) -> list[str] | None:
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return None
    if not command or is_powershell_command_vector(command):
        return None
    if not looks_like_powershell_cmdlet(command[0]):
        return None
    if len(command) == 1 and looks_like_single_powershell_script(command[0]):
        return ["powershell.exe", "-Command", command[0].strip()]
    return ["powershell.exe", "-Command", join_powershell_command_tokens(command)]


def join_powershell_command_tokens(tokens: list[str]) -> str:
    return " ".join(quote_powershell_token(token) for token in tokens).strip()


def quote_powershell_token(token: str) -> str:
    if token == "":
        return "''"
    if token in POWERSHELL_OPERATOR_TOKENS:
        return token
    if re.fullmatch(r"[A-Za-z0-9_./:\\-]+", token):
        return token
    return "'" + token.replace("'", "''") + "'"


def convert_bash_heredoc_to_powershell(script: str) -> str | None:
    lines = script.splitlines()
    if len(lines) < 3:
        return None
    first = lines[0]
    match = re.match(
        r"^\s*(?:cat|type)\s*>\s*(?P<target>\"[^\"]+\"|'[^']+'|\S+)\s*<<\s*(?P<delim>\"[^\"]+\"|'[^']+'|\w+)\s*$",
        first,
        re.IGNORECASE,
    )
    if not match:
        return None
    delimiter = strip_outer_quotes(match.group("delim"))
    if strip_outer_quotes(lines[-1].strip()) != delimiter:
        return None
    target = strip_outer_quotes(match.group("target"))
    body = "\n".join(lines[1:-1])
    body = re.sub(r"^<[\"']?!DOCTYPE", "<!DOCTYPE", body, count=1, flags=re.IGNORECASE)
    if "\n'@\n" in f"\n{body}\n":
        return None
    return f"$html = @'\n{body}\n'@; Set-Content -LiteralPath '{target}' -Value $html -Encoding UTF8"


def convert_bare_here_string_to_set_content(script: str) -> str | None:
    match = re.match(
        r"^\s*@(?P<quote>['\"])\r?\n(?P<body>.*?)\r?\n(?P=quote)@\s+(?P<rest>.+?)\s*$",
        script,
        flags=re.DOTALL,
    )
    if not match:
        return None
    body = match.group("body")
    rest = match.group("rest")
    target = named_powershell_path_argument(rest)
    if not target or not looks_like_artifact_path(target):
        return None
    marker = "'" if "\n'@\n" not in f"\n{body}\n" else '"'
    if f"\n{marker}@\n" in f"\n{body}\n":
        return None
    encoding = named_powershell_argument(rest, "-Encoding") or "UTF8"
    return (
        f"$html = @{marker}\n{body}\n{marker}@; "
        f"Set-Content -LiteralPath {quote_powershell_token(target)} -Value $html "
        f"-Encoding {quote_powershell_token(encoding)}"
    )


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
    parsed = parse_shell_array_string(value)
    if parsed is None:
        return None
    if not is_powershell_command_vector(parsed) or len(parsed) < 3:
        return None
    return " ".join(parsed[2:]).strip()


def parse_shell_array_string(value: str) -> list[str] | None:
    for candidate in json_array_parse_candidates(value):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list) and all(isinstance(part, str) for part in parsed):
            return parsed
    return parse_relaxed_json_string_array(value)


def parse_relaxed_json_string_array(value: str) -> list[str] | None:
    index = skip_whitespace(value, 0)
    if index >= len(value) or value[index] != "[":
        return None
    index += 1
    out: list[str] = []
    while True:
        index = skip_whitespace(value, index)
        if index >= len(value):
            return None
        if value[index] == "]":
            return out
        parsed = parse_relaxed_json_string(value, index)
        if parsed is None:
            return None
        item, index = parsed
        out.append(item)
        index = skip_whitespace(value, index)
        if index >= len(value):
            return None
        if value[index] == ",":
            index += 1
            continue
        if value[index] == "]":
            return out
        return None


def parse_relaxed_json_string(value: str, index: int) -> tuple[str, int] | None:
    if index >= len(value) or value[index] != '"':
        return None
    index += 1
    out: list[str] = []
    while index < len(value):
        char = value[index]
        if char == '"':
            return "".join(out), index + 1
        if char == "\\" and index + 1 < len(value):
            escaped = value[index + 1]
            if escaped in {'"', "\\", "/", "'"}:
                out.append(escaped)
            elif escaped in {"n", "N"}:
                out.append("\n")
            elif escaped == "r":
                out.append("\r")
            elif escaped == "t":
                out.append("\t")
            else:
                out.append(escaped)
            index += 2
            continue
        out.append(char)
        index += 1
    return None


def skip_whitespace(value: str, index: int) -> int:
    while index < len(value) and value[index].isspace():
        index += 1
    return index


def json_array_parse_candidates(value: str) -> list[str]:
    candidates = [value]
    repaired_newlines = value.replace("\\N", "\\n")
    if repaired_newlines != value:
        candidates.append(repaired_newlines)
    return candidates


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


def is_shell_executable(value: str) -> bool:
    return bool(SHELL_EXE_RE.search(value.strip().strip("\"'")))


def looks_like_executable_only_shell_command(command: list[str]) -> bool:
    if not command:
        return False
    if len(command) == 1:
        return is_shell_executable(command[0])
    if is_shell_executable(command[0]) and len(command) == 2 and command[1].lower() in POWERSHELL_COMMAND_FLAGS:
        return True
    if is_powershell_command_vector(command) and len(command) >= 3:
        return looks_like_shell_executable_script(command[2])
    return False


def looks_like_shell_executable_script(script: str) -> bool:
    tokens = split_command_line(script.strip())
    if tokens and tokens[0] == "&":
        tokens = tokens[1:]
    return len(tokens) == 1 and is_shell_executable(tokens[0])


def executable_only_shell_command_issue(command: list[str], arguments: JsonObject, source: str) -> JsonObject:
    metadata_keys = sorted(key for key in SHELL_METADATA_KEYS if key in arguments)
    message = "The shell call only invokes a shell executable and does not include a useful command script."
    if metadata_keys:
        message += " Approval metadata fields cannot stand in for the command script."
    issue: JsonObject = {
        "tool": "shell",
        "issue": "executable_only_command",
        "severity": "error",
        "source": source,
        "command": command,
        "message": message,
    }
    if metadata_keys:
        issue["metadata_keys"] = metadata_keys
    return issue


def looks_like_powershell_cmdlet(value: str) -> bool:
    stripped = value.strip().strip("\"'")
    command_name = first_powershell_command_token(stripped)
    if not command_name:
        return False
    if "\\" in command_name or "/" in command_name or "." in path_last_segment(command_name):
        return False
    if command_name.lower() in POWERSHELL_ALIAS_COMMANDS:
        return True
    if "-" not in command_name:
        return False
    verb = command_name.split("-", 1)[0].lower()
    return verb in POWERSHELL_CMDLET_VERBS


def first_powershell_command_token(value: str) -> str:
    tokens = split_command_line(value)
    if not tokens:
        tokens = value.split()
    for token in tokens:
        cleaned = strip_outer_quotes(token.strip())
        if not cleaned or cleaned == "&" or cleaned in POWERSHELL_OPERATOR_TOKENS:
            continue
        return cleaned
    return ""


def looks_like_single_powershell_script(value: str) -> bool:
    return bool(re.search(r"\s|[|;<>]", value.strip()))


def looks_like_embedded_json_command_array_item(value: str) -> bool:
    stripped = value.strip()
    if not re.search(r'(?i)(?:powershell|pwsh)(?:\.exe)?",\s*"[/-]?(?:command|c)",', stripped):
        return False
    return bool(re.search(r'"\]\s*,\s*"[A-Za-z_][A-Za-z0-9_]*"\s*:', stripped)) or stripped.count('","') >= 2


def contains_powershell_chain_operator(script: str) -> bool:
    return bool(re.search(r"(?<!&)&&(?!&)", strip_powershell_string_literals(script)))


def strip_powershell_here_strings(script: str) -> str:
    return re.sub(r"@(['\"])\r?\n.*?\r?\n\1@", "", script, flags=re.DOTALL)


def strip_powershell_string_literals(script: str) -> str:
    script = strip_powershell_here_strings(script)
    out: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(script):
        char = script[index]
        if quote == "'":
            if char == "'" and index + 1 < len(script) and script[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if char == "`":
                index += 2
                continue
            if char == '"' and index + 1 < len(script) and script[index + 1] == '"':
                index += 2
                continue
            if char == '"':
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def contains_bash_heredoc(script: str) -> bool:
    first_line = script.splitlines()[0] if script.splitlines() else script
    return bool(re.search(r"\b(?:cat|type)\s*>\s*(?:\"[^\"]+\"|'[^']+'|\S+)\s*<<", first_line, re.IGNORECASE))


def contains_bad_here_string_header(script: str) -> bool:
    return bool(re.search(r"@['\"]`n\S", script))


def contains_malformed_powershell_here_string(script: str) -> bool:
    if not re.search(r"\b(?:Set-Content|Out-File|WriteAllText)\b", script, re.IGNORECASE):
        return False
    scrubbed = strip_powershell_here_strings(script)
    if re.search(r"@['\"](?!\r?\n)", scrubbed):
        return True
    if re.search(r"(?<!\S)-Value\s+@(?!(?:['\"]\r?\n|\(|\{))\S+", scrubbed, re.IGNORECASE):
        return True
    if re.search(r"WriteAllText\s*\([^,]+,\s*@(?!(?:['\"]\r?\n))\S+", scrubbed, re.IGNORECASE | re.DOTALL):
        return True
    return False


def looks_like_malformed_json_array_command(script: str) -> bool:
    stripped = script.strip()
    if not stripped.startswith("["):
        return False
    if "powershell" not in stripped.lower() and "-command" not in stripped.lower():
        return False
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return True
    return not isinstance(parsed, list)


def contains_python_compound_one_liner(script: str) -> bool:
    if not re.search(r"\b(?:python|python3|py)(?:\.exe)?\s+-c\b", script, re.IGNORECASE):
        return False
    return bool(re.search(r";\s*(?:async\s+def|def|class|for|while|if|with|try)\b", script))


def contains_uv_run_playwright(script: str) -> bool:
    return bool(re.search(r"\buv\s+run\s+playwright\b", script, re.IGNORECASE))


def contains_html_echo_without_file_write(script: str) -> bool:
    if "<!doctype html" not in script.lower() and "<html" not in script.lower():
        return False
    if not re.search(r"^\s*(?:echo|write-output)\b", script, re.IGNORECASE):
        return False
    return not re.search(r"(>\s*['\"]?[^;&|]*index\.html|set-content|out-file)", script, re.IGNORECASE)


def empty_artifact_write_targets(script: str) -> list[str]:
    targets: list[str] = []
    targets.extend(empty_write_all_text_targets(script))
    targets.extend(empty_set_content_targets(script))
    return dedupe_keep_order([target for target in targets if looks_like_artifact_path(target)])


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def empty_write_all_text_targets(script: str) -> list[str]:
    targets: list[str] = []
    pattern = re.compile(
        r"\[System\.IO\.File\]::WriteAllText\s*\(\s*(?P<target>.+?)\s*,\s*(?P<value>''|\"\"|@'\s*'@|@\"\s*\"@)\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(script):
        expression = match.group("target")
        target = last_quoted_string(expression) or expression.strip()
        if target:
            targets.append(target)
    return targets


def empty_set_content_targets(script: str) -> list[str]:
    targets: list[str] = []
    for segment in powershell_command_segments(script):
        if not re.search(r"\bSet-Content\b", segment, re.IGNORECASE):
            continue
        target = named_powershell_path_argument(segment)
        if not target:
            positional = re.search(
                r"\bSet-Content\b\s+(?P<target>\"[^\"]+\"|'[^']+'|\S+)\s+(?:''|\"\")(?:\s|$)",
                segment,
                re.IGNORECASE | re.DOTALL,
            )
            target = strip_outer_quotes(positional.group("target")) if positional else ""
        if not target:
            continue
        if re.search(r"(?<!\S)-Value\s+(?:''|\"\")(?:\s|$)", segment, re.IGNORECASE | re.DOTALL):
            targets.append(target)
    return targets


def powershell_command_segments(script: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;\r\n]+", strip_powershell_here_strings(script)) if part.strip()]


def named_powershell_path_argument(segment: str) -> str:
    return named_powershell_argument(segment, "-LiteralPath", "-Path")


def named_powershell_argument(segment: str, *names: str) -> str:
    if not names:
        return ""
    alternatives = "|".join(re.escape(name) for name in names)
    match = re.search(
        rf"(?<!\S)(?:{alternatives})\s+(?P<value>\"[^\"]+\"|'[^']+'|\S+)",
        segment,
        re.IGNORECASE | re.DOTALL,
    )
    return strip_outer_quotes(match.group("value")) if match else ""


def last_quoted_string(value: str) -> str:
    matches = re.findall(r"'([^']*)'|\"([^\"]*)\"", value)
    for single, double in reversed(matches):
        return single or double
    return ""


def looks_like_artifact_path(value: str) -> bool:
    extension = path_extension(value)
    return extension in ARTIFACT_EXTENSIONS


def path_extension(path: str) -> str:
    last = path_last_segment(path)
    if "." not in last:
        return ""
    return "." + last.rsplit(".", 1)[1].lower()


def contains_unbounded_web_fetch(script: str) -> bool:
    lowered = script.lower()
    if "http://" not in lowered and "https://" not in lowered:
        return False
    if re.search(r"\binvoke-webrequest\b", script, re.IGNORECASE):
        if re.search(r"select-object\s+-expandproperty\s+content", script, re.IGNORECASE):
            return True
        if re.search(r"\.(?:content|rawcontent)\b", script, re.IGNORECASE):
            return True
    if re.search(r"\b(?:curl|wget|iwr)\b", script, re.IGNORECASE):
        if not re.search(r"\b(?:head|range|first|totalcount|select-object\s+-first|select-string)\b", script, re.IGNORECASE):
            return True
    return False


def contains_powershell_curl_unix_flags(script: str) -> bool:
    scrubbed = strip_powershell_here_strings(script)
    return bool(
        re.search(
            r"(?is)(?:^|[;&|]\s*)curl\s+(?=.*(?:\s-(?:s|S|I|L|m)\b|--head\b|--max-time\b|--silent\b|--show-error\b))",
            scrubbed,
        )
    )


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
    return path_extension(path)


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
