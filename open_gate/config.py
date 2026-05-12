from __future__ import annotations

import os
from pathlib import Path
import tomllib
from typing import Any


JsonObject = dict[str, Any]

DEFAULT_CONFIG: JsonObject = {
    "host": "127.0.0.1",
    "port": 8765,
    "capture_dir": "captures",
    "model": "auto",
    "text": "open-gate probe response",
    "fixture": None,
    "upstream_base_url": None,
    "upstream_api_key": "sk-no-key-required",
    "upstream_timeout": 420.0,
    "capability_probe": "auto",
    "capability_probe_timeout": 8.0,
    "normalization_mode": "repair",
    "upstream_input_mode": "auto",
    "context_policy": "spoon",
    "context_max_chars": 60000,
    "context_recent_items": 12,
    "instruction_policy": "auto",
    "tool_schema_policy": "auto",
    "stream_heartbeat_seconds": 2.0,
    "quiet": False,
    "no_banner": False,
}

CONFIG_SEARCH_NAMES = ("opengate.toml", "open-gate.toml", ".opengate.toml")


def discover_config_path(explicit_path: str | None = None, cwd: Path | None = None) -> Path | None:
    if explicit_path:
        return Path(explicit_path).expanduser()
    env_path = os.environ.get("OPENGATE_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    base = cwd or Path.cwd()
    for name in CONFIG_SEARCH_NAMES:
        candidate = base / name
        if candidate.exists():
            return candidate
    home_candidate = Path.home() / ".opengate" / "config.toml"
    if home_candidate.exists():
        return home_candidate
    return None


def load_config_file(path: Path | None) -> JsonObject:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"OpenGate config file does not exist: {path}")
    loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return {}
    return flatten_config(loaded)


def flatten_config(raw: JsonObject) -> JsonObject:
    flattened: JsonObject = {}
    copy_known_top_level(raw, flattened)

    server = table(raw, "server")
    copy_keys(server, flattened, "host", "port", "capture_dir", "text", "fixture", "quiet", "no_banner")

    upstream = table(raw, "upstream")
    copy_keys(upstream, flattened, "api_key", "timeout", "base_url", "model", "capability_probe", "capability_probe_timeout")
    if "api_key" in flattened:
        flattened["upstream_api_key"] = flattened.pop("api_key")
    if "timeout" in flattened:
        flattened["upstream_timeout"] = flattened.pop("timeout")
    if "base_url" in flattened:
        flattened["upstream_base_url"] = flattened.pop("base_url")
    if upstream:
        built_url = build_upstream_base_url(upstream)
        if built_url and not flattened.get("upstream_base_url"):
            flattened["upstream_base_url"] = built_url

    proxy = table(raw, "proxy")
    copy_keys(
        proxy,
        flattened,
        "normalization_mode",
        "upstream_input_mode",
        "context_policy",
        "context_max_chars",
        "context_recent_items",
        "instruction_policy",
        "tool_schema_policy",
        "stream_heartbeat_seconds",
    )
    return {key: value for key, value in flattened.items() if value is not None}


def copy_known_top_level(raw: JsonObject, out: JsonObject) -> None:
    for key in DEFAULT_CONFIG:
        if key in raw:
            out[key] = raw[key]
    if "upstream" in raw and isinstance(raw["upstream"], str):
        out["upstream_base_url"] = raw["upstream"]


def table(raw: JsonObject, key: str) -> JsonObject:
    value = raw.get(key)
    return value if isinstance(value, dict) else {}


def copy_keys(source: JsonObject, target: JsonObject, *keys: str) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key]


def build_upstream_base_url(upstream: JsonObject) -> str | None:
    host = upstream.get("host")
    port = upstream.get("port")
    if not host:
        return None
    scheme = str(upstream.get("scheme") or "http").rstrip(":/")
    path = str(upstream.get("path") or "/v1")
    if not path.startswith("/"):
        path = "/" + path
    port_text = f":{int(port)}" if isinstance(port, int) else f":{port}" if port else ""
    return f"{scheme}://{host}{port_text}{path}".rstrip("/")


def merge_config(config_file_values: JsonObject, cli_values: JsonObject) -> JsonObject:
    merged = dict(DEFAULT_CONFIG)
    merged.update({key: value for key, value in config_file_values.items() if value is not None})
    merged.update({key: value for key, value in cli_values.items() if value is not None})
    return merged
