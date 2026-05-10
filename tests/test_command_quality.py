from __future__ import annotations

import unittest

from open_gate.command_quality import inspect_tool_calls, repair_shell_arguments, repair_shell_command_argument
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

    def test_leaves_clean_command_array_alone(self) -> None:
        repaired = repair_shell_command_argument(["powershell.exe", "-Command", "Get-ChildItem -Force"])

        self.assertIsNone(repaired)

    def test_repairs_json_array_encoded_powershell_command(self) -> None:
        repaired = repair_shell_command_argument(
            [
                "powershell.exe",
                "-Command",
                "[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"]",
            ]
        )

        self.assertEqual(repaired, ["powershell.exe", "-Command", "Get-ChildItem -Force"])

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


if __name__ == "__main__":
    unittest.main()
