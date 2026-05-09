from __future__ import annotations

import json
from pathlib import Path
import unittest

from open_gate.linter import analyze_text


ROOT = Path(__file__).resolve().parents[1]
TOOLS = json.loads((ROOT / "fixtures" / "tools" / "codex_like_tools.json").read_text(encoding="utf-8"))


class LinterTests(unittest.TestCase):
    def read_fixture(self, name: str) -> str:
        return (ROOT / "fixtures" / "leaks" / name).read_text(encoding="utf-8")

    def test_qwen_xml_tool_call_is_extracted_and_cleaned(self) -> None:
        report = analyze_text(self.read_fixture("qwen_xml_tool_call.txt"), TOOLS)

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell_command")
        self.assertEqual(report.tool_calls[0].arguments["command"], "Get-ChildItem -Force")
        self.assertTrue(report.tool_calls[0].valid)
        self.assertNotIn("<tool_call>", report.cleaned_text)
        self.assertIn("parsed_tool_call", report.leaks)

    def test_hermes_tool_calls_array_is_normalised(self) -> None:
        report = analyze_text(self.read_fixture("hermes_tool_calls_array.txt"), TOOLS)

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell_command")
        self.assertEqual(report.tool_calls[0].arguments["command"], "Get-ChildItem -Force")

    def test_pythonic_call_is_extracted(self) -> None:
        report = analyze_text(self.read_fixture("pythonic_call.txt"), TOOLS)

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell_command")
        self.assertEqual(report.tool_calls[0].source, "pythonic_call")
        self.assertNotIn("functions.shell_command", report.cleaned_text)

    def test_schema_validation_flags_missing_required_arguments(self) -> None:
        report = analyze_text(self.read_fixture("invalid_args.txt"), TOOLS)

        self.assertEqual(len(report.tool_calls), 1)
        self.assertFalse(report.tool_calls[0].valid)
        self.assertIn("Missing required argument: command", report.tool_calls[0].errors)

    def test_top_level_tool_json_fields_become_arguments(self) -> None:
        report = analyze_text(
            '```json\n{"tool":"shell_command","command":"Get-ChildItem -Force","workdir":"."}\n```',
            TOOLS,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].arguments["command"], "Get-ChildItem -Force")
        self.assertTrue(report.tool_calls[0].valid)

    def test_response_recipient_tag_is_extracted(self) -> None:
        report = analyze_text(
            '<response recipient_name=functions.shell_command>\n"Get-ChildItem -Force"\n</response>',
            TOOLS,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell_command")


if __name__ == "__main__":
    unittest.main()
