from __future__ import annotations

import unittest

from open_gate.benchmark import score_response


TOOLS = [
    {
        "type": "function",
        "name": "shell",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["command"],
        },
    }
]


class BenchmarkScoringTests(unittest.TestCase):
    def test_structured_tool_call_is_strict_success(self) -> None:
        response = {
            "output": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"]}",
                }
            ]
        }

        score = score_response(response, TOOLS, {"expected_tool": "shell"}, "responses")

        self.assertTrue(score["strict_success"])
        self.assertFalse(score["leaked"])
        self.assertFalse(score["missed_tool_call"])
        self.assertEqual(score["missing_expected_tools"], [])

    def test_leaked_tool_call_is_failure_but_proxy_recoverable(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "<tool_call>{\"name\":\"shell\",\"arguments\":{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"]}}</tool_call>",
                        }
                    ],
                }
            ]
        }

        score = score_response(response, TOOLS, {"expected_tool": "shell"}, "responses")

        self.assertFalse(score["strict_success"])
        self.assertTrue(score["failure"])
        self.assertTrue(score["leaked"])
        self.assertTrue(score["proxy_recoverable"])

    def test_glm_leaked_tool_call_is_proxy_recoverable(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '<tool_call>shell<arg_key>command</arg_key><arg_value>["powershell.exe", "-Command", "Get-ChildItem -Force"]</arg_value></tool_call>',
                        }
                    ],
                }
            ]
        }

        score = score_response(response, TOOLS, {"expected_tool": "shell"}, "responses")

        self.assertFalse(score["strict_success"])
        self.assertTrue(score["leaked"])
        self.assertTrue(score["proxy_recoverable"])
        self.assertEqual(score["leaked_tool_names"], ["shell"])

    def test_tool_syntax_inside_arguments_is_not_strict_success(self) -> None:
        response = {
            "output": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"echo recipient_name=functions.shell\"]}",
                }
            ]
        }

        score = score_response(response, TOOLS, {"expected_tool": "shell"}, "responses")

        self.assertFalse(score["strict_success"])
        self.assertTrue(score["argument_leak"])

    def test_invalid_argument_type_is_failure(self) -> None:
        response = {
            "output": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":\"Get-ChildItem -Force\"}",
                }
            ]
        }

        score = score_response(response, TOOLS, {"expected_tool": "shell"}, "responses")

        self.assertFalse(score["strict_success"])
        self.assertTrue(score["invalid_tool_call"])

    def test_nested_powershell_is_command_quality_failure(self) -> None:
        response = {
            "output": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"powershell.exe -Command \\\"Get-ChildItem -Force\\\"\"]}",
                }
            ]
        }

        score = score_response(response, TOOLS, {"expected_tool": "shell"}, "responses")

        self.assertFalse(score["strict_success"])
        self.assertTrue(score["command_quality_issue"])
        self.assertEqual(score["command_quality_issues"][0]["issue"], "nested_powershell")

    def test_no_tool_case_fails_on_over_eager_tool(self) -> None:
        response = {
            "output": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"]}",
                }
            ]
        }

        score = score_response(response, TOOLS, {"expect_no_tool": True}, "responses")

        self.assertFalse(score["strict_success"])
        self.assertTrue(score["over_eager_tool"])

    def test_no_tool_case_succeeds_with_clean_text(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "The answer is 42."}],
                }
            ]
        }

        score = score_response(response, TOOLS, {"expect_no_tool": True}, "responses")

        self.assertTrue(score["strict_success"])
        self.assertFalse(score["over_eager_tool"])

    def test_reasoning_leak_is_failure(self) -> None:
        response = {
            "reasoning": {
                "summary": [
                    {
                        "text": "<tool_call>{\"name\":\"shell\",\"arguments\":{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"]}}</tool_call>"
                    }
                ]
            },
            "output": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-ChildItem -Force\"]}",
                }
            ],
        }

        score = score_response(response, TOOLS, {"expected_tool": "shell"}, "responses")

        self.assertFalse(score["strict_success"])
        self.assertTrue(score["reasoning_leaked"])


if __name__ == "__main__":
    unittest.main()
