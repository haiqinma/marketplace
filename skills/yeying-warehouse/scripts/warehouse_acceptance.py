#!/usr/bin/env python3
"""Non-destructive smoke test for a deployed Warehouse HTTP Tool endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

from warehouse_config import ConfigError, load


TOOLS = {
    "warehouse.space.list",
    "warehouse.object.list",
    "warehouse.object.stat",
    "warehouse.object.read",
    "warehouse.object.put",
}


def config(config_path: str | None = None) -> tuple[str, str]:
    try:
        settings = load(config_path)
    except ConfigError as exc:
        raise RuntimeError(str(exc)) from exc
    return settings.base_url, settings.token


def request(base: str, token: str, method: str, suffix: str, payload: dict[str, Any] | None = None, trace_id: str = "") -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if trace_id:
        headers["X-Trace-ID"] = trace_id
    req = urllib.request.Request(base + suffix, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Warehouse HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Warehouse connection failed: {exc.reason}") from exc


def call(base: str, token: str, name: str, arguments: dict[str, Any], trace_id: str) -> dict[str, Any]:
    response = request(base, token, "POST", "/api/v1/public/tools/warehouse/call", {
        "name": name,
        "arguments": arguments,
        "traceId": trace_id,
    }, trace_id)
    if response.get("name") != name or "result" not in response:
        raise RuntimeError(f"unexpected {name} response")
    return response["result"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="TOML 配置文件，默认 ~/.yeying/skills/warehouse/config.toml")
    parser.add_argument("--path", required=True, help="已授权的测试对象路径；测试不会删除该对象")
    parser.add_argument("--list-prefix", help="可选的已授权 list 前缀；默认使用对象所在空间根路径")
    parser.add_argument("--content", default="warehouse-tool-acceptance")
    parser.add_argument("--trace-id", default="")
    args = parser.parse_args()
    trace_id = args.trace_id or "acceptance-" + uuid.uuid4().hex
    try:
        base, token = config(args.config)
        catalog = request(base, token, "GET", "/api/v1/public/tools/warehouse", trace_id=trace_id)
        actual = {item.get("name") for item in catalog.get("tools", [])}
        missing = sorted(TOOLS - actual)
        if missing:
            raise RuntimeError("catalog missing tools: " + ", ".join(missing))
        space = args.path.strip("/").split("/", 1)[0]
        prefix = args.list_prefix or ("/" + space + "/")
        listing = call(base, token, "warehouse.object.list", {"prefix": prefix, "delimiter": "/"}, trace_id)
        content = args.content
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        put_args = {
            "path": args.path,
            "content": content,
            "encoding": "utf-8",
            "contentType": "text/plain; charset=utf-8",
            "checksumSha256": checksum,
        }
        first = call(base, token, "warehouse.object.put", put_args, trace_id)
        second = call(base, token, "warehouse.object.put", put_args, trace_id)
        stat = call(base, token, "warehouse.object.stat", {"path": args.path}, trace_id)
        read = call(base, token, "warehouse.object.read", {"path": args.path, "mode": "content"}, trace_id)
        if first.get("checksumSha256") != checksum or second.get("checksumSha256") != checksum:
            raise RuntimeError("put checksum mismatch")
        if stat.get("checksumSha256") != checksum:
            raise RuntimeError("stat checksum mismatch")
        if read.get("content") != content or read.get("encoding") != "utf-8":
            raise RuntimeError("read content mismatch")
        print(json.dumps({
            "ok": True,
            "baseUrl": base,
            "traceId": trace_id,
            "path": args.path,
            "tools": sorted(actual),
            "listedPrefix": prefix,
            "size": stat.get("size"),
            "checksumSha256": checksum,
            "idempotentRetry": True,
            "note": "acceptance object is intentionally retained; remove it through the normal Warehouse API if needed",
        }, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, OSError, ValueError) as exc:
        print("验收失败: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
