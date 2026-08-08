#!/usr/bin/env python3
"""Signed client for the YeYing Project automation API."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path.home() / ".config" / "yeying" / "project.json"


class ProjectApiError(RuntimeError):
    pass


def normalize_comment_content(content: str) -> str:
    """Accept escaped newlines from shell and agent command invocations."""
    return content.replace("\\r\\n", "\n").replace("\\n", "\n")


def markdown_to_task_html(content: str) -> str:
    """Convert the Markdown accepted by the Skill into Task's HTML editor format."""
    content = normalize_comment_content(content).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not content:
        return ""

    def inline(value: str) -> str:
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
        value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
        value = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", value)
        return re.sub(
            r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
            r'<a href="\2" target="_blank">\1</a>',
            value,
        )

    blocks: list[str] = []
    paragraph: list[str] = []
    list_tag = ""
    list_items: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{'<br>'.join(inline(line) for line in paragraph)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_tag, list_items
        if list_items:
            blocks.append(f"<{list_tag}>{''.join(f'<li>{inline(item)}</li>' for item in list_items)}</{list_tag}>")
            list_items = []
            list_tag = ""

    for source_line in content.split("\n"):
        line = source_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        unordered = re.match(r"^[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
        elif unordered or ordered:
            flush_paragraph()
            next_tag = "ul" if unordered else "ol"
            if list_items and list_tag != next_tag:
                flush_list()
            list_tag = next_tag
            list_items.append((unordered or ordered).group(1))
        else:
            flush_list()
            paragraph.append(line)
    flush_paragraph()
    flush_list()
    return "".join(blocks)


def load_config() -> dict[str, str]:
    config_path = Path(os.environ.get("YEYING_PROJECT_CONFIG", DEFAULT_CONFIG)).expanduser()
    config: dict[str, Any] = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectApiError(f"无法读取配置 {config_path}: {exc}") from exc

    resolved = {
        "url": os.environ.get("YEYING_PROJECT_URL") or config.get("url", ""),
        "access_key": os.environ.get("YEYING_PROJECT_AK") or config.get("access_key", ""),
        "secret_key": os.environ.get("YEYING_PROJECT_SK") or config.get("secret_key", ""),
    }
    missing = [key for key, value in resolved.items() if not value]
    if missing:
        raise ProjectApiError(
            f"缺少配置: {', '.join(missing)}。请设置环境变量或创建 {config_path}"
        )
    resolved["url"] = resolved["url"].rstrip("/")
    return resolved


def canonical_query(params: dict[str, Any]) -> str:
    items: list[tuple[str, str]] = []
    for key in sorted(params):
        value = params[key]
        values = value if isinstance(value, list) else [value]
        for item in values:
            items.append((key, str(item)))
    return urllib.parse.urlencode(items, doseq=True, quote_via=urllib.parse.quote)


def request_api(
    config: dict[str, str],
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    *,
    raw: bool = False,
) -> Any:
    method = method.upper()
    params = params or {}
    query = canonical_query(params) if method == "GET" else ""
    body = b"" if method == "GET" else json.dumps(
        params, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    nonce = secrets.token_hex(16)
    canonical = "\n".join(
        [method, path, query, hashlib.sha256(body).hexdigest(), timestamp, nonce]
    )
    derived_key = hashlib.sha256(config["secret_key"].encode("utf-8")).hexdigest().encode("ascii")
    signature = hmac.new(derived_key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{config['url']}{path}"
    if query:
        url = f"{url}?{query}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-YY-AK": config["access_key"],
        "X-YY-Timestamp": timestamp,
        "X-YY-Nonce": nonce,
        "X-YY-Signature": signature,
        "User-Agent": "yeying-project-collaboration-skill/1.0",
    }
    request = urllib.request.Request(url, data=body if method != "GET" else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
            if raw:
                return content
            payload = json.loads(content.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProjectApiError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProjectApiError(f"请求 Project 失败: {exc}") from exc

    if payload.get("ret") != 1:
        raise ProjectApiError(str(payload.get("msg") or "Project API 返回失败"))
    return payload.get("data")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YeYing Project 自动化协作客户端")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("projects", help="列出令牌可访问项目")

    tasks = subparsers.add_parser("tasks", help="列出项目任务")
    tasks.add_argument("--project-id", type=int, required=True)
    tasks.add_argument("--keyword")
    tasks.add_argument("--page", type=int, default=1)
    tasks.add_argument("--pagesize", type=int, default=50)

    task = subparsers.add_parser("task", help="读取任务详情和最近讨论")
    task.add_argument("--task-id", type=int, required=True)

    comment = subparsers.add_parser("comment", help="追加任务评论")
    comment.add_argument("--task-id", type=int, required=True)
    comment.add_argument("--update-id", type=int, help="编辑当前用户发送的指定消息")
    content = comment.add_mutually_exclusive_group(required=True)
    content.add_argument("--content")
    content.add_argument("--content-file", type=Path)

    update = subparsers.add_parser("update", help="更新任务普通字段")
    update.add_argument("--task-id", type=int, required=True)
    update.add_argument("--name")
    update_content = update.add_mutually_exclusive_group()
    update_content.add_argument("--content", help="Markdown 格式的任务详情")
    update_content.add_argument("--content-file", type=Path, help="包含 Markdown 任务详情的 UTF-8 文件")
    update.add_argument("--content-format", choices=("markdown", "html"), default="markdown")
    update.add_argument("--color")
    update.add_argument("--task-tag", help="JSON 数组")
    update.add_argument("--priority-level", type=int, dest="p_level")
    update.add_argument("--priority-name", dest="p_name")
    update.add_argument("--priority-color", dest="p_color")
    update.add_argument("--times", help="JSON 对象或数组")

    status = subparsers.add_parser("status", help="更新任务状态")
    status.add_argument("--task-id", type=int, required=True)
    status.add_argument("--flow-item-id", type=int)
    completed = status.add_mutually_exclusive_group()
    completed.add_argument("--completed", action="store_true", dest="completed")
    completed.add_argument("--not-completed", action="store_false", dest="completed")
    status.set_defaults(completed=None)

    file_info = subparsers.add_parser("file-info", help="获取文件下载信息")
    file_info.add_argument("--file-id", type=int, required=True)

    download = subparsers.add_parser("download", help="下载文件")
    download.add_argument("--file-id", type=int, required=True)
    download.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config()
        if args.command == "projects":
            data = request_api(config, "GET", "/api/project/lists", {"getstatistics": "no"})
        elif args.command == "tasks":
            params = {"project_id": args.project_id, "page": args.page, "pagesize": args.pagesize}
            if args.keyword:
                params["name"] = args.keyword
            data = request_api(config, "GET", "/api/project/task/lists", params)
        elif args.command == "task":
            task = request_api(config, "GET", "/api/project/task/one", {"task_id": args.task_id})
            content = request_api(config, "GET", "/api/project/task/content", {"task_id": args.task_id})
            flows = request_api(config, "GET", "/api/project/task/flow", {"task_id": args.task_id})
            files = request_api(config, "GET", "/api/project/task/files", {"task_id": args.task_id})
            data = {"task": task, "content": content, "flows": flows, "files": files}
            dialog_id = int(task.get("dialog_id") or 0)
            if dialog_id:
                data["messages"] = request_api(config, "GET", "/api/dialog/msg/list", {
                    "dialog_id": dialog_id, "take": 50,
                })
        elif args.command == "comment":
            text = args.content
            if args.content_file:
                text = args.content_file.read_text(encoding="utf-8")
            text = normalize_comment_content(text)
            dialog = request_api(config, "GET", "/api/project/task/dialog", {"task_id": args.task_id})
            params = {
                "dialog_id": dialog["dialog_id"], "text": text, "text_type": "md",
            }
            if args.update_id:
                params["update_id"] = args.update_id
            data = request_api(config, "POST", "/api/dialog/msg/sendtext", params)
        elif args.command == "update":
            params = {"task_id": args.task_id}
            for key in ("name", "color", "p_level", "p_name", "p_color"):
                value = getattr(args, key)
                if value is not None:
                    params[key] = value
            content = args.content
            if args.content_file:
                content = args.content_file.read_text(encoding="utf-8")
            if content is not None:
                params["content"] = content if args.content_format == "html" else markdown_to_task_html(content)
            for key in ("task_tag", "times"):
                value = getattr(args, key)
                if value is not None:
                    try:
                        params[key] = json.loads(value)
                    except json.JSONDecodeError as exc:
                        raise ProjectApiError(f"--{key.replace('_', '-')} 必须是有效 JSON") from exc
            if len(params) == 1:
                raise ProjectApiError("update 至少需要一个待更新字段")
            data = request_api(config, "POST", "/api/project/task/update", params)
        elif args.command == "status":
            params = {"task_id": args.task_id}
            if args.flow_item_id is not None:
                params["flow_item_id"] = args.flow_item_id
            if args.completed is not None:
                params["complete_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M") if args.completed else False
            if len(params) == 1:
                raise ProjectApiError("status 需要 --flow-item-id、--completed 或 --not-completed")
            data = request_api(config, "POST", "/api/project/task/update", params)
        elif args.command == "file-info":
            data = request_api(config, "GET", "/api/project/task/filedetail", {"file_id": args.file_id})
        else:
            data = request_api(
                config, "GET", "/api/project/task/filedown", {"file_id": args.file_id}, raw=True
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            data = {"file_id": args.file_id, "output": str(args.output), "size": len(data)}
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except (ProjectApiError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
