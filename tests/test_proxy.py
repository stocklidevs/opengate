from __future__ import annotations

import unittest
from unittest.mock import patch

from open_gate.proxy import forward_responses_request, needs_flattened_input, normalize_responses_response, transform_upstream_request


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
        self.assertIn("assistant tool call apply_patch call_1", request["input"])
        self.assertIn("tool output call_1", request["input"])


if __name__ == "__main__":
    unittest.main()
