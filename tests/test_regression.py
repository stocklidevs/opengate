from __future__ import annotations

import json
from pathlib import Path
import unittest

from open_gate.regression import iter_fixture_paths, run_fixture_path


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


if __name__ == "__main__":
    unittest.main()
