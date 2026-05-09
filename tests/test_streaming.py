from __future__ import annotations

import json
import unittest

from open_gate.streaming import response_stream_events, serialise_sse


class StreamingTests(unittest.TestCase):
    def test_message_stream_contains_text_lifecycle(self) -> None:
        events = response_stream_events(
            {
                "id": "resp_test",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hello", "annotations": []}],
                    }
                ],
            }
        )
        names = [name for name, _payload in events]

        self.assertEqual(names[0], "response.created")
        self.assertIn("response.output_text.delta", names)
        self.assertIn("response.output_text.done", names)
        self.assertEqual(names[-1], "response.completed")

    def test_function_call_stream_contains_argument_lifecycle(self) -> None:
        events = response_stream_events(
            {
                "id": "resp_test",
                "output": [
                    {
                        "id": "fc_test",
                        "type": "function_call",
                        "status": "completed",
                        "name": "shell",
                        "call_id": "call_test",
                        "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-Location\"]}",
                    }
                ],
            }
        )
        names = [name for name, _payload in events]

        self.assertIn("response.function_call_arguments.delta", names)
        self.assertIn("response.function_call_arguments.done", names)
        self.assertLess(names.index("response.function_call_arguments.done"), names.index("response.output_item.done"))

    def test_serialise_sse_outputs_event_and_data_lines(self) -> None:
        raw = serialise_sse(response_stream_events({"id": "resp_test", "output": []}))

        self.assertIn(b"event: response.created\n", raw)
        self.assertIn(b"data: ", raw)
        first_data = raw.split(b"data: ", 1)[1].split(b"\n\n", 1)[0]
        self.assertEqual(json.loads(first_data)["type"], "response.created")


if __name__ == "__main__":
    unittest.main()
