from __future__ import annotations

import base64
import json
import re
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
SHELL_WITH_APPROVAL_TOOL = {
    "type": "function",
    "name": "shell",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "array", "items": {"type": "string"}},
            "justification": {"type": "string"},
            "prefix_rule": {"type": "array", "items": {"type": "string"}},
            "sandbox_permissions": {"type": "string"},
            "workdir": {"type": "string"},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
}
UPDATE_PLAN_TOOL = {
    "type": "function",
    "name": "update_plan",
    "parameters": {
        "type": "object",
        "properties": {
            "explanation": {"type": "string"},
            "plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["step", "status"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["plan"],
        "additionalProperties": False,
    },
}
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
WEB_SEARCH_TOOL = {"type": "web_search"}


def diagnostic_text(arguments: str | dict) -> str:
    if isinstance(arguments, dict):
        parsed = arguments
        raw = json.dumps(arguments)
    else:
        raw = arguments
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
    command = parsed.get("command") if isinstance(parsed, dict) else None
    plan = parsed.get("plan") if isinstance(parsed, dict) else None
    if isinstance(plan, list):
        steps = [str(item.get("step")) for item in plan if isinstance(item, dict)]
        return "\n".join([raw, str(parsed.get("explanation") or ""), *steps])
    if not isinstance(command, list):
        return raw
    text = raw
    lower = [part.lower() if isinstance(part, str) else "" for part in command]
    if "-encodedcommand" not in lower:
        return text
    index = lower.index("-encodedcommand")
    if index + 1 >= len(command) or not isinstance(command[index + 1], str):
        return text
    try:
        script = base64.b64decode(command[index + 1]).decode("utf-16le")
    except UnicodeDecodeError:
        return text
    text += "\n" + script
    match = re.search(r"FromBase64String\('([^']+)'\)", script)
    if match:
        text += "\n" + base64.b64decode(match.group(1)).decode("utf-8")
    return text


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

    def test_promotes_fenced_tool_spec_wrapper(self) -> None:
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
                            "text": (
                                "Before running it, place the tool call in a fenced ```json block for inspection.\n\n"
                                "Tool call structure:\n"
                                "```json\n"
                                '{"toolSpec":{"name":"shell","args":{"command":["powershell.exe","-Command","Get-Location"],"workdir":"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}}}\n'
                                "```<channel|>```json\n"
                                '{"toolSpec":{"name":"shell","args":{"command":["powershell.exe","-Command","Get-Location"],"workdir":"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}}}\n'
                                "```"
                            ),
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Run Get-Location with shell."))

        function_call = next(item for item in normalized["output"] if item.get("type") == "function_call")
        self.assertEqual(function_call["name"], "shell")
        self.assertNotIn("toolSpec", normalized["output"][0]["content"][0]["text"])
        self.assertNotIn("<channel|>", normalized["output"][0]["content"][0]["text"])
        self.assertEqual(details["promoted_tool_calls"][0]["source"], "fenced_json")
        self.assertEqual(details["stripped_text_items"], 1)

    def test_strips_channel_delimited_assistant_answer_suffix(self) -> None:
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
                            "text": (
                                "The user asked me to inspect the current directory.\n"
                                "I should answer with the number I saw.\n"
                                "<channel|>I saw 4 entries in the current directory."
                            ),
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("How many entries?"))

        self.assertEqual(
            normalized["output"][0]["content"][0]["text"],
            "I saw 4 entries in the current directory.",
        )
        self.assertEqual(details["channel_delimiter_text_repairs"][0]["after"], "I saw 4 entries in the current directory.")
        self.assertEqual(details["stripped_text_items"], 0)

    def test_leaves_channel_delimiter_without_answer_suffix(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "I will answer now.<channel|>   "}],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Say hello."))

        self.assertEqual(normalized["output"][0]["content"][0]["text"], "I will answer now.<channel|>   ")
        self.assertEqual(details["channel_delimiter_text_repairs"], [])

    def test_does_not_strip_channel_delimiter_from_reasoning_item(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "reasoning_test",
                    "type": "reasoning",
                    "content": [{"type": "reasoning_text", "text": "private analysis<channel|>visible suffix"}],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Think."))

        self.assertEqual(
            normalized["output"][0]["content"][0]["text"],
            "private analysis<channel|>visible suffix",
        )
        self.assertEqual(details["channel_delimiter_text_repairs"], [])

    def test_channel_suffix_gemma_skill_tool_call_becomes_diagnostic(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "I should plan before writing files."
                                '<channel|><|tool_call>call:superpowers:brainstorming'
                                '{message:<|"|>Plan the implementation.<|"|>}<tool_call|>'
                            ),
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create the requested files."))
        message_text = normalized["output"][0]["content"][0]["text"]
        diagnostic_call = normalized["output"][1]
        diagnostic = diagnostic_text(diagnostic_call["arguments"])

        self.assertEqual(message_text, "")
        self.assertEqual(diagnostic_call["type"], "function_call")
        self.assertEqual(diagnostic_call["name"], "shell")
        self.assertIn("reasoning only and no tool call", diagnostic)
        self.assertEqual(details["channel_delimiter_text_repairs"][0]["after"], '<|tool_call>call:superpowers:brainstorming{message:<|"|>Plan the implementation.<|"|>}<tool_call|>')
        self.assertEqual(details["stripped_text_items"], 1)
        self.assertEqual(details["invalid_tool_calls"][0]["name"], "superpowers:brainstorming")
        self.assertNotIn("<|tool_call>", json.dumps(normalized))

    def test_channel_suffix_codex_transcript_tool_call_is_promoted(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "I will create the file."
                                "<channel|>assistant tool call shell chatcmpl-tool-8e5c932fb4903995:\n"
                                '{"command":["powershell.exe","-Command","Set-Content -Path sample.txt -Value ok"]}\n\n'
                                "tool output chatcmpl-tool-8e5c932fb4903995:\n"
                                '{"output":"","metadata":{"exit_code":0,"duration_seconds":0.4}}'
                            ),
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create sample.txt."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertEqual(details["promoted_tool_calls"][0]["source"], "codex_transcript_tool_call")
        self.assertEqual(details["stripped_text_items"], 1)
        self.assertNotIn("assistant tool call", json.dumps(normalized))
        self.assertNotIn("tool output", json.dumps(normalized))

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

    def test_promotes_deepseek_v3_delimited_tool_call(self) -> None:
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
                            "text": (
                                '<\uff5ctool\u2581call\u2581begin\uff5c>function<\uff5ctool\u2581sep\uff5c>shell\n'
                                "```json\n"
                                '{"command": ["powershell.exe", "-Command", "Get-ChildItem -Force"], "workdir": "C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"}\n'
                                "```"
                                '<\uff5ctool\u2581call\u2581end\uff5c><\uff5ctool\u2581calls\u2581end\uff5c>\n'
                                '<\uff5ctool\u2581outputs\u2581begin\uff5c><\uff5ctool\u2581output\u2581begin\uff5c>{"output":"Directory"}'
                                '<\uff5ctool\u2581output\u2581end\uff5c><\uff5ctool\u2581outputs\u2581end\uff5c>\n'
                                "The directory contains files."
                            ),
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Inspect the workspace with shell."))

        function_call = next(item for item in normalized["output"] if item.get("type") == "function_call")
        self.assertEqual(function_call["name"], "shell")
        self.assertIn("Get-ChildItem -Force", function_call["arguments"])
        self.assertNotIn("\u2581", normalized["output"][0]["content"][0]["text"])
        self.assertEqual(details["promoted_tool_calls"][0]["source"], "deepseek_v3_tool_call")
        self.assertEqual(details["stripped_text_items"], 1)

    def test_routes_text_web_search_alias_to_bounded_shell_fetch(self) -> None:
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
                            "text": (
                                "I'll inspect it."
                                "<tool_call>web_search<arg_key>external_web_access</arg_key>"
                                "<arg_value>true</arg_value></tool_call>"
                            ),
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Look at https://styles.refero.design/ before building.", [*TOOLS, WEB_SEARCH_TOOL]),
        )

        function_call = next(item for item in normalized["output"] if item.get("type") == "function_call")
        self.assertEqual(function_call["name"], "shell")
        arguments = json.loads(function_call["arguments"])
        self.assertIn("Invoke-WebRequest -Uri $uri", arguments["command"][2])
        self.assertIn("https://styles.refero.design/", arguments["command"][2])
        self.assertEqual(details["text_tool_call_repairs"][0]["reason"], "hosted_web_tool_to_shell_metadata")
        self.assertEqual(details["promoted_tool_calls"][0]["name"], "shell")
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_routes_structured_web_search_to_bounded_shell_fetch(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "web_search",
                    "arguments": '{"query":"https://styles.refero.design/\\\\\\"}',
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Look at https://styles.refero.design/ before building.", [*TOOLS, WEB_SEARCH_TOOL]),
        )

        self.assertEqual(normalized["output"][0]["name"], "shell")
        arguments = json.loads(normalized["output"][0]["arguments"])
        self.assertIn("https://styles.refero.design/", arguments["command"][2])
        self.assertNotIn('https://styles.refero.design/\\', arguments["command"][2])
        self.assertEqual(details["web_tool_alias_repairs"][0]["reason"], "hosted_web_tool_to_shell_metadata")
        self.assertEqual(details["command_quality_suppressed_structured_calls"], [])

    def test_routes_artifact_web_search_to_bounded_shell_fetch(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "web_search",
                    "arguments": '{"query":"https://styles.refero.design/style/example"}',
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Look at the reference, then create index.html.", [*TOOLS, UPDATE_PLAN_TOOL, WEB_SEARCH_TOOL]),
        )

        self.assertEqual(normalized["output"][0]["name"], "shell")
        arguments = json.loads(normalized["output"][0]["arguments"])
        self.assertIn("Invoke-WebRequest -Uri $uri", arguments["command"][2])
        self.assertIn("https://styles.refero.design/style/example", arguments["command"][2])
        self.assertEqual(details["web_tool_alias_repairs"][0]["reason"], "hosted_web_tool_to_shell_metadata")

    def test_routes_site_query_web_search_to_bounded_shell_fetch(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "web_search",
                    "arguments": '{"query":"site:styles.refero.design"}',
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Summarize https://styles.refero.design/.", [*TOOLS, WEB_SEARCH_TOOL]),
        )

        self.assertEqual(normalized["output"][0]["name"], "shell")
        arguments = json.loads(normalized["output"][0]["arguments"])
        self.assertIn("https://styles.refero.design/", arguments["command"][2])
        self.assertEqual(details["web_tool_alias_repairs"][0]["after_tool"], "shell")
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_no_web_search_tool_keeps_shell_url_guard(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": (
                        '{"command":["powershell.exe","-Command",'
                        '"Invoke-WebRequest -Uri \'https://styles.refero.design/\' -UseBasicParsing"]}'
                    ),
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request("Look at https://styles.refero.design/ before building."),
        )

        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertEqual(details["web_tool_alias_repairs"], [])

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
        arguments = diagnostic_text(normalized["output"][0]["arguments"])

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
        diagnostic = diagnostic_text(normalized["output"][0]["arguments"])

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Open Gate blocked an invalid shell command (malformed_json_array_command)", diagnostic)
        self.assertIn("Continue with a smaller valid structured tool call", diagnostic)
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

    def test_repairs_promoted_direct_powershell_alias(self) -> None:
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
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["dir"]</arg_value></tool_call>',
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Inspect the directory."))

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"dir\"]}",
        )
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_repairs_structured_single_powershell_pipeline_without_literal_quotes(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"Get-ChildItem | Measure-Object -Line\"],\"workdir\":\"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test\"}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Inspect the directory."))

        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem | Measure-Object -Line\"],\"workdir\":\"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test\"}",
        )
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_repairs_structured_single_powershell_script_with_dot_path_argument(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"Get-ChildItem -Path . | Measure-Object\"],\"workdir\":\"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test\"}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Inspect the directory."))

        self.assertEqual(
            normalized["output"][0]["arguments"],
            "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Path . | Measure-Object\"],\"workdir\":\"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test\"}",
        )
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_suppresses_structured_escaped_json_tail_command(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": json.dumps(
                        {
                            "command": [
                                'powershell.exe","-Command","\'(Get-ChildItem).Count\'"],"workdir":"C:\\\\Users\\\\example\\\\source\\\\repos\\\\glm-test"'
                            ]
                        }
                    ),
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Inspect the directory."))
        arguments = diagnostic_text(normalized["output"][0]["arguments"])

        self.assertIn("Open Gate blocked an invalid shell command (malformed_embedded_json_command_array)", arguments)
        self.assertEqual(
            {issue["issue"] for issue in details["command_quality_suppressed_structured_calls"][0]["command_quality_errors"]},
            {"malformed_embedded_json_command_array"},
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
        arguments = diagnostic_text(normalized["output"][0]["arguments"])

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
        arguments = diagnostic_text(normalized["output"][0]["arguments"])

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
        arguments = diagnostic_text(normalized["output"][0]["arguments"])

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
        arguments = diagnostic_text(normalized["output"][0]["arguments"])

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Open Gate blocked an invalid shell command (unbounded_web_fetch)", arguments)
        self.assertIn("Do not retry that route", arguments)
        self.assertEqual(details["command_quality_suppressed_structured_calls"][0]["name"], "shell")
        self.assertIn("quarantined_as", details["command_quality_suppressed_structured_calls"][0])
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_quarantines_structured_command_quality_error_even_with_visible_message(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Let me inspect the site first."}],
                },
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"(Invoke-WebRequest -Uri 'https://styles.refero.design/' -UseBasicParsing -TimeoutSec 10).Content.Substring(0,3000)\"],\"timeout_ms\":15000}",
                },
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Build the page."))

        self.assertEqual(normalized["output"][0]["type"], "message")
        self.assertEqual(normalized["output"][1]["type"], "function_call")
        self.assertIn(
            "Open Gate blocked an invalid shell command (unbounded_web_fetch)",
            diagnostic_text(normalized["output"][1]["arguments"]),
        )
        self.assertEqual(details["command_quality_suppressed_structured_calls"][0]["name"], "shell")
        self.assertIn("quarantined_as", details["command_quality_suppressed_structured_calls"][0])
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_prefers_shell_for_structured_command_quality_diagnostic_when_update_plan_exists(self) -> None:
        request = self.request_with_tools("Inspect the reference site.", [*TOOLS, UPDATE_PLAN_TOOL])
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

        normalized, details = normalize_responses_response(response, request)

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertIn("Open Gate blocked an invalid shell command", diagnostic_text(normalized["output"][0]["arguments"]))
        self.assertIn("quarantined_as", details["command_quality_suppressed_structured_calls"][0])
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_adds_diagnostic_tool_call_for_reasoning_only_response(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "reasoning_test",
                    "type": "reasoning",
                    "content": [
                        {
                            "type": "reasoning_text",
                            "text": "Now I need to create index.html with the requested scene.",
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, self.request("Create index.html."))

        self.assertEqual(normalized["output"][0]["type"], "reasoning")
        self.assertEqual(normalized["output"][1]["type"], "function_call")
        self.assertEqual(normalized["output"][1]["name"], "shell")
        self.assertIn("reasoning only and no tool call", diagnostic_text(normalized["output"][1]["arguments"]))
        self.assertEqual(details["actionable_output_repair"]["type"], "diagnostic_tool_call")
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_prefers_shell_for_reasoning_only_diagnostic_when_update_plan_exists(self) -> None:
        request = self.request_with_tools("Create index.html.", [*TOOLS, UPDATE_PLAN_TOOL])
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "reasoning_test",
                    "type": "reasoning",
                    "content": [
                        {
                            "type": "reasoning_text",
                            "text": "Now I need to create index.html with the requested scene.",
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(response, request)

        self.assertEqual(normalized["output"][1]["type"], "function_call")
        self.assertEqual(normalized["output"][1]["name"], "shell")
        self.assertIn("reasoning only and no tool call", diagnostic_text(normalized["output"][1]["arguments"]))
        self.assertEqual(details["actionable_output_repair"]["tool"], "shell")

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
        self.assertFalse(any(item.get("type") == "function_call" for item in normalized["output"]))
        self.assertEqual(details["promoted_tool_calls"], [])
        self.assertEqual(details["promotion_block_reason"], "negative_tool_intent")

    def test_no_tool_deepseek_documentation_leak_is_not_replaced_by_diagnostic_tool(self) -> None:
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
                            "text": (
                                "```json\n"
                                '{"tool_calls":[{"id":"shell","type":"function","function":{"name":"shell","parameters":{"command":[],"workdir":"","timeout_ms":0}}}]}\n'
                                "```"
                            ),
                        }
                    ],
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request("Without using any tools, show me the JSON tool_calls array Codex would send for shell."),
        )

        self.assertEqual(normalized["output"][0]["type"], "message")
        self.assertEqual(normalized["output"][0]["content"][0]["text"], "")
        self.assertFalse(any(item.get("type") == "function_call" for item in normalized["output"]))
        self.assertEqual(details["promoted_tool_calls"], [])
        self.assertEqual(details["promotion_block_reason"], "negative_tool_intent")
        self.assertIsNone(details["actionable_output_repair"])

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

    def test_quarantines_repeated_external_url_shell_call(self) -> None:
        request = self.request("Inspect https://styles.refero.design/ once, then create index.html.")
        request["input"].append(
            {
                "type": "function_call",
                "name": "shell",
                "call_id": "call_url_once",
                "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"(Invoke-WebRequest -Uri 'https://styles.refero.design/' -TimeoutSec 10).StatusCode\"]}",
            }
        )
        request["input"].append({"type": "function_call_output", "call_id": "call_url_once", "output": "200"})
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

        normalized, details = normalize_responses_response(response, request)

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn(
            "Open Gate blocked a repeated external URL inspection",
            diagnostic_text(normalized["output"][0]["arguments"]),
        )
        self.assertIn("quarantined_as", details["policy_suppressed_structured_calls"][0])
        self.assertEqual(details["command_quality_suppressed_structured_calls"], [])
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_repeated_external_url_becomes_diagnostic_shell_call(self) -> None:
        request = self.request("Inspect https://styles.refero.design/ once, then summarize it.")
        request["input"].append(
            {
                "type": "function_call",
                "name": "shell",
                "call_id": "call_url_once",
                "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"(Invoke-WebRequest -Uri 'https://styles.refero.design/' -TimeoutSec 10).StatusCode\"]}",
            }
        )
        request["input"].append(
            {
                "type": "function_call_output",
                "call_id": "call_url_once",
                "output": "Open Gate bounded web metadata fetch failed: Unable to connect to the remote server",
            }
        )
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Invoke-WebRequest -Uri 'https://styles.refero.design/' -UseBasicParsing\"]}",
                }
            ],
        }

        normalized, details = normalize_responses_response(response, request)

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertIn("repeated external URL inspection", diagnostic_text(normalized["output"][0]["arguments"]))
        self.assertIn("quarantined_as", details["policy_suppressed_structured_calls"][0])
        self.assertEqual(details["actionable_output_repair"], None)

    def test_prefers_shell_for_repeated_external_url_diagnostic_when_update_plan_exists(self) -> None:
        request = self.request_with_tools(
            "Inspect https://styles.refero.design/ once, then create index.html.",
            [*TOOLS, UPDATE_PLAN_TOOL],
        )
        request["input"].append(
            {
                "type": "function_call",
                "name": "shell",
                "call_id": "call_url_once",
                "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"(Invoke-WebRequest -Uri 'https://styles.refero.design/' -TimeoutSec 10).StatusCode\"]}",
            }
        )
        request["input"].append({"type": "function_call_output", "call_id": "call_url_once", "output": "200"})
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

        normalized, details = normalize_responses_response(response, request)

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertIn(
            "Open Gate blocked a repeated external URL inspection",
            diagnostic_text(normalized["output"][0]["arguments"]),
        )
        self.assertIn("quarantined_as", details["policy_suppressed_structured_calls"][0])

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

    def test_quarantines_executable_only_shell_command_with_metadata(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": json.dumps(
                        {
                            "command": "powershell.exe",
                            "justification": "Fetch reference site metadata",
                            "prefix_rule": ["powershell.exe", "-Command", "(Invoke-Web"],
                            "sandbox_permissions": "require_escalated",
                        }
                    ),
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Create index.html.", [SHELL_WITH_APPROVAL_TOOL]),
        )
        arguments = json.loads(normalized["output"][0]["arguments"])
        diagnostic = diagnostic_text(arguments)

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn("Open Gate blocked an invalid shell command (executable_only_command)", diagnostic)
        self.assertIn("Continue with a smaller valid structured tool call", diagnostic)
        self.assertNotIn("prefix_rule", arguments)
        self.assertNotIn("sandbox_permissions", arguments)
        self.assertNotIn("justification", arguments)
        self.assertEqual(
            {issue["issue"] for issue in details["command_quality_suppressed_structured_calls"][0]["command_quality_errors"]},
            {"executable_only_command"},
        )
        self.assertEqual(details["normalized_command_quality_issues"], [])

    def test_quarantines_malformed_artifact_here_string_shell_command(self) -> None:
        response = {
            "id": "resp_test",
            "output": [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": json.dumps(
                        {
                            "command": "powershell.exe -Command \"Set-Content -LiteralPath 'index.html' -Value @```ENDOFHTML``@ -Encoding UTF8\"",
                            "workdir": "C:\\Users\\example\\source\\repos\\glm-test",
                        }
                    ),
                }
            ],
        }

        normalized, details = normalize_responses_response(
            response,
            self.request_with_tools("Create index.html.", [SHELL_WITH_APPROVAL_TOOL]),
        )
        arguments = json.loads(normalized["output"][0]["arguments"])
        diagnostic = diagnostic_text(arguments)

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertEqual(normalized["output"][0]["name"], "shell")
        self.assertIn("malformed_powershell_here_string", diagnostic)
        self.assertIn("Continue with a smaller valid structured tool call", diagnostic)
        self.assertEqual(
            {issue["issue"] for issue in details["command_quality_suppressed_structured_calls"][0]["command_quality_errors"]},
            {"malformed_powershell_here_string"},
        )
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

        self.assertEqual(normalized["output"][0]["type"], "function_call")
        self.assertIn(
            "Open Gate blocked an invalid shell command (windows_powershell_chain_operator)",
            diagnostic_text(normalized["output"][0]["arguments"]),
        )
        self.assertEqual(
            {issue["issue"] for issue in details["normalized_command_quality_issues"]},
            set(),
        )
        self.assertEqual(
            {issue["issue"] for issue in details["command_quality_suppressed_structured_calls"][0]["command_quality_errors"]},
            {"windows_powershell_chain_operator"},
        )
        self.assertIn("quarantined_as", details["command_quality_suppressed_structured_calls"][0])

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

    def test_native_guardrail_explains_web_search_shell_routing(self) -> None:
        request = {
            "model": "GLM-4.7-Flash",
            "tools": [*TOOLS, WEB_SEARCH_TOOL],
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Look at a URL."}]},
            ],
        }

        details = transform_upstream_request(request, "auto")

        self.assertEqual(details["input_mode"], "native")
        guard_text = request["input"][0]["content"][0]["text"]
        self.assertIn("web_search is hosted by Codex", guard_text)
        self.assertIn("Open Gate converts URL lookups from web_search into bounded shell metadata fetches", guard_text)
        self.assertNotIn("There is no web_search/browser tool here", guard_text)

    def test_auto_transform_flattens_developer_role_when_capability_rejects_it(self) -> None:
        request = {
            "model": "Local-Coder-27B",
            "tools": TOOLS,
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Use structured calls only."}],
                },
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "List files."}]},
            ],
        }

        details = transform_upstream_request(
            request,
            "auto",
            upstream_capabilities={"supports_developer_role": False, "supports_system_role": False},
        )

        self.assertEqual(details["input_mode"], "flattened")
        self.assertEqual(details["reason"], "capability_rejects_developer_role")
        self.assertIsInstance(request["input"], str)
        self.assertIn("developer:", request["input"])

    def test_native_guardrail_uses_user_prefix_when_instruction_roles_are_unsupported(self) -> None:
        request = {
            "model": "Local-Coder-27B",
            "tools": TOOLS,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Look at a URL."}]},
            ],
        }

        details = transform_upstream_request(
            request,
            "auto",
            upstream_capabilities={"supports_developer_role": False, "supports_system_role": False},
        )

        self.assertEqual(details["input_mode"], "native")
        self.assertEqual(details["tool_guardrails_format"], "user_prefix")
        self.assertIn("Open Gate tool discipline", request["input"][0]["content"][0]["text"])

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

    def test_request_diet_preserves_namespace_nested_tools(self) -> None:
        request = {
            "model": "DeepSeek-Coder-V2-Lite-Instruct",
            "tools": [
                TOOLS[0],
                {
                    "type": "namespace",
                    "name": "mcp__node_repl__",
                    "description": "JavaScript execution namespace. " * 200,
                    "tools": [
                        {
                            "type": "function",
                            "name": "js",
                            "description": "Run JavaScript in a persistent Node-backed kernel. " * 400,
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "JavaScript source to execute. " * 200,
                                    },
                                    "timeout_ms": {"type": "integer"},
                                },
                                "required": ["code"],
                                "additionalProperties": False,
                            },
                        },
                        {
                            "type": "function",
                            "name": "js_reset",
                            "description": "Reset the persistent kernel.",
                            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                        },
                    ],
                },
            ],
            "input": "Say hello.",
        }

        details = apply_request_diet(request, instruction_policy="full", tool_schema_policy="compact")

        namespace_tool = request["tools"][1]
        nested_tools = namespace_tool["tools"]
        self.assertTrue(details["tool_schema_diet_applied"])
        self.assertEqual(namespace_tool["type"], "namespace")
        self.assertEqual(namespace_tool["name"], "mcp__node_repl__")
        self.assertEqual([tool["name"] for tool in nested_tools], ["js", "js_reset"])
        self.assertLessEqual(len(namespace_tool["description"]), 220)
        self.assertLessEqual(len(nested_tools[0]["description"]), 220)
        self.assertLessEqual(len(nested_tools[0]["parameters"]["properties"]["code"]["description"]), 120)

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

    def test_forward_request_adds_upstream_output_token_cap(self) -> None:
        response = {"id": "resp_test", "output": []}
        request = self.request("Create index.html.")

        with patch("open_gate.proxy.post_json", return_value=(200, response)):
            result = forward_responses_request(
                request_body=request,
                upstream_base_url="http://upstream.invalid/v1",
                api_key="sk-test",
                timeout=1.0,
                normalization_mode="repair",
                upstream_max_output_tokens=2048,
            )

        self.assertEqual(result.upstream_request["max_output_tokens"], 2048)
        self.assertEqual(result.upstream_transform["upstream_max_output_tokens"], 2048)
        self.assertTrue(result.upstream_transform["max_output_tokens_added"])
        self.assertFalse(result.upstream_transform["max_output_tokens_capped"])

    def test_forward_request_preserves_lower_client_output_token_cap(self) -> None:
        response = {"id": "resp_test", "output": []}
        request = self.request("Create index.html.")
        request["max_output_tokens"] = 512

        with patch("open_gate.proxy.post_json", return_value=(200, response)):
            result = forward_responses_request(
                request_body=request,
                upstream_base_url="http://upstream.invalid/v1",
                api_key="sk-test",
                timeout=1.0,
                normalization_mode="repair",
                upstream_max_output_tokens=2048,
            )

        self.assertEqual(result.upstream_request["max_output_tokens"], 512)
        self.assertEqual(result.upstream_transform["max_output_tokens_sent"], 512)
        self.assertFalse(result.upstream_transform["max_output_tokens_added"])
        self.assertFalse(result.upstream_transform["max_output_tokens_capped"])

    def test_forward_retries_flattened_when_upstream_rejects_native_role(self) -> None:
        request = {
            "model": "Local-Coder-27B",
            "tool_choice": "auto",
            "tools": TOOLS,
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Use structured calls only."}],
                },
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "List files."}]},
            ],
        }
        response = {"id": "resp_test", "output": []}

        with patch(
            "open_gate.proxy.post_json",
            side_effect=[
                (400, {"error": {"message": "Unexpected message role.", "type": "BadRequestError"}}),
                (200, response),
            ],
        ):
            result = forward_responses_request(
                request_body=request,
                upstream_base_url="http://upstream.invalid/v1",
                api_key="sk-test",
                timeout=1.0,
                normalization_mode="repair",
            )

        self.assertEqual(result.upstream_status, 200)
        self.assertEqual(result.upstream_transform["input_mode"], "flattened")
        self.assertEqual(result.upstream_transform["retry_reason"], "upstream_rejected_native_input")
        self.assertEqual(result.upstream_transform["first_attempt"]["status"], 400)
        self.assertIsInstance(result.upstream_request["input"], str)

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
