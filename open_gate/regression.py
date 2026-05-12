from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .benchmark import collect_responses_tool_calls, collect_text, validate_with_linter_schema
from .command_quality import inspect_tool_calls
from .linter import analyze_text, load_tool_specs
from .proxy import normalize_responses_response


JsonObject = dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay captured upstream responses through Open Gate normalization.")
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("fixtures/regressions")])
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    fixtures = list(iter_fixture_paths(args.paths))
    results = [run_fixture_path(path) for path in fixtures]
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "failures": sum(1 for item in results if item["failures"]),
        "results": results,
    }
    print(json.dumps(report, indent=2 if args.pretty else None, ensure_ascii=True))
    return 1 if report["failures"] else 0


def iter_fixture_paths(paths: list[Path]) -> list[Path]:
    fixtures: list[Path] = []
    for path in paths:
        if path.is_dir():
            fixtures.extend(sorted(path.glob("*.json")))
        elif path.exists():
            fixtures.append(path)
    return fixtures


def run_fixture_path(path: Path) -> JsonObject:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    result = run_fixture(fixture)
    result["path"] = str(path)
    return result


def run_fixture(fixture: JsonObject) -> JsonObject:
    request = fixture.get("request") or {}
    upstream_response = fixture.get("upstream_response") or {}
    expected = fixture.get("expected") or {}
    normalized, normalization = normalize_responses_response(upstream_response, request)
    tools = request.get("tools") if isinstance(request.get("tools"), list) else []

    text = collect_text(normalized, "responses")
    text_report = analyze_text(text, tools)
    structured_calls = collect_responses_tool_calls(normalized)
    specs = load_tool_specs(tools)
    for call in structured_calls:
        validate_with_linter_schema(call, specs)
    invalid_calls = [call.to_json() for call in structured_calls if not call.valid]
    command_quality_issues = inspect_tool_calls(structured_calls)

    result = {
        "name": fixture.get("name"),
        "source_capture": fixture.get("source_capture"),
        "normalization": normalization,
        "normalized_output": normalized.get("output", []),
        "text_leaks": text_report.leaks,
        "structured_tool_names": [call.name for call in structured_calls],
        "invalid_tool_calls": invalid_calls,
        "command_quality_issues": command_quality_issues,
    }
    result["failures"] = fixture_failures(result, expected)
    return result


def fixture_failures(result: JsonObject, expected: JsonObject) -> list[str]:
    failures: list[str] = []
    if expected.get("no_text_leaks", True) and result["text_leaks"]:
        failures.append(f"text leaks remained: {', '.join(result['text_leaks'])}")
    if expected.get("no_invalid_tool_calls", True) and result["invalid_tool_calls"]:
        failures.append("invalid structured tool calls remained")
    if expected.get("no_command_quality_issues", True) and result["command_quality_issues"]:
        failures.append("command quality issues remained")

    expected_tools = expected.get("expected_tool_calls") or []
    for tool_name in expected_tools:
        if tool_name not in result["structured_tool_names"]:
            failures.append(f"missing expected structured tool call: {tool_name}")

    minimum_repairs = int(expected.get("minimum_structured_argument_repairs") or 0)
    actual_repairs = len(result["normalization"].get("structured_argument_repairs") or [])
    if actual_repairs < minimum_repairs:
        failures.append(f"expected at least {minimum_repairs} structured argument repair(s), got {actual_repairs}")

    minimum_text_repairs = int(expected.get("minimum_text_tool_call_repairs") or 0)
    actual_text_repairs = len(result["normalization"].get("text_tool_call_repairs") or [])
    if actual_text_repairs < minimum_text_repairs:
        failures.append(f"expected at least {minimum_text_repairs} text tool-call repair(s), got {actual_text_repairs}")

    minimum_command_quality_suppressed = int(expected.get("minimum_command_quality_suppressed_structured_calls") or 0)
    actual_command_quality_suppressed = len(result["normalization"].get("command_quality_suppressed_structured_calls") or [])
    if actual_command_quality_suppressed < minimum_command_quality_suppressed:
        failures.append(
            "expected at least "
            f"{minimum_command_quality_suppressed} command-quality suppressed structured call(s), "
            f"got {actual_command_quality_suppressed}"
        )

    minimum_structured_quarantines = int(expected.get("minimum_structured_command_quality_quarantines") or 0)
    command_quality_suppressed = result["normalization"].get("command_quality_suppressed_structured_calls") or []
    actual_structured_quarantines = sum(
        1 for item in command_quality_suppressed if isinstance(item, dict) and isinstance(item.get("quarantined_as"), dict)
    )
    if actual_structured_quarantines < minimum_structured_quarantines:
        failures.append(
            "expected at least "
            f"{minimum_structured_quarantines} structured command-quality quarantine(s), "
            f"got {actual_structured_quarantines}"
        )

    minimum_actionable_repairs = int(expected.get("minimum_actionable_output_repairs") or 0)
    actual_actionable_repairs = 1 if isinstance(result["normalization"].get("actionable_output_repair"), dict) else 0
    if actual_actionable_repairs < minimum_actionable_repairs:
        failures.append(
            f"expected at least {minimum_actionable_repairs} actionable output repair(s), got {actual_actionable_repairs}"
        )

    minimum_policy_quarantines = int(expected.get("minimum_policy_quarantines") or 0)
    policy_suppressed = result["normalization"].get("policy_suppressed_structured_calls") or []
    actual_policy_quarantines = sum(
        1 for item in policy_suppressed if isinstance(item, dict) and isinstance(item.get("quarantined_as"), dict)
    )
    if actual_policy_quarantines < minimum_policy_quarantines:
        failures.append(f"expected at least {minimum_policy_quarantines} policy quarantine(s), got {actual_policy_quarantines}")

    text = json.dumps(result["normalized_output"], ensure_ascii=True)
    for fragment in expected.get("expected_output_fragments") or []:
        if str(fragment) not in text:
            failures.append(f"missing expected normalized output fragment: {fragment}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
