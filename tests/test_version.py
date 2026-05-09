from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

import open_gate


ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version_sources_match(self) -> None:
        version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(open_gate.__version__, version_file)
        self.assertEqual(pyproject["project"]["version"], version_file)


if __name__ == "__main__":
    unittest.main()
