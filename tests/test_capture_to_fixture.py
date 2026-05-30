from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from open_gate.capture_to_fixture import build_fixture


class CaptureToFixtureTests(unittest.TestCase):
    def test_build_fixture_records_channel_delimiter_repairs(self) -> None:
        capture = {
            "request": {
                "model": "Gemma-4-E4B-IT",
                "input": "Say hello.",
                "tools": [],
            },
            "upstream": {
                "response": {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "private preface<channel|>Hello!",
                                }
                            ],
                        }
                    ]
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            capture_path = Path(tmpdir) / "capture.json"
            capture_path.write_text(json.dumps(capture), encoding="utf-8")

            fixture = build_fixture(capture_path)

        self.assertEqual(fixture["expected"]["minimum_channel_delimiter_text_repairs"], 1)
        self.assertEqual(fixture["observed_after_normalization"]["channel_delimiter_text_repairs"][0]["after"], "Hello!")


if __name__ == "__main__":
    unittest.main()
