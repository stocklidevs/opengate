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

    def test_bare_response_recipient_is_extracted(self) -> None:
        report = analyze_text(
            'recipient_name=functions.shell_command\n{"command":"Get-ChildItem -Force"}',
            TOOLS,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell_command")
        self.assertEqual(report.tool_calls[0].source, "bare_response_recipient")
        self.assertEqual(report.cleaned_text, "")

    def test_glm_tool_call_tag_is_extracted(self) -> None:
        tools = [
            {
                "type": "function",
                "name": "shell",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "array", "items": {"type": "string"}},
                        "workdir": {"type": "string"},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            }
        ]
        report = analyze_text(
            '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Get-ChildItem -Force"]</arg_value><arg_key>workdir</arg_key><arg_value>C:\\Users\\example\\source\\repos\\glm-test</arg_value></tool_call>',
            tools,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell")
        self.assertEqual(report.tool_calls[0].source, "glm_tool_call_tag")
        self.assertEqual(report.tool_calls[0].arguments["command"], ["powershell.exe", "-Command", "Get-ChildItem -Force"])
        self.assertEqual(report.tool_calls[0].arguments["workdir"], "C:\\Users\\example\\source\\repos\\glm-test")
        self.assertTrue(report.tool_calls[0].valid)
        self.assertEqual(report.cleaned_text, "")

    def test_line_broken_glm_closing_tag_is_extracted(self) -> None:
        tools = [
            {
                "type": "function",
                "name": "update_plan",
                "parameters": {
                    "type": "object",
                    "properties": {"plan": {"type": "array"}},
                    "required": ["plan"],
                    "additionalProperties": False,
                },
            }
        ]
        report = analyze_text(
            'I will plan.<tool_call>update_plan<arg_key>plan</arg_key><arg_value>[{"step":"Inspect","status":"in_progress"}]</arg_value></\n  tool_call><tool_call>web_search<arg_key>external_web_access</arg_key><arg_value>true</arg_value></tool_call>',
            tools,
        )

        self.assertEqual([call.name for call in report.tool_calls], ["update_plan", "web_search"])
        self.assertTrue(report.tool_calls[0].valid)
        self.assertFalse(report.tool_calls[1].valid)
        self.assertEqual(report.cleaned_text, "I will plan.")

    def test_line_broken_glm_arg_key_closing_tag_is_extracted(self) -> None:
        tools = [
            {
                "type": "function",
                "name": "shell",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "array", "items": {"type": "string"}}},
                    "required": ["command"],
                    "additionalProperties": False,
                },
            }
        ]
        report = analyze_text(
            'I will check.<tool_call>web_search<arg_key>external_web_access</\n  arg_key><arg_value>true</arg_value></tool_call><tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Get-ChildItem -Filter index.html"]</arg_value></tool_call>',
            tools,
        )

        self.assertEqual([call.name for call in report.tool_calls], ["web_search", "shell"])
        self.assertFalse(report.tool_calls[0].valid)
        self.assertTrue(report.tool_calls[1].valid)
        self.assertEqual(
            report.tool_calls[1].arguments["command"],
            ["powershell.exe", "-Command", "Get-ChildItem -Filter index.html"],
        )
        self.assertEqual(report.cleaned_text, "I will check.")

    def test_line_broken_tool_call_opening_tag_is_extracted(self) -> None:
        tools = [
            {
                "type": "function",
                "name": "shell",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "array", "items": {"type": "string"}},
                        "justification": {"type": "string"},
                        "sandbox_permissions": {"type": "string"},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            }
        ]
        report = analyze_text(
            """I'll check the reference.<tool_ca
  ll>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Invoke-WebRequest -Uri 'https://styles.refero.design/' -UseBasicParsing"]</arg_value><arg_key>justification</arg_key><arg_value>Fetch reference site metadata</arg_value><arg_key>sandbox_permissions</arg_key><arg_value>require_escalated</arg_value></tool_call>""",
            tools,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell")
        self.assertTrue(report.tool_calls[0].valid)
        self.assertEqual(report.tool_calls[0].arguments["sandbox_permissions"], "require_escalated")
        self.assertEqual(report.cleaned_text, "I'll check the reference.")

    def test_unparsed_tool_call_documentation_is_stripped(self) -> None:
        report = analyze_text(
            """Here is an example:
```xml
<tool_call>
  <name>shell</name>
  <arguments>
    <command><item>PowerShell.exe</item></command>
  </arguments>
</tool_call>
```
Done.""",
            TOOLS,
        )

        self.assertEqual(report.tool_calls, [])
        self.assertNotIn("<tool_call>", report.cleaned_text)
        self.assertIn("Here is an example:", report.cleaned_text)
        self.assertIn("Done.", report.cleaned_text)

    def test_residual_recipient_syntax_is_neutralized(self) -> None:
        report = analyze_text("Use recipient_name=functions.shell or the recipient_name field.", TOOLS)

        self.assertEqual(report.tool_calls, [])
        self.assertNotIn("recipient_name", report.cleaned_text)
        self.assertIn("recipient name field", report.cleaned_text)


if __name__ == "__main__":
    unittest.main()
