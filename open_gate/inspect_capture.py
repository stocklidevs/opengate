from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise an Open Gate capture file.")
    parser.add_argument("capture", nargs="?", type=Path, help="Capture JSON file. Defaults to newest file in captures/.")
    parser.add_argument("--capture-dir", type=Path, default=Path("captures"))
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    capture = args.capture or newest_capture(args.capture_dir)
    record = json.loads(capture.read_text(encoding="utf-8"))
    body = record.get("body") or {}

    summary = {
        "file": str(capture),
        "captured_at": record.get("captured_at"),
        "method": record.get("method"),
        "path": record.get("path"),
        "model": body.get("model"),
        "stream": body.get("stream"),
        "tool_choice": body.get("tool_choice"),
        "input": summarise_input(body.get("input")),
        "tools": summarise_tools(body.get("tools")),
        "body_keys": sorted(body.keys()),
    }
    if args.pretty:
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    else:
        print(json.dumps(summary, separators=(",", ":"), ensure_ascii=True))
    return 0


def newest_capture(capture_dir: Path) -> Path:
    captures = sorted(capture_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not captures:
        raise SystemExit(f"No capture files found in {capture_dir}.")
    return captures[0]


def summarise_input(input_value: Any) -> list[dict[str, Any]]:
    if not isinstance(input_value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in input_value:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        content_types: list[str] = []
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("type"), str):
                    content_types.append(part["type"])
        out.append(
            {
                "type": item.get("type"),
                "role": item.get("role"),
                "content_parts": len(content) if isinstance(content, list) else None,
                "content_types": content_types,
            }
        )
    return out


def summarise_tools(tools: Any) -> list[dict[str, Any]]:
    if not isinstance(tools, list):
        return []
    out: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        parameters = tool.get("parameters")
        required = parameters.get("required") if isinstance(parameters, dict) else None
        out.append(
            {
                "type": tool.get("type"),
                "name": tool.get("name"),
                "strict": tool.get("strict"),
                "required": required if isinstance(required, list) else None,
            }
        )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
