#!/usr/bin/env python3
"""Small dependency-free client for the Warehouse HTTP Tool API."""

import argparse
import base64
import hashlib
import json
import mimetypes
import posixpath
import sys
import urllib.error
import urllib.request

from warehouse_config import ConfigError, load


def fail(message, code=2):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def load_settings(config_path=None):
    try:
        settings = load(config_path)
    except ConfigError as exc:
        fail(str(exc))
    return settings


def config(config_path=None):
    """Return the legacy base URL/token pair for callers importing this helper."""
    settings = load_settings(config_path)
    return settings.base_url, settings.token


def request(method, path, token, payload=None, trace_id=None):
    body = None
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if trace_id:
        headers["X-Trace-ID"] = trace_id
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            value = json.loads(raw.decode("utf-8")) if raw else {}
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.dumps(json.loads(raw), ensure_ascii=False)
        except json.JSONDecodeError:
            detail = raw
        print("Warehouse HTTP %d: %s" % (exc.code, detail), file=sys.stderr)
        return 10 if exc.code in (401, 403, 409, 412, 413) else 11
    except urllib.error.URLError as exc:
        print("Warehouse connection failed: %s" % exc.reason, file=sys.stderr)
        return 12


def call_tool(base, token, name, arguments, trace_id=None):
    payload = {"name": name, "arguments": arguments}
    if trace_id:
        payload["traceId"] = trace_id
    return request("POST", base + "/api/v1/public/tools/warehouse/call", token, payload, trace_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="TOML 配置文件，默认 ~/.yeying/skills/warehouse/config.toml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    call = sub.add_parser("call")
    call.add_argument("name")
    call.add_argument("arguments", nargs="?", default="{}", help="JSON object")
    call.add_argument("--trace-id")
    put = sub.add_parser("put")
    put.add_argument("path")
    put.add_argument("content")
    put.add_argument("--content-type", default="text/markdown; charset=utf-8")
    put.add_argument("--encoding", choices=("utf-8", "base64"), default="utf-8")
    put.add_argument("--overwrite", action="store_true")
    put.add_argument("--if-match", help="覆盖时要求对象 ETag 匹配")
    put.add_argument("--checksum-sha256", help="内容 SHA-256，支持 hex 或 base64")
    put.add_argument("--trace-id")
    put_file = sub.add_parser("put-file", help="上传本地文件到 Warehouse")
    put_file.add_argument("local_file", help="本地文件路径")
    put_file.add_argument(
        "warehouse_path",
        nargs="?",
        help="完整 Warehouse 对象路径；省略时使用配置中的 upload_directory",
    )
    put_file.add_argument("--content-type", help="覆盖自动检测到的 Content-Type")
    put_file.add_argument("--overwrite", action="store_true")
    put_file.add_argument("--if-match", help="覆盖时要求对象 ETag 匹配")
    put_file.add_argument("--trace-id")
    read = sub.add_parser("read")
    read.add_argument("path")
    read.add_argument("--max-bytes", type=int)
    read.add_argument("--trace-id")
    listing = sub.add_parser("list")
    listing.add_argument("prefix", nargs="?", default="/")
    listing.add_argument("--delimiter", default="/")
    listing.add_argument("--trace-id")
    stat = sub.add_parser("stat")
    stat.add_argument("path")
    stat.add_argument("--trace-id")
    args = parser.parse_args()
    settings = load_settings(args.config)
    base, token = settings.base_url, settings.token

    if args.command == "catalog":
        return request("GET", base + "/api/v1/public/tools/warehouse", token, trace_id=getattr(args, "trace_id", None))
    if args.command == "call":
        try:
            arguments = json.loads(args.arguments)
        except json.JSONDecodeError as exc:
            fail("arguments must be valid JSON: %s" % exc)
        if not isinstance(arguments, dict):
            fail("arguments must be a JSON object")
        return call_tool(base, token, args.name, arguments, args.trace_id)
    if args.command == "put":
        arguments = {"path": args.path, "content": args.content,
                     "encoding": args.encoding, "contentType": args.content_type,
                     "overwrite": args.overwrite}
        if args.if_match:
            arguments["ifMatch"] = args.if_match
        if args.checksum_sha256:
            arguments["checksumSha256"] = args.checksum_sha256
        return call_tool(base, token, "warehouse.object.put", arguments, args.trace_id)
    if args.command == "put-file":
        from pathlib import Path

        local_file = Path(args.local_file).expanduser()
        if not local_file.is_file():
            fail("local file does not exist or is not a regular file: %s" % local_file)
        if args.warehouse_path:
            warehouse_path = args.warehouse_path
        elif settings.upload_directory:
            warehouse_path = posixpath.join(settings.upload_directory, local_file.name)
        else:
            fail("set [warehouse].upload_directory or provide warehouse_path")
        try:
            if local_file.stat().st_size > 5 * 1024 * 1024:
                fail("local file exceeds the 5 MiB warehouse.object.put limit")
            content = local_file.read_bytes()
        except OSError as exc:
            fail("cannot read local file %s: %s" % (local_file, exc))
        max_bytes = 5 * 1024 * 1024
        if len(content) > max_bytes:
            fail("local file exceeds the 5 MiB warehouse.object.put limit")
        content_type = args.content_type or mimetypes.guess_type(local_file.name)[0]
        if content_type is None:
            try:
                content.decode("utf-8")
                content_type = "text/plain; charset=utf-8"
            except UnicodeDecodeError:
                content_type = "application/octet-stream"
        arguments = {
            "path": warehouse_path,
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
            "contentType": content_type,
            "checksumSha256": hashlib.sha256(content).hexdigest(),
            "overwrite": args.overwrite,
        }
        if args.if_match:
            arguments["ifMatch"] = args.if_match
        return call_tool(base, token, "warehouse.object.put", arguments, args.trace_id)
    if args.command == "read":
        arguments = {"path": args.path, "mode": "content"}
        if args.max_bytes is not None:
            arguments["maxBytes"] = args.max_bytes
        return call_tool(base, token, "warehouse.object.read", arguments, args.trace_id)
    if args.command == "list":
        return call_tool(base, token, "warehouse.object.list",
                         {"prefix": args.prefix, "delimiter": args.delimiter}, args.trace_id)
    return call_tool(base, token, "warehouse.object.stat", {"path": args.path}, args.trace_id)


if __name__ == "__main__":
    raise SystemExit(main())
