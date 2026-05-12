from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .command_quality import inspect_tool_calls
from .linter import ToolCall, analyze_text, load_tool_specs


JsonObject = dict[str, Any]


@dataclass
class Endpoint:
    base_url: str
    api_key: str
    timeout: float

    def post_json(self, path: str, body: JsonObject) -> JsonObject:
        url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
        raw = json.dumps(body, ensure_ascii=True).encode("utf-8")
        request = Request(
            url,
            data=raw,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Connection failed: {exc.reason}") from exc
        return json.loads(payload) if payload else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark direct/proxied tool-call behavior.")
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL, e.g. http://host:8001/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--suite", type=Path, default=Path("fixtures/benchmarks/codex_shell_smoke.json"))
    parser.add_argument("--api", choices=["responses", "chat"], help="Override suite API.")
    parser.add_argument("--api-key", default="sk-no-key-required")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument("--include-raw-response", action="store_true")
    parser.add_argument("--summary-only", action="store_true", help="Print only the report summary to stdout.")
    parser.add_argument("--label", default="benchmark")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    api = args.api or suite.get("api") or "responses"
    endpoint = Endpoint(args.base_url, args.api_key, args.timeout)
    created_at = datetime.now(timezone.utc).isoformat()

    results: list[JsonObject] = []
    for run_index in range(args.runs):
        for case in suite.get("cases", []):
            if not isinstance(case, dict):
                continue
            started = time.perf_counter()
            result = run_case(endpoint, suite, case, api, args, run_index)
            result["latency_seconds"] = round(time.perf_counter() - started, 3)
            results.append(result)
            if args.output:
                write_report(args.output, build_report(args, suite, api, results, created_at, completed=False))

    report = build_report(args, suite, api, results, created_at, completed=True)

    raw = json.dumps(report, indent=2, ensure_ascii=True)
    if args.output:
        write_report(args.output, report)
    if args.summary_only:
        print(json.dumps({key: report[key] for key in ("label", "created_at", "suite", "runs", "summary")}, indent=2, ensure_ascii=True))
    else:
        print(raw)
    return 0


def build_report(
    args: argparse.Namespace,
    suite: JsonObject,
    api: str,
    results: list[JsonObject],
    created_at: str,
    completed: bool,
) -> JsonObject:
    cases_per_run = sum(1 for case in suite.get("cases", []) if isinstance(case, dict))
    expected_total = int(args.runs) * cases_per_run
    return {
        "label": args.label,
        "created_at": created_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "model": args.model,
        "api": api,
        "suite": suite.get("name") or str(args.suite),
        "runs": args.runs,
        "completed": completed,
        "cases_completed": len(results),
        "cases_expected": expected_total,
        "summary": summarise(results),
        "results": results,
    }


def write_report(path: Path, report: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_case(endpoint: Endpoint, suite: JsonObject, case: JsonObject, api: str, args: argparse.Namespace, run_index: int) -> JsonObject:
    request_body = build_request(suite, case, api, args)
    try:
        response = endpoint.post_json("/responses" if api == "responses" else "/chat/completions", request_body)
        error = None
    except RuntimeError as exc:
        response = {}
        error = str(exc)

    score = score_response(response, suite.get("tools") or [], case, api, error=error)
    score.update(
        {
            "case_id": case.get("id"),
            "category": case.get("category"),
            "run_index": run_index,
            "expected_tool": case.get("expected_tool"),
            "expected_tools": expected_tools(case),
            "expect_no_tool": bool(case.get("expect_no_tool")),
            "http_error": error,
        }
    )
    if args.include_raw_response:
        score["raw_response"] = response
    return score


def build_request(suite: JsonObject, case: JsonObject, api: str, args: argparse.Namespace) -> JsonObject:
    tools = suite.get("tools") or []
    tool_choice = case.get("tool_choice", suite.get("tool_choice", "auto"))
    prompt = str(case.get("prompt") or "")
    developer = case.get("developer") or suite.get("developer")
    if api == "chat":
        messages = []
        if developer:
            messages.append({"role": "system", "content": str(developer)})
        messages.append({"role": "user", "content": prompt})
        return {
            "model": args.model,
            "messages": messages,
            "tools": to_chat_tools(tools),
            "tool_choice": tool_choice,
            "temperature": args.temperature,
            "max_tokens": args.max_output_tokens,
        }
    input_items = []
    if developer:
        input_items.append({"type": "message", "role": "developer", "content": [{"type": "input_text", "text": str(developer)}]})
    input_items.append({"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]})
    return {
        "model": args.model,
        "input": input_items,
        "tools": tools,
        "tool_choice": tool_choice,
        "parallel_tool_calls": True,
        "temperature": args.temperature,
        "max_output_tokens": args.max_output_tokens,
        "stream": False,
        "store": False,
    }


def score_response(response: JsonObject, tools: list[JsonObject], case: JsonObject, api: str, error: str | None = None) -> JsonObject:
    text = collect_text(response, api)
    reasoning_text = collect_reasoning_text(response, api)
    structured = collect_structured_tool_calls(response, api)
    specs = load_tool_specs(tools)
    for call in structured:
        validate_with_linter_schema(call, specs)

    text_leak_report = analyze_text(text, tools)
    reasoning_leak_report = analyze_text(reasoning_text, tools)
    all_leaked_calls = text_leak_report.tool_calls + reasoning_leak_report.tool_calls
    all_calls = structured + all_leaked_calls
    expected = expected_tools(case)
    expect_no_tool = bool(case.get("expect_no_tool"))
    expected_set = set(expected)
    structured_names = [call.name for call in structured if call.valid]
    leaked_names = [call.name for call in all_leaked_calls if call.valid]
    all_names = [call.name for call in all_calls]

    missing_expected = [name for name in expected if name not in structured_names and name not in leaked_names]
    missing_structured = [name for name in expected if name not in structured_names]
    unexpected_tools = sorted({name for name in all_names if expected_set and name not in expected_set})
    over_eager_tool = bool(expect_no_tool and all_calls)
    has_expected_structured = bool(expected and not missing_structured)
    has_expected_leaked = bool(expected and all(name in leaked_names for name in expected))
    no_tool_success = bool(expect_no_tool and not all_calls)
    invalid_calls = [call.to_json() for call in all_calls if not call.valid]
    argument_leaks = argument_leak_reports(all_calls)
    command_quality_issues = inspect_tool_calls(structured)
    protocol_type = protocol_incompatibility_type(error)
    protocol_incompatibility = bool(protocol_type)
    transport_error = bool(error and not protocol_incompatibility)
    missed = bool(expected and missing_expected)
    text_leaked = bool(text_leak_report.tool_calls or text_leak_report.leaks)
    reasoning_leaked = bool(reasoning_leak_report.tool_calls or reasoning_leak_report.leaks)
    leaked = bool(text_leaked or reasoning_leaked)
    expected_condition = no_tool_success if expect_no_tool else has_expected_structured
    wrong_tool = bool(unexpected_tools or over_eager_tool)
    strict_success = bool(
        error is None
        and expected_condition
        and not leaked
        and not invalid_calls
        and not wrong_tool
        and not argument_leaks
        and not command_quality_issues
    )
    proxy_recoverable = bool(error is None and not has_expected_structured and has_expected_leaked and not invalid_calls and not expect_no_tool)
    failure = bool(not strict_success)

    return {
        "strict_success": strict_success,
        "failure": failure,
        "proxy_recoverable": proxy_recoverable,
        "protocol_incompatibility": protocol_incompatibility,
        "protocol_incompatibility_type": protocol_type,
        "transport_error": transport_error,
        "leaked": leaked,
        "text_leaked": text_leaked,
        "reasoning_leaked": reasoning_leaked,
        "missed_tool_call": missed,
        "wrong_tool": wrong_tool,
        "over_eager_tool": over_eager_tool,
        "invalid_tool_call": bool(invalid_calls),
        "argument_leak": bool(argument_leaks),
        "command_quality_issue": bool(command_quality_issues),
        "structured_tool_calls": [call.to_json() for call in structured],
        "leaked_tool_calls": [call.to_json() for call in all_leaked_calls],
        "invalid_tool_calls": invalid_calls,
        "argument_leaks": argument_leaks,
        "command_quality_issues": command_quality_issues,
        "missing_expected_tools": missing_expected,
        "missing_structured_tools": missing_structured,
        "unexpected_tools": unexpected_tools,
        "structured_tool_names": structured_names,
        "leaked_tool_names": leaked_names,
        "leak_markers": sorted(set(text_leak_report.leaks + reasoning_leak_report.leaks)),
        "text_leak_markers": text_leak_report.leaks,
        "reasoning_leak_markers": reasoning_leak_report.leaks,
        "text_chars": len(text),
        "reasoning_chars": len(reasoning_text),
        "text_preview": text[:1000],
        "reasoning_preview": reasoning_text[:1000],
    }


def protocol_incompatibility_type(error: str | None) -> str | None:
    if not error:
        return None
    lowered = error.lower()
    if "unexpected message role" in lowered:
        return "unexpected_message_role"
    if "unsupported message role" in lowered or "unsupported role" in lowered or "invalid role" in lowered:
        return "unsupported_message_role"
    if "function_call_output" in lowered or "function_call" in lowered:
        return "unsupported_responses_tool_history"
    if "input should be" in lowered or "invalid input" in lowered:
        return "unsupported_responses_input_shape"
    return None


def expected_tools(case: JsonObject) -> list[str]:
    raw_many = case.get("expected_tools")
    if isinstance(raw_many, list):
        return [item for item in raw_many if isinstance(item, str) and item]
    raw_one = case.get("expected_tool")
    if isinstance(raw_one, str) and raw_one:
        return [raw_one]
    return []


def collect_text(response: JsonObject, api: str) -> str:
    if api == "chat":
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            content = message.get("content") if isinstance(message, dict) else ""
            return content if isinstance(content, str) else ""
        return ""

    pieces: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                text = part.get("text")
                if isinstance(text, str):
                    pieces.append(text)
    if not pieces:
        output_text = response.get("output_text")
        if isinstance(output_text, str):
            pieces.append(output_text)
    return "\n".join(pieces)


def collect_reasoning_text(response: JsonObject, api: str) -> str:
    if api == "chat":
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            if isinstance(message, dict):
                reasoning = message.get("reasoning_content") or message.get("reasoning")
                return flatten_text(reasoning)
        return ""

    pieces: list[str] = []
    top_reasoning = response.get("reasoning")
    if top_reasoning:
        pieces.append(flatten_text(top_reasoning))
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "reasoning":
            pieces.append(flatten_text(item))
    return "\n".join(piece for piece in pieces if piece)


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        pieces: list[str] = []
        for key, item in value.items():
            if key in {"text", "content", "summary", "reasoning", "reasoning_content"}:
                pieces.append(flatten_text(item))
            elif isinstance(item, list | dict):
                nested = flatten_text(item)
                if nested:
                    pieces.append(nested)
        return "\n".join(piece for piece in pieces if piece)
    if isinstance(value, list):
        return "\n".join(piece for piece in (flatten_text(item) for item in value) if piece)
    return ""


def collect_structured_tool_calls(response: JsonObject, api: str) -> list[ToolCall]:
    if api == "chat":
        return collect_chat_tool_calls(response)
    return collect_responses_tool_calls(response)


def collect_responses_tool_calls(response: JsonObject) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index, item in enumerate(response.get("output") or []):
        if not isinstance(item, dict):
            continue
        if item.get("type") in ("function_call", "custom_tool_call"):
            name = item.get("name")
            args = item.get("arguments", {})
            if isinstance(name, str):
                calls.append(ToolCall(name=name, arguments=parse_arguments(args), source="responses_structured", span=(index, index), raw=json.dumps(item, ensure_ascii=True)))
        if isinstance(item.get("tool_calls"), list):
            calls.extend(calls_from_tool_call_list(item["tool_calls"], "responses_tool_calls"))
    return calls


def collect_chat_tool_calls(response: JsonObject) -> list[ToolCall]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return []
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        return []
    return calls_from_tool_call_list(message.get("tool_calls"), "chat_structured")


def calls_from_tool_call_list(values: Any, source: str) -> list[ToolCall]:
    if not isinstance(values, list):
        return []
    calls: list[ToolCall] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            continue
        function = value.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            args = function.get("arguments", {})
        else:
            name = value.get("name")
            args = value.get("arguments", {})
        if isinstance(name, str):
            calls.append(ToolCall(name=name, arguments=parse_arguments(args), source=source, span=(index, index), raw=json.dumps(value, ensure_ascii=True)))
    return calls


def parse_arguments(value: Any) -> JsonObject:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
        return loaded if isinstance(loaded, dict) else {"value": loaded}
    if value is None:
        return {}
    return {"value": value}


def validate_with_linter_schema(call: ToolCall, specs: dict[str, Any]) -> None:
    if specs and call.name not in specs:
        call.valid = False
        call.errors.append(f"Unknown tool: {call.name}")
    spec = specs.get(call.name)
    schema = spec.parameters if spec else {}
    for key in schema.get("required") or []:
        if key not in call.arguments:
            call.valid = False
            call.errors.append(f"Missing required argument: {key}")
    properties = schema.get("properties") or {}
    if isinstance(properties, dict):
        for key, value in call.arguments.items():
            if key not in properties:
                if schema.get("additionalProperties") is False:
                    call.valid = False
                    call.errors.append(f"Unexpected argument: {key}")
                continue
            expected = properties.get(key)
            if isinstance(expected, dict):
                type_name = expected.get("type")
                if type_name and not json_type_matches(value, type_name):
                    call.valid = False
                    call.errors.append(f"Argument {key} expected {type_name}, got {type(value).__name__}")


def json_type_matches(value: Any, type_name: str | list[str]) -> bool:
    if isinstance(type_name, list):
        return any(json_type_matches(value, item) for item in type_name)
    checks = {
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, int | float) and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
        "null": lambda item: item is None,
    }
    checker = checks.get(type_name)
    return True if checker is None else checker(value)


def argument_leak_reports(calls: list[ToolCall]) -> list[JsonObject]:
    reports: list[JsonObject] = []
    for call in calls:
        text = json.dumps(call.arguments, ensure_ascii=True)
        report = analyze_text(text, None)
        markers = [marker for marker in report.leaks if marker != "parsed_tool_call"]
        if markers:
            reports.append({"tool": call.name, "markers": markers, "preview": text[:500]})
    return reports


def to_chat_tools(tools: list[JsonObject]) -> list[JsonObject]:
    chat_tools: list[JsonObject] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        if "function" in tool:
            chat_tools.append(tool)
            continue
        chat_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            }
        )
    return chat_tools


def summarise(results: list[JsonObject]) -> JsonObject:
    total = len(results)
    if total == 0:
        return {"total": 0}
    counters = {
        "strict_successes": sum(1 for item in results if item.get("strict_success")),
        "failures": sum(1 for item in results if item.get("failure")),
        "leaks": sum(1 for item in results if item.get("leaked")),
        "text_leaks": sum(1 for item in results if item.get("text_leaked")),
        "reasoning_leaks": sum(1 for item in results if item.get("reasoning_leaked")),
        "proxy_recoverable": sum(1 for item in results if item.get("proxy_recoverable")),
        "missed_tool_calls": sum(1 for item in results if item.get("missed_tool_call")),
        "wrong_tools": sum(1 for item in results if item.get("wrong_tool")),
        "over_eager_tools": sum(1 for item in results if item.get("over_eager_tool")),
        "invalid_tool_calls": sum(1 for item in results if item.get("invalid_tool_call")),
        "argument_leaks": sum(1 for item in results if item.get("argument_leak")),
        "command_quality_issues": sum(1 for item in results if item.get("command_quality_issue")),
        "http_errors": sum(1 for item in results if item.get("http_error")),
        "protocol_incompatibilities": sum(1 for item in results if item.get("protocol_incompatibility")),
        "transport_errors": sum(1 for item in results if item.get("transport_error")),
    }
    rates = {f"{key}_rate": round(value / total, 4) for key, value in counters.items()}
    return {"total": total, **counters, **rates}


if __name__ == "__main__":
    raise SystemExit(main())
