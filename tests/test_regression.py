from __future__ import annotations

import json
from pathlib import Path
import unittest

from open_gate.regression import iter_fixture_paths, run_fixture, run_fixture_path


ROOT = Path(__file__).resolve().parents[1]


class RegressionFixtureTests(unittest.TestCase):
    def test_regression_fixtures_replay_cleanly(self) -> None:
        fixtures = iter_fixture_paths([ROOT / "fixtures" / "regressions"])

        self.assertTrue(fixtures)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                result = run_fixture_path(fixture)
                self.assertEqual(result["failures"], [])

    def test_nested_powershell_fixture_repairs_to_single_shell(self) -> None:
        result = run_fixture_path(ROOT / "fixtures" / "regressions" / "qwen_nested_powershell_20260509.json")
        output = result["normalized_output"][0]
        arguments = json.loads(output["arguments"])

        self.assertEqual(
            arguments["command"],
            ["powershell.exe", "-Command", "Get-ChildItem -Force | Measure-Object | Select-Object -ExpandProperty Count"],
        )
        self.assertEqual(result["command_quality_issues"], [])

    def test_expected_absent_fragments_fail_when_text_remains(self) -> None:
        result = run_fixture(
            {
                "name": "absent-fragment-check",
                "request": {},
                "upstream_response": {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "visible answer with banned text",
                                }
                            ],
                        }
                    ],
                },
                "expected": {
                    "expected_absent_fragments": ["banned text"],
                },
            }
        )

        self.assertEqual(
            result["failures"],
            ["unexpected normalized output fragment remained: banned text"],
        )

    def test_minimum_channel_delimiter_text_repairs_fail_when_missing(self) -> None:
        result = run_fixture(
            {
                "name": "channel-repair-minimum-check",
                "request": {},
                "upstream_response": {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "plain answer"}],
                        }
                    ],
                },
                "expected": {
                    "minimum_channel_delimiter_text_repairs": 1,
                },
            }
        )

        self.assertEqual(
            result["failures"],
            ["expected at least 1 channel delimiter text repair(s), got 0"],
        )


if __name__ == "__main__":
    unittest.main()
