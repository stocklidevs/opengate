from __future__ import annotations

import json
from pathlib import Path
import unittest

from open_gate.linter import analyze_text, load_tool_specs


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

    def test_kimi_reserved_token_tool_call_is_extracted_and_cleaned(self) -> None:
        tools = [
            {
                "type": "function",
                "name": "ping",
                "parameters": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"],
                    "additionalProperties": False,
                },
            }
        ]
        report = analyze_text(
            '<|reserved_token_163595|><|reserved_token_163597|>functions.ping:0<|reserved_token_163598|>{"x": "ok"}<|reserved_token_163599|><|reserved_token_163596|>',
            tools,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "ping")
        self.assertEqual(report.tool_calls[0].source, "kimi_reserved_tool_call")
        self.assertEqual(report.tool_calls[0].arguments["x"], "ok")
        self.assertTrue(report.tool_calls[0].valid)
        self.assertEqual(report.cleaned_text, "")
        self.assertIn("parsed_tool_call", report.leaks)
        self.assertIn("kimi_reserved_tool_marker", report.leaks)

    def test_gemma_pipe_tool_call_is_extracted_and_cleaned(self) -> None:
        report = analyze_text(
            '<|tool_call>call:superpowers:brainstorming{message:<|"|>Plan the implementation.<|"|>}<tool_call|>',
            TOOLS,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "superpowers:brainstorming")
        self.assertEqual(report.tool_calls[0].source, "gemma_pipe_tool_call")
        self.assertFalse(report.tool_calls[0].valid)
        self.assertIn("Unknown tool: superpowers:brainstorming", report.tool_calls[0].errors)
        self.assertEqual(report.cleaned_text, "")
        self.assertIn("parsed_tool_call", report.leaks)

    def test_codex_transcript_tool_call_is_extracted_and_cleaned(self) -> None:
        report = analyze_text(
            "assistant tool call shell chatcmpl-tool-8e5c932fb4903995:\n"
            '{"command":["powershell.exe","-Command","Write-Output \'{row} ${total:,.2f}\'"]}\n\n'
            "tool output chatcmpl-tool-8e5c932fb4903995:\n"
            '{"output":"","metadata":{"exit_code":0,"duration_seconds":0.4}}',
            TOOLS,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell")
        self.assertEqual(report.tool_calls[0].source, "codex_transcript_tool_call")
        self.assertEqual(
            report.tool_calls[0].arguments["command"],
            ["powershell.exe", "-Command", "Write-Output '{row} ${total:,.2f}'"],
        )
        self.assertEqual(report.cleaned_text, "")
        self.assertIn("parsed_tool_call", report.leaks)
        self.assertIn("codex_transcript_tool_call", report.leaks)

    def test_codex_transcript_tool_call_recovers_unterminated_json_and_junk(self) -> None:
        # Observed with Qwen3.6: a transcript header, then a JSON object that is
        # missing its closing brace, then XML close tags. Strict raw_decode fails,
        # so the call must be recovered by balancing brackets and trailing junk
        # stripped, or the turn ends on a bland final message with no tool call.
        report = analyze_text(
            "Good, customers.csv is created. Let me write orders.csv next.\n\n"
            "assistant tool call shell_command chatcmpl-tool-cf34a0a92717e776:\n"
            '{"command": ["powershell.exe", "-NoProfile", "-Command", "$p=\'orders.csv\'"]\n'
            "</parameter>\n</function>\n</tool_call>",
            TOOLS,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell_command")
        self.assertEqual(
            report.tool_calls[0].arguments["command"],
            ["powershell.exe", "-NoProfile", "-Command", "$p='orders.csv'"],
        )
        self.assertEqual(report.tool_calls[0].source, "codex_transcript_tool_call")
        self.assertEqual(
            report.cleaned_text,
            "Good, customers.csv is created. Let me write orders.csv next.",
        )

    def test_deepseek_v3_delimited_tool_call_is_extracted_and_cleaned(self) -> None:
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
            '<\uff5ctool\u2581call\u2581begin\uff5c>function<\uff5ctool\u2581sep\uff5c>shell\n'
            "```json\n"
            '{"command": ["powershell.exe", "-Command", "Get-ChildItem -Force"], "workdir": "C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}\n'
            "```"
            '<\uff5ctool\u2581call\u2581end\uff5c><\uff5ctool\u2581calls\u2581end\uff5c>\n'
            '<\uff5ctool\u2581outputs\u2581begin\uff5c><\uff5ctool\u2581output\u2581begin\uff5c>{"output":"Directory"}'
            '<\uff5ctool\u2581output\u2581end\uff5c><\uff5ctool\u2581outputs\u2581end\uff5c>\n'
            "The directory contains files.",
            tools,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell")
        self.assertEqual(report.tool_calls[0].source, "deepseek_v3_tool_call")
        self.assertEqual(report.tool_calls[0].arguments["command"], ["powershell.exe", "-Command", "Get-ChildItem -Force"])
        self.assertTrue(report.tool_calls[0].valid)
        self.assertEqual(report.cleaned_text, "The directory contains files.")
        self.assertIn("parsed_tool_call", report.leaks)
        self.assertIn("deepseek_v3_tool_marker", report.leaks)

    def test_deepseek_v3_partial_markers_are_stripped_without_promotion(self) -> None:
        report = analyze_text(
            "```json\n"
            '{"command": ["powershell.exe", "-Command", "Get-Location"], "workdir": "C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}\n'
            "```"
            '<\uff5ctool\u2581call\u2581end\uff5c><\uff5ctool\u2581calls\u2581end\uff5c>\n'
            '<\uff5ctool\u2581outputs\u2581begin\uff5c><\uff5ctool\u2581output\u2581begin\uff5c>{"output":"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}'
            '<\uff5ctool\u2581output\u2581end\uff5c><\uff5ctool\u2581outputs\u2581end\uff5c>\n'
            'The current working directory is "C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test".',
            TOOLS,
        )

        self.assertEqual(report.tool_calls, [])
        self.assertNotIn("\u2581", report.cleaned_text)
        self.assertNotIn('"command"', report.cleaned_text)
        self.assertEqual(report.cleaned_text, 'The current working directory is "C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test".')
        self.assertIn("deepseek_v3_tool_marker", report.leaks)

    def test_json_tool_calls_function_parameters_become_arguments(self) -> None:
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
            "```json\n"
            '{"tool_calls":[{"id":"tool_1","type":"function","function":{"name":"shell","parameters":{"command":["powershell.exe","-Command","Get-Content forest-scene.html -TotalCount 1"],"workdir":"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}}}]}\n'
            "```",
            tools,
        )

        self.assertEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell")
        self.assertEqual(
            report.tool_calls[0].arguments["command"],
            ["powershell.exe", "-Command", "Get-Content forest-scene.html -TotalCount 1"],
        )
        self.assertTrue(report.tool_calls[0].valid)

    def test_tool_spec_wrapper_becomes_tool_call(self) -> None:
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
            "Before running it, place the tool call in a fenced ```json block for inspection.\n\n"
            "```json\n"
            '{"toolSpec":{"name":"shell","args":{"command":["powershell.exe","-Command","Get-Location"],"workdir":"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}}}\n'
            "```<channel|>```json\n"
            '{"toolSpec":{"name":"shell","args":{"command":["powershell.exe","-Command","Get-Location"],"workdir":"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}}}\n'
            "```",
            tools,
        )

        self.assertGreaterEqual(len(report.tool_calls), 1)
        self.assertEqual(report.tool_calls[0].name, "shell")
        self.assertEqual(report.tool_calls[0].source, "fenced_json")
        self.assertEqual(report.tool_calls[0].arguments["command"], ["powershell.exe", "-Command", "Get-Location"])
        self.assertNotIn("toolSpec", report.cleaned_text)
        self.assertNotIn("<channel|>", report.cleaned_text)
        self.assertIn("parsed_tool_call", report.leaks)
        self.assertTrue(report.tool_calls[0].valid)

    def test_type_only_hosted_tool_is_available(self) -> None:
        tools = [{"type": "web_search"}]

        specs = load_tool_specs(tools)
        report = analyze_text(
            "<tool_call>web_search<arg_key>external_web_access</arg_key><arg_value>true</arg_value></tool_call>",
            tools,
        )

        self.assertIn("web_search", specs)
        self.assertEqual(report.tool_calls[0].name, "web_search")
        self.assertTrue(report.tool_calls[0].valid)

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

    def test_residual_tool_call_tag_text_is_neutralized(self) -> None:
        report = analyze_text("The exact <tool_call> XML would go here.", TOOLS)

        self.assertEqual(report.tool_calls, [])
        self.assertNotIn("<tool_call>", report.cleaned_text)
        self.assertIn("tool call", report.cleaned_text)
        self.assertIn("tool_call_tag", report.leaks)

    def test_residual_recipient_syntax_is_neutralized(self) -> None:
        report = analyze_text("Use recipient_name=functions.shell or the recipient_name field.", TOOLS)

        self.assertEqual(report.tool_calls, [])
        self.assertNotIn("recipient_name", report.cleaned_text)
        self.assertIn("recipient name field", report.cleaned_text)


if __name__ == "__main__":
    unittest.main()
