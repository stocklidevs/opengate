from __future__ import annotations

import argparse
import json
from pathlib import Path

from .command_quality import inspect_tool_calls
from .linter import analyze_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse and lint leaked tool calls from model text.")
    parser.add_argument("text_file", type=Path, help="Text fixture or captured model output to inspect.")
    parser.add_argument("--tools", type=Path, help="Optional JSON file containing Responses-style tool definitions.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    text = args.text_file.read_text(encoding="utf-8")
    tools = None
    if args.tools:
        tools = json.loads(args.tools.read_text(encoding="utf-8"))

    report = analyze_text(text, tools)
    output = report.to_json()
    output["command_quality_issues"] = inspect_tool_calls(report.tool_calls)
    if args.pretty:
        print(json.dumps(output, indent=2, ensure_ascii=True))
    else:
        print(json.dumps(output, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
