from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from open_gate.codex_report import build_report


class CodexReportTests(unittest.TestCase):
    def test_report_counts_repairs_and_clean_returned_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_dir = root / "captures"
            capture_dir.mkdir()
            codex_dir = root / "codex"
            codex_dir.mkdir()
            (capture_dir / "sample-proxy.json").write_text(
                json.dumps(
                    {
                        "captured_at": "2026-05-09T00:00:00+00:00",
                        "kind": "proxy_exchange",
                        "normalization_mode": "repair",
                        "timing": {
                            "duration_seconds": 12.5,
                            "stream_heartbeats": 2,
                        },
                        "request": {
                            "stream": True,
                            "tools": [
                                {
                                    "type": "function",
                                    "name": "shell",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"command": {"type": "array"}},
                                        "required": ["command"],
                                    },
                                }
                            ],
                        },
                        "upstream": {
                            "status": 200,
                            "transform": {"input_mode": "flattened", "reason": "unsupported_responses_history"},
                            "response": {
                                "output": [
                                    {
                                        "type": "function_call",
                                        "name": "shell",
                                        "arguments": "{\"command\":\"powershell.exe -Command \\\"Get-Location\\\"\"}",
                                    }
                                ]
                            },
                        },
                        "normalization": {
                            "mode": "repair",
                            "structured_argument_repairs": [{"tool": "shell"}],
                            "stripped_text_items": 0,
                        },
                        "response": {
                            "output": [
                                {
                                    "type": "function_call",
                                    "name": "shell",
                                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Get-Location\"]}",
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            (codex_dir / "case.jsonl").write_text(
                "\n".join(
                    [
                        '{"type":"turn.started"}',
                        '{"type":"item.completed","item":{"type":"command_execution","status":"completed"}}',
                        '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}',
                        '{"type":"turn.completed"}',
                    ]
                ),
                encoding="utf-8",
            )

            report = build_report(capture_dir, codex_dir)

        self.assertEqual(report["summary"]["proxy_exchanges"], 1)
        self.assertEqual(report["summary"]["flattened_upstream_requests"], 1)
        self.assertEqual(report["summary"]["stream_heartbeats"], 2)
        self.assertEqual(report["summary"]["max_proxy_duration_seconds"], 12.5)
        self.assertEqual(report["summary"]["structured_argument_repairs"], 1)
        self.assertEqual(report["summary"]["returned_command_quality_issues"], 0)
        self.assertEqual(report["summary"]["codex_turns_completed"], 1)


if __name__ == "__main__":
    unittest.main()
