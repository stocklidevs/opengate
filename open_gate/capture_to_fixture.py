from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .benchmark import collect_responses_tool_calls
from .command_quality import inspect_tool_calls
from .linter import analyze_text
from .proxy import normalize_responses_response


JsonObject = dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an Open Gate proxy capture into a regression fixture.")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--output-dir", type=Path, default=Path("fixtures/regressions"))
    parser.add_argument("--full-request", action="store_true")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    fixture = build_fixture(args.capture, name=args.name, full_request=args.full_request, notes=args.notes)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"{fixture['name']}.json"
    output_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(output_path)
    return 0


def build_fixture(capture_path: Path, name: str | None = None, full_request: bool = False, notes: str = "") -> JsonObject:
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    request = capture.get("request") or capture.get("body")
    upstream_response = ((capture.get("upstream") or {}).get("response")) or capture.get("response")
    if not isinstance(request, dict) or not isinstance(upstream_response, dict):
        raise ValueError(f"{capture_path} is not a proxy capture with request and upstream response objects")

    fixture_name = name or safe_stem(capture_path.stem)
    fixture_request = request if full_request else minimal_request(request, upstream_response)
    normalized, normalization = normalize_responses_response(upstream_response, fixture_request)
    text_report = analyze_text(collect_text_from_response(normalized), fixture_request.get("tools") or [])
    command_quality_issues = inspect_tool_calls(collect_responses_tool_calls(normalized))

    return {
        "schema_version": 1,
        "name": fixture_name,
        "source_capture": str(capture_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
        "request": fixture_request,
        "upstream_response": upstream_response,
        "expected": {
            "no_text_leaks": True,
            "no_invalid_tool_calls": True,
            "no_command_quality_issues": True,
            "minimum_structured_argument_repairs": len(normalization.get("structured_argument_repairs") or []),
            "minimum_text_tool_call_repairs": len(normalization.get("text_tool_call_repairs") or []),
            "expected_tool_calls": [call.name for call in collect_responses_tool_calls(normalized)],
        },
        "observed_after_normalization": {
            "structured_argument_repairs": normalization.get("structured_argument_repairs") or [],
            "text_leaks": text_report.leaks,
            "command_quality_issues": command_quality_issues,
        },
    }


def minimal_request(request: JsonObject, upstream_response: JsonObject) -> JsonObject:
    keep = {
        key: request[key]
        for key in (
            "model",
            "tool_choice",
            "parallel_tool_calls",
            "stream",
            "store",
            "temperature",
            "max_output_tokens",
        )
        if key in request
    }
    keep["input"] = latest_user_input(request)
    keep["tools"] = relevant_tools(request.get("tools") or [], upstream_response)
    return keep


def latest_user_input(request: JsonObject) -> list[JsonObject]:
    input_items = request.get("input")
    if isinstance(input_items, str):
        return [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": input_items}]}]
    if not isinstance(input_items, list):
        return []
    for item in reversed(input_items):
        if isinstance(item, dict) and item.get("role") == "user":
            return [item]
    return []


def relevant_tools(tools: list[Any], upstream_response: JsonObject) -> list[JsonObject]:
    names = {call.name for call in collect_responses_tool_calls(upstream_response)}
    if not names:
        return [tool for tool in tools if isinstance(tool, dict)]
    kept: list[JsonObject] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        nested_name = function.get("name") if isinstance(function, dict) else None
        name = tool.get("name") or nested_name
        if name in names:
            kept.append(tool)
    return kept


def collect_text_from_response(response: JsonObject) -> str:
    pieces: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                pieces.append(part["text"])
    return "\n".join(pieces)


def safe_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return cleaned.strip("_") or "capture_fixture"


if __name__ == "__main__":
    raise SystemExit(main())
