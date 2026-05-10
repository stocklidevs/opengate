from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from .proxy import build_proxy_error_response, forward_responses_request
from .streaming import response_stream_events, serialise_sse_comment
from .version import __version__


JsonObject = dict[str, Any]
DEFAULT_TEXT = "open-gate probe response"
SENSITIVE_HEADERS = {"authorization", "openai-organization", "openai-project", "api-key", "x-api-key"}


class CaptureServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], config: JsonObject):
        super().__init__(server_address, handler)
        self.config = config


class Handler(BaseHTTPRequestHandler):
    server: CaptureServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "open-gate",
                    "version": __version__,
                    "model": self.server.config.get("model"),
                    "mode": "proxy" if self.server.config.get("upstream_base_url") else "capture",
                    "normalization_mode": self.server.config.get("normalization_mode", "repair"),
                    "upstream_input_mode": self.server.config.get("upstream_input_mode", "auto"),
                    "context_policy": self.server.config.get("context_policy", "full"),
                    "context_max_chars": self.server.config.get("context_max_chars"),
                    "context_recent_items": self.server.config.get("context_recent_items"),
                    "instruction_policy": self.server.config.get("instruction_policy", "auto"),
                    "tool_schema_policy": self.server.config.get("tool_schema_policy", "auto"),
                    "stream_heartbeat_seconds": self.server.config.get("stream_heartbeat_seconds", 5.0),
                    "capture_dir": self.server.config.get("capture_dir"),
                }
            )
            return
        if path == "/v1/models":
            model = self.server.config["model"]
            self._send_json({"object": "list", "data": [{"id": model, "object": "model", "created": int(time.time()), "owned_by": "open-gate"}]})
            return
        self._send_json({"error": {"message": f"Unhandled path: {path}", "type": "not_found"}}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_json_body()

        if path == "/v1/responses" and self.server.config.get("upstream_base_url"):
            self._handle_proxy_response(path, body)
            return

        self._capture(path, body)

        if path == "/v1/responses":
            text = self._response_text()
            response = build_response(body, text, self.server.config["model"])
            if body.get("stream"):
                self._stream_response(response, text)
            else:
                self._send_json(response)
            return

        if path == "/v1/chat/completions":
            text = self._response_text()
            if body.get("stream"):
                self._stream_chat_completion(body, text)
            else:
                self._send_json(build_chat_completion(body, text, self.server.config["model"]))
            return

        self._send_json({"error": {"message": f"Unhandled path: {path}", "type": "not_found"}}, status=404)

    def _handle_proxy_response(self, path: str, body: JsonObject) -> None:
        if body.get("stream"):
            self._handle_proxy_response_stream(path, body)
            return

        started_at = datetime.now(timezone.utc)
        started_monotonic = time.monotonic()
        result = self._forward_proxy_response(body)
        timing = self._proxy_timing(started_at, started_monotonic, stream_heartbeats=0)
        response, status = self._proxy_response_from_result(body, result)
        self._capture_proxy_exchange(path, body, result, response, timing)
        self._send_json(response, status=status)

    def _handle_proxy_response_stream(self, path: str, body: JsonObject) -> None:
        result_queue: Queue[tuple[str, Any]] = Queue(maxsize=1)
        started_at = datetime.now(timezone.utc)
        started_monotonic = time.monotonic()

        def worker() -> None:
            try:
                result_queue.put(("result", self._forward_proxy_response(body)))
            except Exception as exc:  # pragma: no cover - defensive guard around upstream adapters.
                result_queue.put(("exception", exc))

        Thread(target=worker, daemon=True).start()
        self._start_sse_response()

        heartbeats = 0
        client_connected = True
        heartbeat_seconds = float(self.server.config["stream_heartbeat_seconds"])
        while True:
            try:
                kind, value = result_queue.get(timeout=heartbeat_seconds)
                break
            except Empty:
                heartbeats += 1
                if client_connected:
                    client_connected = self._write_sse_comment(f"open-gate waiting for upstream heartbeat={heartbeats}")

        timing = self._proxy_timing(started_at, started_monotonic, stream_heartbeats=heartbeats)
        if kind == "exception":
            upstream_response = {"error": {"message": str(value), "type": value.__class__.__name__}}
            response = build_proxy_error_response(body, 599, upstream_response)
            self._capture_proxy_exception(path, body, upstream_response, response, timing)
        else:
            result = value
            response, _status = self._proxy_response_from_result(body, result)
            self._capture_proxy_exchange(path, body, result, response, timing)

        if client_connected:
            self._write_response_events(response)

    def _forward_proxy_response(self, body: JsonObject) -> Any:
        return forward_responses_request(
            request_body=body,
            upstream_base_url=self.server.config["upstream_base_url"],
            api_key=self.server.config["upstream_api_key"],
            timeout=float(self.server.config["upstream_timeout"]),
            normalization_mode=self.server.config["normalization_mode"],
            upstream_input_mode=self.server.config["upstream_input_mode"],
            context_policy=self.server.config["context_policy"],
            context_max_chars=int(self.server.config["context_max_chars"]),
            context_recent_items=int(self.server.config["context_recent_items"]),
            instruction_policy=self.server.config["instruction_policy"],
            tool_schema_policy=self.server.config["tool_schema_policy"],
        )

    def _proxy_timing(self, started_at: datetime, started_monotonic: float, stream_heartbeats: int) -> JsonObject:
        completed_at = datetime.now(timezone.utc)
        return {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": round(time.monotonic() - started_monotonic, 3),
            "stream_heartbeats": stream_heartbeats,
        }

    def _proxy_response_from_result(self, body: JsonObject, result: Any) -> tuple[JsonObject, int]:
        response = result.returned_response
        status = 200
        if result.upstream_status >= 400:
            response = build_proxy_error_response(body, result.upstream_status, result.upstream_response)
            status = 502
        return response, status

    def _capture_proxy_exchange(
        self,
        path: str,
        body: JsonObject,
        result: Any,
        response: JsonObject,
        timing: JsonObject,
    ) -> None:
        self._capture_record(
            {
                "kind": "proxy_exchange",
                "method": self.command,
                "path": path,
                "client": self.client_address[0],
                "headers": self._safe_headers(),
                "request": body,
                "timing": timing,
                "upstream": {
                    "base_url": self.server.config["upstream_base_url"],
                    "status": result.upstream_status,
                    "request": result.upstream_request,
                    "transform": result.upstream_transform,
                    "response": result.upstream_response,
                },
                "normalization_mode": self.server.config["normalization_mode"],
                "normalization": result.normalization,
                "normalized_response": result.normalized_response,
                "response": response,
            },
            prefix="proxy",
        )

    def _capture_proxy_exception(
        self,
        path: str,
        body: JsonObject,
        upstream_response: JsonObject,
        response: JsonObject,
        timing: JsonObject,
    ) -> None:
        self._capture_record(
            {
                "kind": "proxy_exchange",
                "method": self.command,
                "path": path,
                "client": self.client_address[0],
                "headers": self._safe_headers(),
                "request": body,
                "timing": timing,
                "upstream": {
                    "base_url": self.server.config["upstream_base_url"],
                    "status": 599,
                    "request": None,
                    "transform": None,
                    "response": upstream_response,
                },
                "normalization_mode": self.server.config["normalization_mode"],
                "normalization": {"mode": self.server.config["normalization_mode"], "error": upstream_response["error"]},
                "normalized_response": response,
                "response": response,
            },
            prefix="proxy",
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.server.config.get("quiet"):
            return
        super().log_message(fmt, *args)

    def _read_json_body(self) -> JsonObject:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            loaded = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {"_raw": raw.decode("utf-8", errors="replace")}
        return loaded if isinstance(loaded, dict) else {"_value": loaded}

    def _capture(self, path: str, body: JsonObject) -> None:
        record = {
            "kind": "request",
            "method": self.command,
            "path": path,
            "client": self.client_address[0],
            "headers": self._safe_headers(),
            "body": body,
        }
        self._capture_record(record)

    def _capture_record(self, record: JsonObject, prefix: str = "capture") -> None:
        capture_dir = Path(self.server.config["capture_dir"])
        capture_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        record = {"captured_at": now.isoformat(), **record}
        name = f"{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}-{prefix}-{uuid.uuid4().hex[:8]}.json"
        (capture_dir / name).write_text(json.dumps(record, indent=2, ensure_ascii=True), encoding="utf-8")

    def _safe_headers(self) -> JsonObject:
        return {
            key: ("<redacted>" if key.lower() in SENSITIVE_HEADERS else value)
            for key, value in self.headers.items()
        }

    def _response_text(self) -> str:
        fixture = self.server.config.get("fixture")
        if fixture:
            return Path(fixture).read_text(encoding="utf-8")
        return self.server.config.get("text") or DEFAULT_TEXT

    def _send_json(self, payload: JsonObject, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _start_sse_response(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def _stream_response(self, response: JsonObject, text: str) -> None:
        self._start_sse_response()

        resp_id = response["id"]
        item = response["output"][0]
        item_id = item["id"]
        started = dict(response)
        started["status"] = "in_progress"
        started["output"] = []

        events = [
            {"type": "response.created", "sequence_number": 0, "response": started},
            {"type": "response.in_progress", "sequence_number": 1, "response": started},
            {"type": "response.output_item.added", "sequence_number": 2, "response_id": resp_id, "output_index": 0, "item": {**item, "content": [], "status": "in_progress"}},
            {"type": "response.content_part.added", "sequence_number": 3, "response_id": resp_id, "item_id": item_id, "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
            {"type": "response.output_text.delta", "sequence_number": 4, "response_id": resp_id, "item_id": item_id, "output_index": 0, "content_index": 0, "delta": text},
            {"type": "response.output_text.done", "sequence_number": 5, "response_id": resp_id, "item_id": item_id, "output_index": 0, "content_index": 0, "text": text},
            {"type": "response.content_part.done", "sequence_number": 6, "response_id": resp_id, "item_id": item_id, "output_index": 0, "content_index": 0, "part": item["content"][0]},
            {"type": "response.output_item.done", "sequence_number": 7, "response_id": resp_id, "output_index": 0, "item": item},
            {"type": "response.completed", "sequence_number": 8, "response": response},
        ]
        for event in events:
            self._write_sse(event["type"], event)

    def _stream_response_generic(self, response: JsonObject) -> None:
        self._start_sse_response()
        self._write_response_events(response)

    def _write_response_events(self, response: JsonObject) -> None:
        for event_name, payload in response_stream_events(response):
            self._write_sse(event_name, payload)

    def _stream_chat_completion(self, request: JsonObject, text: str) -> None:
        self._start_sse_response()
        model = request.get("model") or self.server.config["model"]
        chunk_id = f"chatcmpl_og_{uuid.uuid4().hex}"
        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
        }
        done = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        self._write_sse("message", chunk)
        self._write_sse("message", done)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _write_sse(self, event_name: str, payload: JsonObject) -> None:
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _write_sse_comment(self, comment: str) -> bool:
        try:
            self.wfile.write(serialise_sse_comment(comment))
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return False


def build_response(request: JsonObject, text: str, default_model: str) -> JsonObject:
    now = int(time.time())
    resp_id = f"resp_og_{uuid.uuid4().hex}"
    item_id = f"msg_og_{uuid.uuid4().hex}"
    model = request.get("model") or default_model
    return {
        "id": resp_id,
        "object": "response",
        "created_at": now,
        "status": "completed",
        "background": False,
        "error": None,
        "incomplete_details": None,
        "instructions": request.get("instructions"),
        "max_output_tokens": request.get("max_output_tokens"),
        "model": model,
        "output": [
            {
                "id": item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": request.get("parallel_tool_calls", True),
        "previous_response_id": request.get("previous_response_id"),
        "reasoning": request.get("reasoning"),
        "store": request.get("store", False),
        "temperature": request.get("temperature"),
        "text": request.get("text", {"format": {"type": "text"}}),
        "tool_choice": request.get("tool_choice", "auto"),
        "tools": request.get("tools", []),
        "top_p": request.get("top_p"),
        "truncation": request.get("truncation", "disabled"),
        "usage": {
            "input_tokens": 0,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 0,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 0,
        },
        "metadata": request.get("metadata", {}),
    }


def build_chat_completion(request: JsonObject, text: str, default_model: str) -> JsonObject:
    return {
        "id": f"chatcmpl_og_{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.get("model") or default_model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local Responses API capture server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--capture-dir", default="captures")
    parser.add_argument("--model", default="open-gate-probe")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--fixture", help="Text file to stream as the assistant response.")
    parser.add_argument("--upstream-base-url", "--upstream", dest="upstream_base_url", help="Forward /v1/responses to this OpenAI-compatible upstream base URL.")
    parser.add_argument("--upstream-api-key", default="sk-no-key-required")
    parser.add_argument("--upstream-timeout", type=float, default=120.0)
    parser.add_argument("--stream-heartbeat-seconds", type=float, default=5.0, help="Seconds between SSE keepalive comments while waiting for a buffered upstream response.")
    parser.add_argument(
        "--normalization-mode",
        choices=["repair", "observe"],
        default="repair",
        help="repair returns normalized responses; observe records normalizer findings but returns raw upstream responses.",
    )
    parser.add_argument(
        "--upstream-input-mode",
        choices=["auto", "native", "flatten"],
        default="auto",
        help="auto flattens Responses history that vLLM rejects; native forwards input unchanged; flatten always sends a string transcript upstream.",
    )
    parser.add_argument(
        "--context-policy",
        choices=["full", "spoon"],
        default="full",
        help="full sends the complete flattened transcript; spoon compacts older Codex history and keeps recent turns exact.",
    )
    parser.add_argument(
        "--context-max-chars",
        type=int,
        default=60000,
        help="Maximum flattened input characters sent upstream when --context-policy spoon is active.",
    )
    parser.add_argument(
        "--context-recent-items",
        type=int,
        default=10,
        help="Number of newest Responses input items kept exact when --context-policy spoon is active.",
    )
    parser.add_argument(
        "--instruction-policy",
        choices=["full", "auto", "digest"],
        default="auto",
        help="full forwards Codex instructions unchanged; auto/digest replace oversized instructions with an Open Gate digest.",
    )
    parser.add_argument(
        "--tool-schema-policy",
        choices=["full", "auto", "compact"],
        default="auto",
        help="full forwards tool schemas unchanged; auto/compact trim oversized schema descriptions before forwarding upstream.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.stream_heartbeat_seconds <= 0:
        parser.error("--stream-heartbeat-seconds must be greater than 0")
    if args.context_max_chars < 4000:
        parser.error("--context-max-chars must be at least 4000")
    if args.context_recent_items < 1:
        parser.error("--context-recent-items must be at least 1")

    config = {
        "capture_dir": args.capture_dir,
        "model": args.model,
        "text": args.text,
        "fixture": args.fixture,
        "upstream_base_url": args.upstream_base_url,
        "upstream_api_key": args.upstream_api_key,
        "upstream_timeout": args.upstream_timeout,
        "normalization_mode": args.normalization_mode,
        "upstream_input_mode": args.upstream_input_mode,
        "context_policy": args.context_policy,
        "context_max_chars": args.context_max_chars,
        "context_recent_items": args.context_recent_items,
        "instruction_policy": args.instruction_policy,
        "tool_schema_policy": args.tool_schema_policy,
        "stream_heartbeat_seconds": args.stream_heartbeat_seconds,
        "quiet": args.quiet,
    }
    server = CaptureServer((args.host, args.port), Handler, config)
    print(f"open-gate listening on http://{args.host}:{args.port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
