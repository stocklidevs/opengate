from __future__ import annotations

import unittest
from unittest.mock import patch

from open_gate.proxy import (
    apply_request_diet,
    build_proxy_error_response,
    compile_responses_context,
    forward_responses_request,
    needs_flattened_input,
    normalize_responses_response,
    transform_upstream_request,
)


TOOLS = [
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
SPAWN_AGENT_TOOL = {
    "type": "function",
    "name": "spawn_agent",
    "parameters": {
        "type": "object",
        "properties": {
            "agent_type": {"type": "string"},
            "message": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


class ProxyNormalizationTests(unittest.TestCase):
    def request(self, prompt: str) -> dict:
        return {
            "model": "Qwen3-Coder-Next",
            "tool_choice": "auto",
            "tools": TOOLS,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
        }

    def request_with_tools(self, prompt: str, tools: list[dict]) -> dict:
        request = self.request(prompt)
        request["tools"] = tools
        return request

    def test_promotes_recoverable_fenced_tool_json(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '```json\n{"tool":"shell","command":["powershell.exe","-Command","Get-Location"],"workdir":"."}\n```',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Run the command, then answer."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertEqual(details["promoted_tool_calls"][0]["name"], "shell")

    def test_promotes_glm_tool_call_tag(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Get-ChildItem -Force"]</arg_value><arg_key>workdir</arg_key><arg_value>C:\\Users\\example\\source\\repos\\glm-test</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Inspect the workspace with shell."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertEqual(details["promoted_tool_calls"][0]["source"], "glm_tool_call_tag")
        self.assertEqual(details["stripped_text_items"], 1)

    def test_promotes_top_level_glm_output_text(self) -> None:
        response = {
            "id": "resp_test",
            "output": [],
            "output_text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Get-Location"]</arg_value></tool_call>',
        }

        normalized, details = normalize_responses_response(response, self.request("Run shell."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertEqual(normalized["output_text"], "")
        self.assertEqual(details["promoted_tool_calls"][0]["source"], "glm_tool_call_tag")

    def test_repairs_and_promotes_glm_string_command_tag(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>Get-ChildItem -Force</arg_value><arg_key>workdir</arg_key><arg_value>C:\\Users\\example\\source\\repos\\glm-test</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("List files with shell."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"],\"workdir\":\"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test\"}",
        )
        self.assertEqual(details["text_tool_call_repairs"][0]["tool"], "shell")
        self.assertEqual(details["promoted_tool_calls"][0]["arguments"]["command"][0], "powershell.exe")

    def test_repairs_and_promotes_glm_nested_json_array_with_uppercase_newline_escape(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe","-Command","[\\"powershell.exe\\",\\"-Command\\",\\"Set-Content \'log_triage.py\' -Value @\'\\\\nimport sys\\\\N# comment\\\\n\'@\\"]"]</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create log_triage.py."))
        arguments = normalized["output"][0]["arguments"]

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Set-Content 'log_triage.py'", arguments)
        self.assertIn("\\n# comment", arguments)
        self.assertEqual(details["text_tool_call_repairs"][0]["tool"], "shell")
        self.assertEqual(details["invalid_tool_calls"], [])

    def test_repairs_glm_extra_argument_before_promotion(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["Get-ChildItem"]</arg_value><arg_key>recipient_name</arg_key><arg_value>functions.shell</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("List files with shell."))
        arguments = normalized["output"][0]["arguments"]

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem\"]", arguments)
        self.assertNotIn("recipient_name", arguments)
        self.assertEqual(details["promoted_tool_calls"][0]["arguments"], {"command": ["powershell.exe", "-Command", "Get-ChildItem"]})

    def test_blocks_spawn_agent_without_explicit_user_request(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>spawn_agent<arg_key>agent_type</arg_key><arg_value>code</arg_value><arg_key>message</arg_key><arg_value>Create index.html.</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Create index.html in this folder.", [*TOOLS, SPAWN_AGENT_TOOL]),
        )

        self.assertEqual(normalized["output"][0]["content"][0]["text"], "")
        self.assertEqual(details["promoted_tool_calls"], [])
        self.assertEqual(details["invalid_tool_calls"][0]["name"], "spawn_agent")
        self.assertIn("explicit user request", details["invalid_tool_calls"][0]["errors"][0])
        self.assertIn("agent_type", details["invalid_tool_calls"][0]["errors"][1])

    def test_allows_spawn_agent_when_user_explicitly_requests_subagents(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>spawn_agent<arg_key>agent_type</arg_key><arg_value>worker</arg_value><arg_key>message</arg_key><arg_value>Create index.html.</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Use a subagent to create index.html.", [*TOOLS, SPAWN_AGENT_TOOL]),
        )

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "spawn_agent")
        self.assertEqual(details["promoted_tool_calls"][0]["arguments"]["agent_type"], "worker")

    def test_suppresses_structured_spawn_agent_without_user_request(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "spawn_agent",
                    "arguments": "{\"agent_type\":\"worker\",\"message\":\"Create index.html.\"}",
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Create index.html in this folder.", [*TOOLS, SPAWN_AGENT_TOOL]),
        )

        self.assertEqual(normalized["output"], [])
        self.assertEqual(details["policy_suppressed_structured_calls"][0]["name"], "spawn_agent")

    def test_quarantines_promoted_tool_call_with_unrepaired_command_quality_error(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "[\\"powershell.exe\\", \\"-Command\\", \\"Set-Content\\", \\"-Path\\", \\"index.html\\";"]</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Open Gate blocked an invalid shell command (malformed_json_array_command)", normalized["output"][0]["arguments"])
        self.assertEqual(details["invalid_tool_calls"], [])
        self.assertTrue(any("quarantined_command_quality_issues" in repair for repair in details["text_tool_call_repairs"]))

    def test_repairs_promoted_direct_powershell_cmdlet(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["Write-Host", "loading"]</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Write-Host loading\"]}",
        )
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_repairs_structured_split_powershell_command(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Set-Content\",\"-Path\",\"index.html\",\"-Value\",\"<html></html>\"]}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))

        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Set-Content -Path index.html -Value '<html></html>'\"]}",
        )
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_quarantines_promoted_empty_artifact_write(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["C:\\\\WINDOWS\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe","-Command","[System.IO.File]::WriteAllText(\'index.html\', \'\')"]</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }
        response["output"].insert(
            0,
            {
                "id": "reasoning_test",
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": "Good, I cleared index.html."}],
            },
        )

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))
        arguments = normalized["output"][0]["arguments"]

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Open Gate blocked an empty file write", arguments)
        self.assertIn("Open Gate blocked an empty file write", str(details["text_tool_call_repairs"]))
        self.assertEqual(details["reasoning_items_removed"], 1)
        self.assertEqual([item["type"] for item in normalized["output"]], ["function_call"])
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_quarantines_structured_empty_artifact_write(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"[System.IO.File]::WriteAllText((Resolve-Path 'index.html').Path, '')\"]}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))
        arguments = normalized["output"][0]["arguments"]

        self.assertIn("Open Gate blocked an empty file write", arguments)
        self.assertIn("empty_artifact_write", {issue["issue"] for issue in details["upstream_command_quality_issues"]})
        self.assertEqual(details["command_quality_suppressed_structured_calls"], [])

    def test_promotes_glm_multiline_file_write_array_string(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell", "-Command", "[System.IO.File]::WriteAllText(\'index.html\', @\'\n<!DOCTYPE html>\n<html lang=\\"en\\"></html>\n\'@, \\"utf8\\")"]</arg_value><arg_key>workdir</arg_key><arg_value>C:\\Users\\example\\source\\repos\\glm-test</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))
        arguments = normalized["output"][0]["arguments"]

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("[System.IO.File]::WriteAllText", arguments)
        self.assertIn("<!DOCTYPE html>", arguments)
        self.assertEqual(details["invalid_tool_calls"], [])
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_quarantines_promoted_unbounded_web_fetch_as_diagnostic_tool(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "<tool_call>shell<arg_key>command</arg_key><arg_value>@('curl', '-s', 'https://styles.refero.design/')</arg_value><arg_key>justification</arg_key><arg_value>Fetch reference site metadata</arg_value></tool_call>",
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))
        arguments = normalized["output"][0]["arguments"]

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Open Gate blocked an invalid shell command (unbounded_web_fetch)", arguments)
        self.assertIn("Do not retry that route", arguments)
        self.assertEqual(details["invalid_tool_calls"], [])
        self.assertTrue(any("quarantined_command_quality_issues" in repair for repair in details["text_tool_call_repairs"]))
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_repairs_promoted_bare_here_string_file_write(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "<tool_call>shell<arg_key>command</arg_key><arg_value>[\"powershell.exe\", \"-Command\", \"@'\n<!DOCTYPE html>\n<html></html>\n'@ -Path '.\\\\index.html' -Encoding UTF8\"]</arg_value></tool_call>",
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))
        arguments = normalized["output"][0]["arguments"]

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Set-Content -LiteralPath", arguments)
        self.assertIn("<!DOCTYPE html>", arguments)
        self.assertEqual(details["invalid_tool_calls"], [])
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_suppresses_structured_command_quality_error(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Invoke-WebRequest -Uri 'https://styles.refero.design/' -UseBasicParsing | Select-Object -ExpandProperty Content\"]}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Inspect the reference site."))

        self.assertEqual(normalized["output"][0]["type"], "message")
        self.assertIn("suppressed an invalid tool call", normalized["output"][0]["content"][0]["text"])
        self.assertEqual(details["command_quality_suppressed_structured_calls"][0]["name"], "shell")
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_strips_reasoning_glm_tool_call_without_promoting(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "reasoning_test",
                    "type": "reasoning",
                    "content": [
                        {
                            "type": "reasoning_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Get-Location"]</arg_value></tool_call>',
                        }
                    ],
                },
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Done."}],
                },
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Run shell."))

        self.assertEqual(normalized["output"][0]["content"][0]["text"], "")
        self.assertEqual(normalized["output"][1]["type"], "message")
        self.assertEqual(details["promoted_tool_calls"], [])
        self.assertEqual(details["stripped_text_items"], 1)

    def test_glm_documentation_tool_call_tag_is_stripped_not_promoted(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Get-ChildItem -Force"]</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request("Without using tools, show a sample <tool_call> for documentation only."),
        )

        self.assertEqual(normalized["output"][0]["type"], "message")
        self.assertEqual(normalized["output"][0]["content"][0]["text"], "")
        self.assertEqual(details["promoted_tool_calls"], [])
        self.assertEqual(details["promotion_block_reason"], "negative_tool_intent")

    def test_no_tool_documentation_leak_is_stripped_not_promoted(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '```json\n{"tool_calls":[{"name":"shell","arguments":{"command":["powershell.exe","-Command","Get-Location"]}}]}\n```',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Without using any tools, show an example."))

        self.assertEqual(normalized["output"][0]["type"], "message")
        self.assertEqual(normalized["output"][0]["content"][0]["text"], "")
        self.assertEqual(details["promoted_tool_calls"], [])
        self.assertEqual(details["promotion_block_reason"], "negative_tool_intent")

    def test_sample_artifact_prompt_still_promotes_tool_calls(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["New-Item", "-Path", "sample_app.log", "-ItemType", "File"]</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request("Create sample_app.log and run two sample commands."),
        )

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(details["promoted_tool_calls"][0]["name"], "shell")
        self.assertIsNone(details["promotion_block_reason"])

    def test_no_tool_prompt_suppresses_structured_calls(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-Location\"]}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Without using any tools, show an example."))

        self.assertEqual(normalized["output"], [])
        self.assertEqual(len(details["suppressed_structured_calls"]), 1)

    def test_repairs_string_command_argument(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":\"Get-Location\",\"recipient_name\":\"functions.shell\"}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Run the command."))

        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-Location\"]}",
        )
        self.assertEqual(len(details["structured_argument_repairs"]), 1)
        self.assertEqual(details["upstream_command_quality_issues"][0]["issue"], "string_command")
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_repairs_nested_powershell_command_argument(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":\"powershell.exe -Command \\\"Get-Location\\\"\"}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Run the command."))

        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-Location\"]}",
        )
        self.assertEqual(len(details["structured_argument_repairs"]), 1)
        self.assertEqual(details["upstream_command_quality_issues"][0]["issue"], "string_command")
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_suppresses_unrepaired_command_quality_errors(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"cd glm-test && uv run playwright install chromium\"]}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Run the command."))

        self.assertEqual(normalized["output"][0]["type"], "message")
        self.assertIn("suppressed an invalid tool call", normalized["output"][0]["content"][0]["text"])
        self.assertEqual(
            {issue["issue"] for issue in details["normalized_command_quality_issues"]},
            set(),
        )
        self.assertEqual(
            {issue["issue"] for issue in details["command_quality_suppressed_structured_calls"][0]["command_quality_errors"]},
            {"windows_powershell_chain_operator"},
        )

    def test_observe_mode_returns_raw_response_but_records_repair(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":\"powershell.exe -Command \\\"Get-Location\\\"\"}",
                }
            ],
        }

        with patch("open_gate.proxy.post_json", return_value=(200, response)):
            result = forward_responses_request(
                request_body=self.request("Run the command."),
                upstream_base_url="http://upstream.invalid/v1",
                api_key="sk-test",
                timeout=1.0,
                normalization_mode="observe",
            )

        self.assertEqual(result.returned_response["output"][0]["arguments"], response["output"][0]["arguments"])
        self.assertEqual(
            result.normalized_response["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-Location\"]}",
        )
        self.assertEqual(result.normalization["mode"], "observe")

    def test_detects_codex_history_that_needs_flattening_for_vllm(self) -> None:
        input_items = [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create a file."}]},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "I will patch it."}]},
            {"type": "function_call", "name": "apply_patch", "arguments": "{\"patch\":\"...\"}", "call_id": "call_1"},
            {"type": "function_call_output", "call_id": "call_1", "output": "Done"},
        ]

        self.assertTrue(needs_flattened_input(input_items))

    def test_auto_transform_flattens_unsupported_codex_history(self) -> None:
        request = {
            "model": "Qwen3-Coder-Next",
            "tools": TOOLS,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create a file."}]},
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "I will patch it."}]},
                {"type": "function_call", "name": "apply_patch", "arguments": "{\"patch\":\"...\"}", "call_id": "call_1"},
                {"type": "function_call_output", "call_id": "call_1", "output": "Done"},
            ],
        }

        details = transform_upstream_request(request, "auto")

        self.assertEqual(details["input_mode"], "flattened")
        self.assertIsInstance(request["input"], str)
        self.assertTrue(details["tool_guardrails_injected"])
        self.assertIn("Open Gate tool discipline", request["input"])
        self.assertIn("web_search", request["input"])
        self.assertIn("assistant tool call apply_patch call_1", request["input"])
        self.assertIn("tool output call_1", request["input"])

    def test_native_transform_injects_tool_guardrails(self) -> None:
        request = {
            "model": "GLM-4.7-Flash",
            "tools": TOOLS,
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Existing instructions."}],
                },
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Look at a URL."}]},
            ],
        }

        details = transform_upstream_request(request, "auto")

        self.assertEqual(details["input_mode"], "native")
        self.assertTrue(details["tool_guardrails_injected"])
        self.assertEqual(request["input"][1]["role"], "developer")
        guard_text = request["input"][1]["content"][0]["text"]
        self.assertIn("Open Gate tool discipline", guard_text)
        self.assertIn("The only callable tools", guard_text)
        self.assertIn("web_search", guard_text)
        self.assertIn("There is no web_search/browser tool here", guard_text)

    def test_native_transform_does_not_duplicate_tool_guardrails(self) -> None:
        request = {
            "model": "GLM-4.7-Flash",
            "tools": TOOLS,
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Open Gate tool discipline:\n- Already present."}],
                },
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue."}]},
            ],
        }

        details = transform_upstream_request(request, "auto")

        self.assertFalse(details["tool_guardrails_injected"])
        self.assertEqual(len(request["input"]), 2)

    def test_spoon_policy_forces_flattening_and_compacts_history(self) -> None:
        request = {
            "model": "Qwen3-Coder-Next",
            "tools": TOOLS,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create an HTML page."}]},
                {
                    "type": "function_call",
                    "name": "shell",
                    "call_id": "call_bad",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"cd glm-test && uv run playwright install chromium\"]}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_bad",
                    "output": "A" * 9000 + "\nFailed to spawn: playwright\n",
                },
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Now finish the page quickly."}]},
            ],
        }

        details = transform_upstream_request(
            request,
            "auto",
            context_policy="spoon",
            context_max_chars=4000,
            context_recent_items=1,
        )

        self.assertEqual(details["input_mode"], "flattened")
        self.assertEqual(details["reason"], "unsupported_responses_history")
        self.assertEqual(details["context_policy"], "spoon")
        self.assertLessEqual(len(request["input"]), 4000)
        self.assertIn("Open Gate context digest", request["input"])
        self.assertIn("Now finish the page quickly.", request["input"])
        self.assertIn("apply_patch is not available", request["input"])
        self.assertNotIn("A" * 1000, request["input"])
        self.assertGreater(details["dropped_context_chars"], 0)

    def test_spoon_policy_preserves_durable_user_constraints(self) -> None:
        input_items = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Goal:\n- Everything must be contained in index.html.\n- No frameworks.\n- Keep performance reasonable.",
                    }
                ],
            },
            {"type": "function_call_output", "call_id": "old", "output": "x" * 8000},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue."}]},
        ]

        result = compile_responses_context(
            input_items,
            context_policy="spoon",
            max_chars=4000,
            recent_items=1,
            tools=TOOLS,
        )

        self.assertIn("Durable user constraints", result.text)
        self.assertIn("Everything must be contained in index.html.", result.text)
        self.assertIn("No frameworks.", result.text)
        self.assertIn("Keep performance reasonable.", result.text)

    def test_spoon_policy_summarizes_large_recent_tool_output(self) -> None:
        result = compile_responses_context(
            [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create index.html."}]},
                {"type": "function_call_output", "call_id": "call_echo", "output": "<!DOCTYPE html>" + ("x" * 6000)},
            ],
            context_policy="spoon",
            max_chars=4000,
            recent_items=2,
            tools=TOOLS,
        )

        self.assertIn("tool output call_echo chars=", result.text)
        self.assertNotIn("x" * 1000, result.text)

    def test_spoon_policy_keeps_failure_constraints(self) -> None:
        input_items = [
            {
                "type": "function_call",
                "name": "shell",
                "call_id": "call_bad",
                "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"cd glm-test && uv run playwright install chromium\"]}",
            },
            {
                "type": "function_call_output",
                "call_id": "call_bad",
                "output": "unsupported call: write_file\nFailed to spawn: playwright\n",
            },
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue."}]},
        ]

        result = compile_responses_context(
            input_items,
            context_policy="spoon",
            max_chars=4000,
            recent_items=1,
            tools=TOOLS,
        )

        self.assertIn("PowerShell does not accept &&", result.text)
        self.assertIn("workdir", result.text)
        self.assertIn("Tool 'write_file' was unsupported", result.text)
        self.assertIn("Playwright executable was unavailable", result.text)
        self.assertIn("Continue.", result.text)

    def test_request_diet_digests_large_instructions_and_tools(self) -> None:
        request = {
            "model": "GLM-4.7-Flash",
            "instructions": "Codex instructions. " * 900,
            "tools": [
                {
                    "type": "function",
                    "name": "shell",
                    "description": "Run shell commands. " * 1000,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "array",
                                "description": "Command arguments. " * 500,
                                "items": {"type": "string", "description": "One argument. " * 200},
                            }
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                }
            ],
            "input": "Create index.html.",
        }

        details = apply_request_diet(request, instruction_policy="auto", tool_schema_policy="auto")

        self.assertTrue(details["instruction_diet_applied"])
        self.assertTrue(details["tool_schema_diet_applied"])
        self.assertLess(details["instructions_sent_chars"], details["instructions_original_chars"])
        self.assertLess(details["tools_sent_chars"], details["tools_original_chars"])
        self.assertTrue(request["instructions"].startswith("Open Gate instruction digest"))
        self.assertLessEqual(len(request["tools"][0]["description"]), 220)
        command_schema = request["tools"][0]["parameters"]["properties"]["command"]
        self.assertLessEqual(len(command_schema["description"]), 120)
        self.assertEqual(command_schema["items"]["type"], "string")

    def test_transform_applies_request_diet_after_spooning(self) -> None:
        request = {
            "model": "GLM-4.7-Flash",
            "instructions": "Large instruction block. " * 900,
            "tools": [
                {
                    "type": "function",
                    "name": "shell",
                    "description": "Run shell commands. " * 1000,
                    "parameters": TOOLS[0]["parameters"],
                }
            ],
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create index.html."}]},
                {"type": "function_call_output", "call_id": "call_web", "output": "<!DOCTYPE html>" + ("x" * 10000)},
            ],
        }

        details = transform_upstream_request(request, "auto", context_policy="spoon", context_max_chars=60000)

        self.assertEqual(details["input_mode"], "flattened")
        self.assertTrue(details["instruction_diet_applied"])
        self.assertTrue(details["tool_schema_diet_applied"])
        self.assertLess(details["upstream_body_chars"], details["instructions_original_chars"] + details["tools_original_chars"] + 12000)
        self.assertIn("Open Gate context digest", request["input"])
        self.assertNotIn("x" * 1000, request["input"])

    def test_timeout_returns_proxy_result_with_transformed_request(self) -> None:
        request = self.request("Run a slow command.")
        request["instructions"] = "Large instruction block. " * 900

        with patch("open_gate.proxy.urlopen", side_effect=TimeoutError("timed out")):
            result = forward_responses_request(
                request_body=request,
                upstream_base_url="http://upstream.invalid/v1",
                api_key="sk-test",
                timeout=0.01,
                normalization_mode="repair",
            )

        self.assertEqual(result.upstream_status, 599)
        self.assertEqual(result.upstream_response["error"]["type"], "TimeoutError")
        self.assertIsNotNone(result.upstream_request)
        self.assertIsNotNone(result.upstream_transform)
        self.assertTrue(result.upstream_transform["instruction_diet_applied"])

    def test_forward_request_overrides_client_model_for_upstream(self) -> None:
        response = {"id": "resp_test", "output": []}
        request = self.request("Say hi.")
        request["model"] = "stale-codex-profile-model"

        with patch("open_gate.proxy.post_json", return_value=(200, response)):
            result = forward_responses_request(
                request_body=request,
                upstream_base_url="http://upstream.invalid/v1",
                api_key="sk-test",
                timeout=1.0,
                normalization_mode="repair",
                upstream_model="GLM-4.7-Flash",
            )

        self.assertEqual(result.upstream_request["model"], "GLM-4.7-Flash")
        self.assertEqual(result.upstream_transform["requested_model"], "stale-codex-profile-model")
        self.assertEqual(result.upstream_transform["upstream_model"], "GLM-4.7-Flash")
        self.assertTrue(result.upstream_transform["model_overridden"])

    def test_proxy_error_response_is_completed_to_avoid_codex_retry_storms(self) -> None:
        response = build_proxy_error_response(
            {"model": "Qwen3-Coder-Next"},
            599,
            {"error": {"message": "Connection timed out", "type": "upstream_connection_error"}},
        )

        self.assertEqual(response["status"], "completed")
        self.assertIsNone(response["error"])
        self.assertIn("Do not retry the same route", response["output"][0]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
