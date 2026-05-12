from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


JsonObject = dict[str, Any]


@dataclass
class UpstreamCapabilities:
    probed: bool = False
    probe_mode: str = "off"
    supports_responses_user_input: bool | None = None
    supports_developer_role: bool | None = None
    supports_system_role: bool | None = None
    supports_native_tool_history: bool | None = None
    requires_flattened_input: bool = False
    probe_errors: list[JsonObject] = field(default_factory=list)

    def to_json(self) -> JsonObject:
        return asdict(self)


def disabled_capabilities() -> JsonObject:
    return UpstreamCapabilities(probed=False, probe_mode="off").to_json()


def probe_upstream_capabilities(
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
) -> JsonObject:
    probe_timeout = max(0.5, min(float(timeout), 8.0))
    capabilities = UpstreamCapabilities(probed=True, probe_mode="auto")

    user_status = run_probe(
        base_url,
        api_key,
        probe_timeout,
        probe_body(model, [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reply with OK."}]}]),
    )
    capabilities.supports_responses_user_input = user_status["ok"]
    record_error(capabilities, "responses_user_input", user_status)

    developer_status = run_probe(
        base_url,
        api_key,
        probe_timeout,
        probe_body(
            model,
            [
                {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "Reply tersely."}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reply with OK."}]},
            ],
        ),
    )
    capabilities.supports_developer_role = developer_status["ok"]
    record_error(capabilities, "developer_role", developer_status)

    system_status = run_probe(
        base_url,
        api_key,
        probe_timeout,
        probe_body(
            model,
            [
                {"type": "message", "role": "system", "content": [{"type": "input_text", "text": "Reply tersely."}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reply with OK."}]},
            ],
        ),
    )
    capabilities.supports_system_role = system_status["ok"]
    record_error(capabilities, "system_role", system_status)

    history_status = run_probe(
        base_url,
        api_key,
        probe_timeout,
        probe_body(
            model,
            [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Use the prior tool output."}]},
                {
                    "type": "function_call",
                    "name": "shell",
                    "call_id": "call_probe",
                    "arguments": "{\"command\":[\"powershell.exe\",\"-Command\",\"Write-Output OK\"]}",
                },
                {"type": "function_call_output", "call_id": "call_probe", "output": "OK"},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reply with OK."}]},
            ],
        ),
    )
    capabilities.supports_native_tool_history = history_status["ok"]
    record_error(capabilities, "native_tool_history", history_status)
    capabilities.requires_flattened_input = capabilities.supports_responses_user_input is False
    return capabilities.to_json()


def probe_body(model: str, input_items: list[JsonObject]) -> JsonObject:
    return {
        "model": model,
        "input": input_items,
        "temperature": 0,
        "max_output_tokens": 1,
        "stream": False,
        "store": False,
    }


def run_probe(base_url: str, api_key: str, timeout: float, body: JsonObject) -> JsonObject:
    url = urljoin(base_url.rstrip("/") + "/", "responses")
    raw = json.dumps(body, ensure_ascii=True).encode("utf-8")
    request = Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return {"ok": response.status < 400, "status": response.status, "message": response_message(payload)}
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "message": response_message(payload)}
    except (TimeoutError, URLError) as exc:
        return {"ok": None, "status": None, "message": str(exc), "error_type": exc.__class__.__name__}


def response_message(payload: str) -> str:
    if not payload:
        return ""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return payload[:500]
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
    return ""


def record_error(capabilities: UpstreamCapabilities, probe_name: str, status: JsonObject) -> None:
    if status.get("ok") is not False:
        return
    capabilities.probe_errors.append(
        {
            "probe": probe_name,
            "status": status.get("status"),
            "message": status.get("message"),
        }
    )
