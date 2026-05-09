from __future__ import annotations

import unittest

from open_gate.command_quality import inspect_tool_calls, repair_shell_command_argument
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


if __name__ == "__main__":
    unittest.main()
