from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .benchmark import collect_responses_tool_calls, collect_text, validate_with_linter_schema
from .command_quality import inspect_tool_calls
from .linter import analyze_text, load_tool_specs


JsonObject = dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Open Gate captures and Codex JSONL output from live runs.")
    parser.add_argument("capture_dir", type=Path, help="Directory containing Open Gate proxy capture JSON files.")
    parser.add_argument("--codex-dir", type=Path, help="Directory containing codex exec JSONL/log output.")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    report = build_report(args.capture_dir, args.codex_dir)
    if args.summary_only:
        report = {key: report[key] for key in ("created_at", "capture_dir", "codex_dir", "summary")}
    print(json.dumps(report, indent=2 if args.pretty else None, ensure_ascii=True))
    return 0


def build_report(capture_dir: Path, codex_dir: Path | None = None) -> JsonObject:
    captures = [summarize_capture(path) for path in iter_capture_paths(capture_dir)]
    codex_runs = [summarize_codex_jsonl(path) for path in iter_codex_paths(codex_dir)] if codex_dir else []
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "capture_dir": str(capture_dir),
        "codex_dir": str(codex_dir) if codex_dir else None,
        "summary": summarize(captures, codex_runs),
        "captures": captures,
        "codex_runs": codex_runs,
    }


def iter_capture_paths(capture_dir: Path) -> list[Path]:
    if capture_dir.is_file():
        return [capture_dir]
    if not capture_dir.exists():
        return []
    return sorted(capture_dir.rglob("*proxy*.json"))


def iter_codex_paths(codex_dir: Path | None) -> list[Path]:
    if codex_dir is None:
        return []
    if codex_dir.is_file():
        return [codex_dir]
    if not codex_dir.exists():
        return []
    return sorted(path for path in codex_dir.rglob("*") if path.suffix.lower() in {".jsonl", ".log", ".txt"})


def summarize_capture(path: Path) -> JsonObject:
    capture = json.loads(path.read_text(encoding="utf-8"))
    request = capture.get("request") if isinstance(capture.get("request"), dict) else {}
    tools = request.get("tools") if isinstance(request.get("tools"), list) else []
    upstream = capture.get("upstream") if isinstance(capture.get("upstream"), dict) else {}
    upstream_response = upstream.get("response") if isinstance(upstream.get("response"), dict) else {}
    returned_response = capture.get("response") if isinstance(capture.get("response"), dict) else {}
    normalized_response = capture.get("normalized_response") if isinstance(capture.get("normalized_response"), dict) else returned_response
    normalization = capture.get("normalization") if isinstance(capture.get("normalization"), dict) else {}
    raw_text = json.dumps(capture, ensure_ascii=True)

    upstream_analysis = analyze_response(upstream_response, tools)
    returned_analysis = analyze_response(returned_response, tools)
    normalized_analysis = analyze_response(normalized_response, tools)

    return {
        "file": str(path),
        "captured_at": capture.get("captured_at"),
        "normalization_mode": capture.get("normalization_mode") or normalization.get("mode"),
        "upstream_status": upstream.get("status"),
        "request_stream": bool(request.get("stream")),
        "blocked_by_policy": "blocked by policy" in raw_text.lower(),
        "repairs": len(normalization.get("structured_argument_repairs") or []),
        "stripped_text_items": int(normalization.get("stripped_text_items") or 0),
        "suppressed_structured_calls": len(normalization.get("suppressed_structured_calls") or []),
        "promoted_tool_calls": len(normalization.get("promoted_tool_calls") or []),
        "invalid_tool_calls": len(normalization.get("invalid_tool_calls") or []),
        "upstream": upstream_analysis,
        "returned": returned_analysis,
        "normalized": normalized_analysis,
    }


def analyze_response(response: JsonObject, tools: list[JsonObject]) -> JsonObject:
    text = collect_text(response, "responses")
    text_report = analyze_text(text, tools)
    calls = collect_responses_tool_calls(response)
    specs = load_tool_specs(tools)
    for call in calls:
        validate_with_linter_schema(call, specs)
    invalid_calls = [call.to_json() for call in calls if not call.valid]
    command_quality_issues = inspect_tool_calls(calls)
    return {
        "text_leaks": sorted(set(text_report.leaks)),
        "text_leaked": bool(text_report.leaks or text_report.tool_calls),
        "structured_tool_calls": [call.to_json() for call in calls],
        "structured_tool_names": [call.name for call in calls],
        "invalid_tool_calls": invalid_calls,
        "command_quality_issues": command_quality_issues,
        "message_chars": len(text),
    }


