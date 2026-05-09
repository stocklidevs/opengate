from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


JsonObject = dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe OpenAI-compatible server JSON request-size behavior.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key", default="sk-no-key-required")
    parser.add_argument("--sizes", default="4096,8192,16384,65536,262144", help="Comma-separated prompt byte sizes.")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    results = []
    for size in parse_sizes(args.sizes):
        results.append(probe_size(args.base_url, args.model, args.api_key, size, args.timeout))

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "model": args.model,
        "results": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if all(item["ok"] for item in results) else 1


def parse_sizes(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def probe_size(base_url: str, model: str, api_key: str, size: int, timeout: float) -> JsonObject:
    prompt = "a" * size
    body = {"model": model, "prompt": prompt}
    raw = json.dumps(body, ensure_ascii=True).encode("utf-8")
    request = Request(
        urljoin(base_url.rstrip("/") + "/", "../tokenize"),
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    started_size = len(raw)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "prompt_bytes": size,
            "request_bytes": started_size,
            "ok": True,
            "status": 200,
            "token_count": payload.get("count"),
            "max_model_len": payload.get("max_model_len"),
        }
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "prompt_bytes": size,
            "request_bytes": started_size,
            "ok": False,
            "status": exc.code,
            "error": detail[:1000],
        }
    except URLError as exc:
        return {
            "prompt_bytes": size,
            "request_bytes": started_size,
            "ok": False,
            "status": None,
            "error": str(exc.reason),
        }


if __name__ == "__main__":
    raise SystemExit(main())
