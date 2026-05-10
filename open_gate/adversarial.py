from __future__ import annotations

import argparse
import json
import random
import re
from typing import Any

from .proxy import normalize_responses_response


JsonObject = dict[str, Any]

TOOLS: list[JsonObject] = [
    {
        "type": "function",
        "name": "shell",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}},
                "workdir": {"type": "string"},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "update_plan",
        "parameters": {
            "type": "object",
            "properties": {
                "plan": {"type": "array", "items": {"type": "object"}},
                "explanation": {"type": "string"},
            },
            "required": ["plan"],
            "additionalProperties": False,
        },
    },
]

RAW_TOOL_SYNTAX_RE = re.compile(
    r"<\s*/?\s*t\s*o\s*o\s*l\s*_\s*c\s*a\s*l\s*l|"
    r"<\s*/?\s*a\s*r\s*g\s*_\s*k\s*e\s*y|"
    r"<\s*/?\s*a\s*r\s*g\s*_\s*v\s*a\s*l\s*u\s*e|"
    r"\brecipient_name\b|"
    r"\bfunctions\.[A-Za-z_][A-Za-z0-9_]*\s*\(",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic adversarial Open Gate normalizer checks.")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=6047)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    failures = run_adversarial_checks(args.iterations, args.seed)
    if failures:
        print(json.dumps({"ok": False, "failures": failures[:10], "failure_count": len(failures)}, indent=2))
        return 1
    if not args.quiet:
        print(json.dumps({"ok": True, "iterations": args.iterations, "seed": args.seed}, indent=2))
    return 0


def run_adversarial_checks(iterations: int = 200, seed: int = 6047) -> list[JsonObject]:
    rng = random.Random(seed)
    failures: list[JsonObject] = []
    for index in range(iterations):
        for case in build_cases(rng):
            failure = check_case(case, index)
            if failure:
                failures.append(failure)
    return failures


def build_cases(rng: random.Random) -> list[JsonObject]:
    shell_call = glm_call(
        "shell",
        {"command": ["powershell.exe", "-Command", "Get-ChildItem -Filter index.html"]},
        rng,
    )
    web_search_call = glm_call("web_search", {"external_web_access": True}, rng)
    plan_call = glm_call(
        "update_plan",
        {"plan": [{"step": "Inspect", "status": "in_progress"}]},
        rng,
    )
    return [
        {
            "name": "message_shell_after_unknown",
            "text": f"I will inspect.{web_search_call}{shell_call}",
            "expected_tools": ["shell"],
        },
        {
            "name": "message_update_plan",
            "text": f"I will plan.{plan_call}",
            "expected_tools": ["update_plan"],
        },
        {
            "name": "reasoning_unknown_only",
            "reasoning_text": f"Thinking.{web_search_call}",
            "text": "Done.",
            "expected_tools": [],
        },
        {
            "name": "top_level_output_text",
            "output_text": shell_call,
            "expected_tools": ["shell"],
        },
    ]


def check_case(case: JsonObject, iteration: int) -> JsonObject | None:
    response = response_for_case(case)
    normalized, _details = normalize_responses_response(response, request_body())
    text = response_text(normalized)
    tools = structured_tool_names(normalized)
    expected_tools = case["expected_tools"]

    if RAW_TOOL_SYNTAX_RE.search(text):
        return {"iteration": iteration, "case": case["name"], "issue": "raw_tool_syntax", "text": text[:500]}
    for expected in expected_tools:
        if expected not in tools:
            return {"iteration": iteration, "case": case["name"], "issue": "missing_tool", "expected": expected, "tools": tools}
    unexpected = [tool for tool in tools if tool not in expected_tools]
    if unexpected:
        return {"iteration": iteration, "case": case["name"], "issue": "unexpected_tool", "unexpected": unexpected}
    return None


def request_body() -> JsonObject:
    return {
        "model": "GLM-4.7-Flash",
        "tool_choice": "auto",
        "tools": TOOLS,
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Use the right tool."}]}],
    }


def response_for_case(case: JsonObject) -> JsonObject:
    output: list[JsonObject] = []
    reasoning_text = case.get("reasoning_text")
    if isinstance(reasoning_text, str):
        output.append(
            {
                "id": "reasoning_test",
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": reasoning_text}],
            }
        )
    text = case.get("text")
    if isinstance(text, str):
        output.append(
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        )
    response = {"id": "resp_test", "output": output}
    output_text = case.get("output_text")
    if isinstance(output_text, str):
        response["output_text"] = output_text
    return response


def response_text(response: JsonObject) -> str:
    pieces: list[str] = []
    if isinstance(response.get("output_text"), str):
        pieces.append(response["output_text"])
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                pieces.append(part["text"])
    return "\n".join(pieces)


def structured_tool_names(response: JsonObject) -> list[str]:
    names: list[str] = []
    for item in response.get("output") or []:
        if isinstance(item, dict) and item.get("type") in ("function_call", "custom_tool_call"):
            name = item.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def glm_call(name: str, args: JsonObject, rng: random.Random) -> str:
    parts = [open_tag("tool_call", rng), name]
    for key, value in args.items():
        parts.extend(
            [
                open_tag("arg_key", rng),
                key,
                close_tag("arg_key", rng),
                open_tag("arg_value", rng),
                json.dumps(value, ensure_ascii=True),
                close_tag("arg_value", rng),
            ]
        )
    parts.append(close_tag("tool_call", rng))
    return "".join(parts)


def open_tag(name: str, rng: random.Random) -> str:
    return f"<{outer_ws(rng)}{split_name(name, rng)}{outer_ws(rng)}>"


def close_tag(name: str, rng: random.Random) -> str:
    return f"</{outer_ws(rng)}{split_name(name, rng)}{outer_ws(rng)}>"


def split_name(name: str, rng: random.Random) -> str:
    pieces: list[str] = []
    for char in name:
        if char == "_" and rng.random() < 0.5:
            pieces.append(whitespace(rng))
        pieces.append(char)
        if rng.random() < 0.35:
            pieces.append(whitespace(rng))
    return "".join(pieces)


def outer_ws(rng: random.Random) -> str:
    return whitespace(rng) if rng.random() < 0.35 else ""


def whitespace(rng: random.Random) -> str:
    return rng.choice([" ", "\t", "\n", "\n  ", "\r\n  "])


if __name__ == "__main__":
    raise SystemExit(main())
