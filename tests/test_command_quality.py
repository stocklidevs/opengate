from __future__ import annotations

import unittest

from open_gate.command_quality import (
    inspect_tool_calls,
    parse_shell_array_string,
    repair_shell_arguments,
    repair_shell_command_argument,
)
from open_gate.linter import ToolCall


class CommandQualityTests(unittest.TestCase):
    def test_detects_nested_powershell_command(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    'powershell.exe -Command "Get-ChildItem -Force | Measure-Object"',
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["issue"], "nested_powershell")
        self.assertEqual(
            issues[0]["repaired_command"],
            ["powershell.exe", "-Command", "Get-ChildItem -Force | Measure-Object"],
        )

    def test_repairs_nested_powershell_string_inside_array(self) -> None:
        repaired = repair_shell_command_argument(
            [
                "powershell.exe",
                "-Command",
                'powershell.exe -Command "Get-ChildItem -Force | Measure-Object"',
            ]
        )

        self.assertEqual(repaired, ["powershell.exe", "-Command", "Get-ChildItem -Force | Measure-Object"])

    def test_repairs_split_powershell_command_arguments(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": ["powershell.exe", "-Command", "Set-Content", "-Path", "index.html", "-Value", "ready"]},
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])
        repaired = repair_shell_arguments(call.arguments)

        self.assertIn("split_powershell_command", {issue["issue"] for issue in issues})
        self.assertEqual(
            repaired["command"],
            ["powershell.exe", "-Command", "Set-Content -Path index.html -Value ready"],
        )

    def test_repairs_direct_powershell_cmdlet_arguments(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": ["Write-Host", "loading"]},
            source="glm_tool_call_tag",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])
        repaired = repair_shell_arguments(call.arguments)

        self.assertIn("direct_powershell_cmdlet", {issue["issue"] for issue in issues})
        self.assertEqual(repaired["command"], ["powershell.exe", "-Command", "Write-Host loading"])

    def test_repairs_direct_powershell_alias_arguments(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": ["dir"]},
            source="deepseek_v3_tool_call",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])
        repaired = repair_shell_arguments(call.arguments)

        self.assertIn("direct_powershell_cmdlet", {issue["issue"] for issue in issues})
        self.assertEqual(repaired["command"], ["powershell.exe", "-Command", "dir"])

    def test_leaves_clean_command_array_alone(self) -> None:
        repaired = repair_shell_command_argument(["powershell.exe", "-Command", "Get-ChildItem -Force"])

        self.assertIsNone(repaired)

    def test_detects_executable_only_shell_command(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": ["powershell.exe", "-Command", "powershell.exe"],
                "justification": "Fetch reference site metadata",
                "prefix_rule": ["powershell.exe", "-Command", "(Invoke-Web"],
                "sandbox_permissions": "require_escalated",
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(issues[0]["issue"], "executable_only_command")
        self.assertEqual(issues[0]["severity"], "error")
        self.assertEqual(issues[0]["metadata_keys"], ["justification", "prefix_rule", "sandbox_permissions"])

    def test_detects_string_command_that_is_only_shell_executable(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": "powershell.exe"},
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertIn("string_command", {issue["issue"] for issue in issues})
        self.assertIn("executable_only_command", {issue["issue"] for issue in issues})

    def test_repairs_json_array_encoded_powershell_command(self) -> None:
        repaired = repair_shell_command_argument(
            [
                "powershell.exe",
                "-Command",
                "[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"]",
            ]
        )

        self.assertEqual(repaired, ["powershell.exe", "-Command", "Get-ChildItem -Force"])

    def test_repairs_json_array_encoded_powershell_command_with_uppercase_newline_escape(self) -> None:
        repaired = repair_shell_command_argument(
            [
                "powershell.exe",
                "-Command",
                "[\"powershell.exe\",\"-Command\",\"Set-Content 'log_triage.py' -Value @'\\nimport sys\\N# comment\\n'@\"]",
            ]
        )

        self.assertEqual(
            repaired,
            ["powershell.exe", "-Command", "Set-Content 'log_triage.py' -Value @'\nimport sys\n# comment\n'@"],
        )

    def test_parses_relaxed_multiline_shell_array_string(self) -> None:
        parsed = parse_shell_array_string(
            '["powershell", "-Command", "[System.IO.File]::WriteAllText(\'index.html\', @\'\n'
            '<!DOCTYPE html>\n<html lang=\\"en\\"></html>\n'
            '\'@, \\"utf8\\")"]'
        )

        self.assertEqual(parsed[0:2], ["powershell", "-Command"])
        self.assertIn("<!DOCTYPE html>", parsed[2])
        self.assertIn('<html lang="en">', parsed[2])

    def test_detects_windows_powershell_chain_operator(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": ["powershell.exe", "-Command", "cd glm-test && uv run python -c \"print(1)\""]},
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertIn("windows_powershell_chain_operator", {issue["issue"] for issue in issues})
        self.assertIn("relative_cd_without_workdir", {issue["issue"] for issue in issues})

    def test_ignores_javascript_chain_operator_inside_here_string(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "$html = @'\n<script>if (active && ready) run();</script>\n'@; Set-Content index.html $html",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertNotIn("windows_powershell_chain_operator", {issue["issue"] for issue in issues})

    def test_ignores_javascript_chain_operator_inside_quoted_artifact_string(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "Set-Content -Path index.html -Value '<script>if (active && ready) run();</script>'",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertNotIn("windows_powershell_chain_operator", {issue["issue"] for issue in issues})

    def test_still_detects_chain_operator_outside_powershell_strings(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "Write-Output 'safe && text'; cd glm-test && uv run python -c \"print(1)\"",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertIn("windows_powershell_chain_operator", {issue["issue"] for issue in issues})

    def test_detects_powershell_here_string_escape_misuse(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": ["powershell.exe", "-Command", "$script = @'`nimport asyncio`n'@"]},
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(issues[0]["issue"], "powershell_here_string_header")

    def test_detects_malformed_powershell_here_string_placeholder(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "Set-Content -LiteralPath 'index.html' -Value @```ENDOFHTML``@ -Encoding UTF8",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertIn("malformed_powershell_here_string", {issue["issue"] for issue in issues})

    def test_repairs_bad_powershell_here_string_header(self) -> None:
        repaired = repair_shell_arguments(
            {"command": ["powershell.exe", "-Command", "$script = @'`nimport asyncio`n'@"]}
        )

        self.assertEqual(repaired["command"], ["powershell.exe", "-Command", "$script = @'\nimport asyncio\n'@"])

    def test_detects_python_compound_statement_one_liner(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "python -c \"import asyncio; async def main(): pass\"",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(issues[0]["issue"], "python_compound_statement_one_liner")

    def test_detects_view_image_non_image_path(self) -> None:
        call = ToolCall(
            name="view_image",
            arguments={"path": "C:\\Users\\example\\source\\repos\\glm-test"},
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(issues[0]["issue"], "view_image_non_image_path")

    def test_detects_skill_file_read_as_mcp_resource(self) -> None:
        call = ToolCall(
            name="read_mcp_resource",
            arguments={
                "server": "codex-skills",
                "uri": "file://C:/Users/example/.codex/skills/.system/imagegen/SKILL.md",
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(issues[0]["issue"], "skill_file_as_mcp_resource")

    def test_detects_uv_run_playwright_entrypoint(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": ["powershell.exe", "-Command", "uv run playwright install chromium"]},
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(issues[0]["issue"], "uv_run_playwright_entrypoint")

    def test_detects_html_echo_without_file_write(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={"command": ["powershell.exe", "-Command", "echo \"<!DOCTYPE html><html></html>\""]},
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertEqual(issues[0]["issue"], "html_echo_without_file_write")

    def test_quarantines_empty_artifact_write(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                    "-Command",
                    "[System.IO.File]::WriteAllText((Resolve-Path 'index.html').Path, '')",
                ]
            },
            source="glm_tool_call_tag",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])
        repaired = repair_shell_arguments(call.arguments)

        self.assertEqual(issues[0]["issue"], "empty_artifact_write")
        self.assertEqual(issues[0]["targets"], ["index.html"])
        self.assertIn("Open Gate blocked an empty file write", repaired["command"][2])

    def test_quarantines_empty_set_content_artifact_write(self) -> None:
        repaired = repair_shell_arguments(
            {"command": ["powershell.exe", "-Command", "Set-Content -Path index.html -Value ''"]}
        )

        self.assertIn("Open Gate blocked an empty file write", repaired["command"][2])

    def test_allows_nonempty_artifact_write(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "[System.IO.File]::WriteAllText('index.html', '<!DOCTYPE html><html></html>')",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertNotIn("empty_artifact_write", {issue["issue"] for issue in issues})

    def test_detects_unbounded_web_fetch(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "Invoke-WebRequest -Uri 'https://styles.refero.design/' -UseBasicParsing | Select-Object -ExpandProperty Content",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertIn("unbounded_web_fetch", {issue["issue"] for issue in issues})

    def test_detects_powershell_curl_unix_flags(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    'curl -s -S -m 10 --head "https://styles.refero.design/"',
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertIn("powershell_curl_unix_flags", {issue["issue"] for issue in issues})

    def test_detects_malformed_json_array_command(self) -> None:
        call = ToolCall(
            name="shell",
            arguments={
                "command": [
                    "powershell.exe",
                    "-Command",
                    "[\"powershell.exe\", \"-Command\", \"Set-Content\", \"-Path\", \"index.html\";",
                ]
            },
            source="responses_structured",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])

        self.assertIn("malformed_json_array_command", {issue["issue"] for issue in issues})

    def test_repairs_bash_heredoc_for_powershell(self) -> None:
        repaired = repair_shell_arguments(
            {
                "command": [
                    "powershell.exe",
                    "-Command",
                    "cat > \"index.html\" << 'EOF'\n<\"!DOCTYPE html>\n<html></html>\nEOF",
                ]
            }
        )

        self.assertIn("Set-Content -LiteralPath 'index.html'", repaired["command"][2])
        self.assertIn("<!DOCTYPE html>", repaired["command"][2])

    def test_repairs_bare_here_string_file_write_for_powershell(self) -> None:
        command = [
            "powershell.exe",
            "-Command",
            "@'\n<!DOCTYPE html>\n<html></html>\n'@ -Path '.\\index.html' -Encoding UTF8",
        ]
        call = ToolCall(
            name="shell",
            arguments={"command": command},
            source="glm_tool_call_tag",
            span=(0, 0),
            raw="{}",
        )

        issues = inspect_tool_calls([call])
        repaired = repair_shell_arguments({"command": command})

        self.assertIn("bare_here_string_file_write", {issue["issue"] for issue in issues})
        self.assertIn("Set-Content -LiteralPath", repaired["command"][2])
        self.assertIn("<!DOCTYPE html>", repaired["command"][2])
        self.assertIn("-Value $html", repaired["command"][2])


if __name__ == "__main__":
    unittest.main()
