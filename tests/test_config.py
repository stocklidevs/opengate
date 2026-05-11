from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from open_gate.config import discover_config_path, flatten_config, load_config_file, merge_config


class ConfigTests(unittest.TestCase):
    def test_flattens_upstream_host_port_into_base_url(self) -> None:
        config = flatten_config(
            {
                "server": {"host": "127.0.0.1", "port": 8765},
                "upstream": {
                    "scheme": "http",
                    "host": "127.0.0.1",
                    "port": 8001,
                    "path": "/v1",
                    "model": "auto",
                },
                "proxy": {"context_policy": "spoon"},
            }
        )

        self.assertEqual(config["host"], "127.0.0.1")
        self.assertEqual(config["upstream_base_url"], "http://127.0.0.1:8001/v1")
        self.assertEqual(config["model"], "auto")
        self.assertEqual(config["context_policy"], "spoon")

    def test_cli_values_override_config_values(self) -> None:
        merged = merge_config(
            {"port": 8765, "context_policy": "spoon"},
            {"port": 9999, "context_policy": None},
        )

        self.assertEqual(merged["port"], 9999)
        self.assertEqual(merged["context_policy"], "spoon")

    def test_discovers_local_opengate_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opengate.toml"
            path.write_text("[server]\nport = 8765\n", encoding="utf-8")

            self.assertEqual(discover_config_path(cwd=Path(tmp)), path)
            self.assertEqual(load_config_file(path)["port"], 8765)


if __name__ == "__main__":
    unittest.main()
