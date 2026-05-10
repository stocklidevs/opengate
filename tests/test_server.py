from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from open_gate.proxy import ProxyResult
from open_gate.server import CaptureServer, Handler
from open_gate.version import __version__


class ServerStreamingTests(unittest.TestCase):
    def test_health_reports_server_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = CaptureServer(
                ("127.0.0.1", 0),
                Handler,
                {
                    "capture_dir": tmp,
                    "model": "GLM-4.7-Flash",
                    "text": "unused",
                    "fixture": None,
                    "upstream_base_url": "http://upstream.invalid/v1",
                    "upstream_api_key": "sk-test",
                    "upstream_timeout": 120.0,
                    "normalization_mode": "repair",
                    "upstream_input_mode": "auto",
                    "context_policy": "spoon",
                    "context_max_chars": 60000,
                    "context_recent_items": 10,
                    "instruction_policy": "auto",
                    "tool_schema_policy": "auto",
                    "stream_heartbeat_seconds": 0.05,
                    "quiet": True,
                },
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                connection.request("GET", "/health")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                connection.close()
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(response.status, 200)
            self.assertEqual(payload["service"], "open-gate")
            self.assertEqual(payload["version"], __version__)
            self.assertEqual(payload["model"], "GLM-4.7-Flash")
            self.assertEqual(payload["context_policy"], "spoon")
            self.assertEqual(payload["instruction_policy"], "auto")
            self.assertEqual(payload["tool_schema_policy"], "auto")

    def test_streaming_proxy_sends_heartbeat_before_buffered_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            capture_dir = Path(tmp)
            server = CaptureServer(
                ("127.0.0.1", 0),
                Handler,
                {
                    "capture_dir": str(capture_dir),
                    "model": "Qwen3-Coder-Next",
                    "text": "unused",
                    "fixture": None,
                    "upstream_base_url": "http://upstream.invalid/v1",
                    "upstream_api_key": "sk-test",
                    "upstream_timeout": 120.0,
                    "normalization_mode": "repair",
                    "upstream_input_mode": "auto",
                    "context_policy": "full",
                    "context_max_chars": 60000,
                    "context_recent_items": 10,
                    "instruction_policy": "auto",
                    "tool_schema_policy": "auto",
                    "stream_heartbeat_seconds": 0.05,
                    "quiet": True,
                },
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                with patch("open_gate.server.forward_responses_request", side_effect=slow_proxy_result):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    connection.request(
                        "POST",
                        "/v1/responses",
                        body=json.dumps({"model": "Qwen3-Coder-Next", "stream": True, "input": "hello"}),
                        headers={"Content-Type": "application/json"},
                    )
                    response = connection.getresponse()

                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.fp.readline().startswith(b": open-gate waiting for upstream"))
                    rest = response.read()
                    connection.close()
            finally:
                server.shutdown()
                server.server_close()

            self.assertIn(b"event: response.created\n", rest)
            self.assertIn(b"event: response.completed\n", rest)
            capture = json.loads(next(capture_dir.glob("*proxy*.json")).read_text(encoding="utf-8"))
            self.assertGreaterEqual(capture["timing"]["stream_heartbeats"], 1)
            self.assertGreater(capture["timing"]["duration_seconds"], 0)


def slow_proxy_result(**_kwargs: object) -> ProxyResult:
    time.sleep(0.15)
    response = {
        "id": "resp_test",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": "Qwen3-Coder-Next",
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
    return ProxyResult(
        upstream_request={"stream": False},
        upstream_transform={"input_mode": "native", "reason": "compatible_input"},
        upstream_status=200,
        upstream_response=response,
        normalized_response=response,
        returned_response=response,
        normalization={"mode": "repair"},
    )


if __name__ == "__main__":
    unittest.main()
