from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any


JsonObject = dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise an Open Gate benchmark report by category and case.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    results = [item for item in report.get("results", []) if isinstance(item, dict)]
    summary = {
        "label": report.get("label"),
        "suite": report.get("suite"),
        "runs": report.get("runs"),
        "overall": report.get("summary"),
        "by_category": group_results(results, "category"),
        "by_case": group_results(results, "case_id"),
        "failure_cases": [
            summarise_group(case_id, items)
            for case_id, items in sorted(grouped(results, "case_id").items())
            if any(item.get("failure") for item in items)
        ],
    }
    if args.pretty:
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    else:
        print(json.dumps(summary, separators=(",", ":"), ensure_ascii=True))
    return 0


def grouped(results: list[JsonObject], key: str) -> dict[str, list[JsonObject]]:
    groups: dict[str, list[JsonObject]] = defaultdict(list)
    for item in results:
        groups[str(item.get(key) or "<missing>")].append(item)
    return dict(groups)


def group_results(results: list[JsonObject], key: str) -> list[JsonObject]:
    return [summarise_group(name, items) for name, items in sorted(grouped(results, key).items())]


def summarise_group(name: str, items: list[JsonObject]) -> JsonObject:
    total = len(items)
    counters = {
        "strict_successes": sum(1 for item in items if item.get("strict_success")),
        "failures": sum(1 for item in items if item.get("failure")),
        "leaks": sum(1 for item in items if item.get("leaked")),
        "text_leaks": sum(1 for item in items if item.get("text_leaked")),
        "reasoning_leaks": sum(1 for item in items if item.get("reasoning_leaked")),
        "proxy_recoverable": sum(1 for item in items if item.get("proxy_recoverable")),
        "missed_tool_calls": sum(1 for item in items if item.get("missed_tool_call")),
        "wrong_tools": sum(1 for item in items if item.get("wrong_tool")),
        "over_eager_tools": sum(1 for item in items if item.get("over_eager_tool")),
        "invalid_tool_calls": sum(1 for item in items if item.get("invalid_tool_call")),
        "argument_leaks": sum(1 for item in items if item.get("argument_leak")),
        "http_errors": sum(1 for item in items if item.get("http_error")),
    }
    rates = {f"{key}_rate": round(value / total, 4) for key, value in counters.items()} if total else {}
    return {"name": name, "total": total, **counters, **rates}


if __name__ == "__main__":
    raise SystemExit(main())