def summarize_codex_jsonl(path: Path) -> JsonObject:
    events: list[JsonObject] = []
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)

    types = Counter(str(event.get("type")) for event in events)
    command_started_items = [
        event.get("item")
        for event in events
        if event.get("type") == "item.started"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "command_execution"
    ]
    command_completed_items = [
        event.get("item")
        for event in events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "command_execution"
    ]
    agent_messages = [
        event.get("item")
        for event in events
        if isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message"
    ]
    errors = [event.get("message") for event in events if event.get("type") == "error"]
    return {
        "file": str(path),
        "events": len(events),
        "turn_completed": types["turn.completed"],
        "turn_failed": types["turn.failed"],
        "errors": len(errors),
        "error_messages": [message for message in errors if isinstance(message, str)],
        "command_executions": max(len(command_started_items), len(command_completed_items)),
        "commands_started": len(command_started_items),
        "commands_completed": sum(1 for item in command_completed_items if isinstance(item, dict) and item.get("status") == "completed"),
        "agent_messages": len(agent_messages),
        "blocked_by_policy": "blocked by policy" in raw_text.lower(),
    }


def summarize(captures: list[JsonObject], codex_runs: list[JsonObject]) -> JsonObject:
    total_captures = len(captures)
    total_codex = len(codex_runs)
    return {
        "proxy_exchanges": total_captures,
        "upstream_errors": sum(1 for item in captures if item.get("upstream_status") and item["upstream_status"] >= 400),
        "captures_with_repairs": sum(1 for item in captures if item.get("repairs")),
        "structured_argument_repairs": sum(int(item.get("repairs") or 0) for item in captures),
        "stripped_text_items": sum(int(item.get("stripped_text_items") or 0) for item in captures),
        "promoted_tool_calls": sum(int(item.get("promoted_tool_calls") or 0) for item in captures),
        "suppressed_structured_calls": sum(int(item.get("suppressed_structured_calls") or 0) for item in captures),
        "blocked_by_policy_captures": sum(1 for item in captures if item.get("blocked_by_policy")),
        "upstream_text_leaks": sum(1 for item in captures if item["upstream"].get("text_leaked")),
        "returned_text_leaks": sum(1 for item in captures if item["returned"].get("text_leaked")),
        "upstream_command_quality_issues": sum(1 for item in captures if item["upstream"].get("command_quality_issues")),
        "returned_command_quality_issues": sum(1 for item in captures if item["returned"].get("command_quality_issues")),
        "upstream_invalid_tool_calls": sum(1 for item in captures if item["upstream"].get("invalid_tool_calls")),
        "returned_invalid_tool_calls": sum(1 for item in captures if item["returned"].get("invalid_tool_calls")),
        "codex_runs": total_codex,
        "codex_turns_completed": sum(1 for item in codex_runs if item.get("turn_completed")),
        "codex_turns_failed": sum(1 for item in codex_runs if item.get("turn_failed")),
        "codex_runs_with_errors": sum(1 for item in codex_runs if item.get("errors")),
        "codex_runs_with_policy_blocks": sum(1 for item in codex_runs if item.get("blocked_by_policy")),
        "codex_command_executions": sum(int(item.get("command_executions") or 0) for item in codex_runs),
        "codex_agent_messages": sum(int(item.get("agent_messages") or 0) for item in codex_runs),
        "codex_turn_completion_rate": rate(sum(1 for item in codex_runs if item.get("turn_completed")), total_codex),
        "returned_clean_capture_rate": rate(
            sum(
                1
                for item in captures
                if not item["returned"].get("text_leaked")
                and not item["returned"].get("command_quality_issues")
                and not item["returned"].get("invalid_tool_calls")
                and not item.get("blocked_by_policy")
            ),
            total_captures,
        ),
    }


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
