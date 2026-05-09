from __future__ import annotations

from copy import deepcopy
import json
import time
import uuid
from typing import Any, Iterable


JsonObject = dict[str, Any]


def response_stream_events(response: JsonObject) -> list[tuple[str, JsonObject]]:
    response = normalise_response_for_stream(response)
    response_id = response["id"]
    started = deepcopy(response)
    started["status"] = "in_progress"
    started["output"] = []

    events: list[tuple[str, JsonObject]] = []
    seq = 0
    events.append(("response.created", {"type": "response.created", "sequence_number": seq, "response": started}))
    seq += 1
    events.append(("response.in_progress", {"type": "response.in_progress", "sequence_number": seq, "response": started}))
    seq += 1

    for output_index, item in enumerate(response.get("output") or []):
        added_item = item_for_added_event(item)
        events.append(
            (
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "sequence_number": seq,
                    "response_id": response_id,
                    "output_index": output_index,
                    "item": added_item,
                },
            )
        )
        seq += 1

        item_type = item.get("type")
        if item_type == "message":
            for event_name, payload in message_part_events(response_id, item, output_index, seq):
                events.append((event_name, payload))
                seq = payload["sequence_number"] + 1
        elif item_type in ("function_call", "custom_tool_call"):
            for event_name, payload in function_call_argument_events(response_id, item, output_index, seq):
                events.append((event_name, payload))
                seq = payload["sequence_number"] + 1

        events.append(
            (
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "sequence_number": seq,
                    "response_id": response_id,
                    "output_index": output_index,
                    "item": item,
                },
            )
        )
        seq += 1

    completed = deepcopy(response)
    completed["status"] = completed.get("status") or "completed"
    events.append(("response.completed", {"type": "response.completed", "sequence_number": seq, "response": completed}))
    return events


def serialise_sse(events: Iterable[tuple[str, JsonObject]]) -> bytes:
    chunks: list[bytes] = []
    for event_name, payload in events:
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        chunks.append(f"event: {event_name}\n".encode("utf-8"))
        chunks.append(f"data: {data}\n\n".encode("utf-8"))
    return b"".join(chunks)


def normalise_response_for_stream(response: JsonObject) -> JsonObject:
    response = deepcopy(response)
    response.setdefault("id", f"resp_og_{uuid.uuid4().hex}")
    response.setdefault("object", "response")
    response.setdefault("created_at", int(time.time()))
    response.setdefault("status", "completed")
    output = response.setdefault("output", [])
    if not isinstance(output, list):
        response["output"] = []
        return response
    for item in output:
        if not isinstance(item, dict):
            continue
        item.setdefault("id", f"{item_prefix(item)}_og_{uuid.uuid4().hex}")
        item.setdefault("status", "completed")
        if item.get("type") == "message":
            item.setdefault("role", "assistant")
            item.setdefault("content", [])
        if item.get("type") in ("function_call", "custom_tool_call"):
            item.setdefault("call_id", f"call_og_{uuid.uuid4().hex}")
            arguments = item.get("arguments")
            if not isinstance(arguments, str):
                item["arguments"] = json.dumps(arguments or {}, ensure_ascii=True, separators=(",", ":"))
    return response


def item_prefix(item: JsonObject) -> str:
    if item.get("type") == "function_call":
        return "fc"
    if item.get("type") == "message":
        return "msg"
    if item.get("type") == "reasoning":
        return "rs"
    return "item"


def item_for_added_event(item: JsonObject) -> JsonObject:
    added = deepcopy(item)
    added["status"] = "in_progress"
    if added.get("type") == "message":
        added["content"] = []
    elif added.get("type") in ("function_call", "custom_tool_call"):
        added["arguments"] = ""
    return added


def message_part_events(response_id: str, item: JsonObject, output_index: int, seq: int) -> list[tuple[str, JsonObject]]:
    events: list[tuple[str, JsonObject]] = []
    item_id = item["id"]
    for content_index, part in enumerate(item.get("content") or []):
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type not in ("output_text", "text"):
            continue
        text = part.get("text") if isinstance(part.get("text"), str) else ""
        empty_part = deepcopy(part)
        empty_part["text"] = ""
        events.append(
            (
                "response.content_part.added",
                {
                    "type": "response.content_part.added",
                    "sequence_number": seq,
                    "response_id": response_id,
                    "item_id": item_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "part": empty_part,
                },
            )
        )
        seq += 1
        if text:
            events.append(
                (
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "sequence_number": seq,
                        "response_id": response_id,
                        "item_id": item_id,
                        "output_index": output_index,
                        "content_index": content_index,
                        "delta": text,
                    },
                )
            )
            seq += 1
        events.append(
            (
                "response.output_text.done",
                {
                    "type": "response.output_text.done",
                    "sequence_number": seq,
                    "response_id": response_id,
                    "item_id": item_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "text": text,
                },
            )
        )
        seq += 1
        events.append(
            (
                "response.content_part.done",
                {
                    "type": "response.content_part.done",
                    "sequence_number": seq,
                    "response_id": response_id,
                    "item_id": item_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "part": part,
                },
            )
        )
        seq += 1
    return events


def function_call_argument_events(response_id: str, item: JsonObject, output_index: int, seq: int) -> list[tuple[str, JsonObject]]:
    arguments = item.get("arguments") if isinstance(item.get("arguments"), str) else ""
    item_id = item["id"]
    events: list[tuple[str, JsonObject]] = []
    if arguments:
        events.append(
            (
                "response.function_call_arguments.delta",
                {
                    "type": "response.function_call_arguments.delta",
                    "sequence_number": seq,
                    "response_id": response_id,
                    "item_id": item_id,
                    "output_index": output_index,
                    "delta": arguments,
                },
            )
        )
        seq += 1
    events.append(
        (
            "response.function_call_arguments.done",
            {
                "type": "response.function_call_arguments.done",
                "sequence_number": seq,
                "response_id": response_id,
                "item_id": item_id,
                "output_index": output_index,
                "arguments": arguments,
            },
        )
    )
    return events
