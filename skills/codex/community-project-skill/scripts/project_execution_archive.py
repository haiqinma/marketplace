#!/usr/bin/env python3
"""Capture and publish an AI-assisted Project task execution.

The local state file is the assembly point. Project remains the destination and
the task conversation is the attachment boundary; this script has no Warehouse
dependency.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from project_api import ProjectApiError, load_config, request_api, request_upload


SCHEMA = "yeying.project.execution-archive.v1"
REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = {
    "authorization",
    "access",
    "api",
    "app",
    "cookie",
    "password",
    "private",
    "secret",
    "token",
    "key",
    "ak",
    "sk",
}
SENSITIVE_VALUE = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]+|(?:sk|ak|token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+)"
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_execution_state_path(workdir: Path, task_id: int) -> Path:
    return workdir / f".project-execution-{task_id}.json"


def default_execution_output_dir(workdir: Path, task_id: int) -> Path:
    return workdir / f".project-execution-{task_id}"


def redact(value: Any, key: str = "") -> Any:
    """Remove credentials from nested records while preserving useful structure."""
    normalized_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key)).replace("-", "_").lower()
    key_parts = set(normalized_key.split("_"))
    sensitive_exact = {"authorization", "cookie", "password", "secret", "token", "ak", "sk"}
    sensitive_compound = {"access_token", "api_key", "app_key", "private_key", "secret_key", "access_key"}
    if normalized_key in sensitive_exact or normalized_key in sensitive_compound or key_parts.intersection(SENSITIVE_KEY_PARTS - {"access", "api", "app", "private", "key"}):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item, key) for item in value]
    if isinstance(value, str):
        return SENSITIVE_VALUE.sub(REDACTED, value)
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectApiError(f"无法读取 JSON 文件 {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def attach_lifecycle(state: dict[str, Any], lifecycle_file: Path | None = None) -> dict[str, Any]:
    """Attach a task-bound lifecycle snapshot without carrying local paths into the archive."""
    selected = lifecycle_file or (Path(state["lifecycle_file"]) if state.get("lifecycle_file") else None)
    if not selected:
        return state
    lifecycle = read_json(selected)
    if not isinstance(lifecycle, dict):
        raise ProjectApiError("生命周期快照必须是 JSON 对象")
    if int(lifecycle.get("project_id") or 0) != int(state["project_id"]) or int(lifecycle.get("task_id") or 0) != int(state["task_id"]):
        raise ProjectApiError("生命周期快照的 Project/Task 与执行归档绑定不一致")
    state["lifecycle"] = redact(lifecycle)
    return state


def load_state(path: Path) -> dict[str, Any]:
    state = read_json(path)
    if not isinstance(state, dict) or state.get("schema") != SCHEMA:
        raise ProjectApiError(f"状态文件不是 {SCHEMA}: {path}")
    return state


def content_from_args(args: argparse.Namespace) -> Any:
    if args.record_file:
        return read_json(args.record_file)
    content: Any = args.content
    if args.content_file:
        content = args.content_file.read_text(encoding="utf-8")
    if content is None:
        raise ProjectApiError("append 需要 --record-file、--content 或 --content-file")
    record: dict[str, Any] = {"role": args.role, "content": content, "kind": args.kind}
    if args.metadata:
        try:
            record["metadata"] = json.loads(args.metadata)
        except json.JSONDecodeError as exc:
            raise ProjectApiError("--metadata 必须是有效 JSON") from exc
    return record


def render_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def render_collapsed(label: str, value: Any) -> list[str]:
    """Keep the archive index readable while preserving every captured record."""
    return [
        "<details>",
        f"<summary>{label}</summary>",
        "",
        render_content(value),
        "",
        "</details>",
        "",
    ]


def render_markdown(state: dict[str, Any]) -> str:
    lines = [
        f"# Project 任务执行归档",
        "",
        f"- Project: `{state['project_id']}`",
        f"- Task: `{state['task_id']}`",
        f"- Execution: `{state['execution_id']}`",
        f"- Source: `{state['source_tool']}`",
        f"- Model: `{state.get('model') or 'unknown'}`",
        f"- Started: `{state['started_at']}`",
        f"- Finished: `{state.get('finished_at') or 'running'}`",
        f"- Status: `{state['status']}`",
        "",
        "## Completeness",
        "",
        f"- complete: `{str(state.get('complete', False)).lower()}`",
        f"- missing: `{', '.join(state.get('missing', [])) or 'none'}`",
        "",
        f"- captured records: `{len(state.get('records', []))}` (原始记录默认折叠，JSON transcript 保留脱敏详情)",
        "",
    ]
    if state.get("summary"):
        lines += ["## Summary", "", str(state["summary"]), ""]
    if state.get("result"):
        lines += ["## Result", "", render_content(state["result"]), ""]
    if state.get("lifecycle"):
        lines += ["## Development Lifecycle", "", render_content(state["lifecycle"]), ""]
    for section, label in (("repository", "Repository"), ("commits", "Commits"), ("pull_requests", "Pull Requests"), ("verification", "Verification")):
        if state.get(section):
            lines += [f"## {label}", "", render_content(state[section]), ""]
    lines += ["## Records", "", "原始事件按条目折叠，先阅读摘要，需要审计时再展开。", ""]
    for index, record in enumerate(state.get("records", []), 1):
        role = record.get("role") or record.get("kind") or "event"
        kind = record.get("kind") or "message"
        lines += [f"### {index}. {role} / {kind}", ""]
        lines += render_collapsed("查看原始记录", record.get("content", record))
    if state.get("attachments"):
        lines += ["## Attachment References", ""]
        for attachment in state["attachments"]:
            lines.append(f"- `{attachment.get('name', 'attachment')}`: {attachment.get('uri', '')}")
        lines.append("")
    return "\n".join(lines)


def finalize_state(state: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    state["records"] = redact(state.get("records", []))
    state["attachments"] = redact(state.get("attachments", []))
    if state.get("summary") is not None:
        state["summary"] = redact(state["summary"])
    if state.get("result") is not None:
        state["result"] = redact(state["result"])
    for key in ("lifecycle", "repository", "commits", "pull_requests", "verification"):
        if state.get(key) is not None:
            state[key] = redact(state[key])
    state["finished_at"] = now()
    state["status"] = "succeeded" if state.get("complete") else "incomplete"
    transcript_md = output_dir / "transcript.md"
    transcript_json = output_dir / "transcript.json"
    transcript_md.write_text(render_markdown(state), encoding="utf-8")
    structured = {
        "schema": SCHEMA,
        "conversation": {
            "projectId": state["project_id"],
            "taskId": state["task_id"],
            "executionId": state["execution_id"],
            "sourceTool": state["source_tool"],
            "model": state.get("model"),
            "startedAt": state["started_at"],
            "finishedAt": state["finished_at"],
            "status": state["status"],
        },
        "complete": bool(state.get("complete")),
        "missing": state.get("missing", []),
        "records": state.get("records", []),
        "attachments": state.get("attachments", []),
        "summary": state.get("summary"),
        "result": state.get("result"),
        "lifecycle": state.get("lifecycle"),
        "repository": state.get("repository"),
        "commits": state.get("commits", []),
        "pullRequests": state.get("pull_requests", []),
        "verification": state.get("verification", []),
    }
    write_json(transcript_json, structured)
    files = [
        {"name": path.name, "sha256": digest(path), "size": path.stat().st_size}
        for path in (transcript_md, transcript_json)
    ]
    manifest = {
        "schema": SCHEMA,
        "executionId": state["execution_id"],
        "projectId": state["project_id"],
        "taskId": state["task_id"],
        "sourceTool": state["source_tool"],
        "model": state.get("model"),
        "startedAt": state["started_at"],
        "finishedAt": state["finished_at"],
        "exportedAt": now(),
        "complete": bool(state.get("complete")),
        "missing": state.get("missing", []),
        "redacted": True,
        "recordCount": len(state.get("records", [])),
        "lifecycleStage": (state.get("lifecycle") or {}).get("stage"),
        "lifecycleSha256": hashlib.sha256(
            json.dumps(state["lifecycle"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest() if state.get("lifecycle") else None,
        "files": files,
    }
    manifest_path = output_dir / "manifest.json"
    write_json(manifest_path, manifest)
    state["archive_dir"] = str(output_dir)
    state["archive_files"] = [item["name"] for item in files] + [manifest_path.name]
    state["manifest"] = manifest
    state["finalized_at"] = now()
    return state


def task_dialog_id(api: dict[str, str], task_id: int) -> int:
    task = request_api(api, "GET", "/api/project/task/one", {"task_id": task_id})
    dialog_id = int(task.get("dialog_id") or 0)
    if not dialog_id:
        raise ProjectApiError(f"任务 {task_id} 没有可用对话，无法上传任务附件")
    return dialog_id


def existing_task_files(api: dict[str, str], task_id: int) -> dict[str, dict[str, Any]]:
    data = request_api(api, "GET", "/api/project/task/files", {"task_id": task_id})
    return {str(item.get("name")): item for item in (data if isinstance(data, list) else []) if item.get("name")}


def verify_existing(api: dict[str, str], item: dict[str, Any], path: Path) -> None:
    file_id = int(item.get("id") or 0)
    if not file_id:
        raise ProjectApiError(f"任务附件 {path.name} 缺少文件 ID，无法验证幂等性")
    remote = request_api(api, "GET", "/api/project/task/filedown", {"file_id": file_id}, raw=True)
    remote_digest = hashlib.sha256(remote).hexdigest()
    if remote_digest != digest(path):
        raise ProjectApiError(f"任务已有同名归档但内容不同: {path.name}")


def publish(
    state_path: Path,
    state: dict[str, Any],
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    archive_dir = Path(state.get("archive_dir", ""))
    if state.get("status") not in ("succeeded", "incomplete") or not archive_dir.is_dir():
        raise ProjectApiError("请先执行 finalize")
    api = load_config(config_path) if config_path else load_config()
    existing = existing_task_files(api, int(state["task_id"]))
    dialog_id = task_dialog_id(api, int(state["task_id"]))
    uploaded: list[dict[str, Any]] = []
    for name in ("transcript.md", "transcript.json", "manifest.json"):
        path = archive_dir / name
        if not path.is_file():
            raise ProjectApiError(f"归档文件不存在: {path}")
        deterministic_name = f"execution-{state['execution_id']}-{name}"
        target = existing.get(deterministic_name)
        if target:
            verify_existing(api, target, path)
            uploaded.append({"name": deterministic_name, "file_id": target.get("id"), "reused": True})
            continue
        renamed = archive_dir / deterministic_name
        renamed.write_bytes(path.read_bytes())
        try:
            result = request_upload(api, "/api/dialog/msg/sendfile", {"dialog_id": dialog_id}, "files", renamed)
        finally:
            renamed.unlink(missing_ok=True)
        file_id = result.get("id") if isinstance(result, dict) else None
        uploaded.append({"name": deterministic_name, "file_id": file_id, "reused": False})
    marker = f"[execution:{state['execution_id']}]"
    messages = request_api(api, "GET", "/api/dialog/msg/list", {"dialog_id": dialog_id, "take": 100})
    message_text = json.dumps(messages, ensure_ascii=False)
    comment_sent = marker in message_text
    if not comment_sent:
        comment = (
            f"{marker} 执行过程已归档。\n\n"
            f"状态：{state['status']}；完整：{str(state.get('complete', False)).lower()}。\n"
            f"归档文件：{', '.join(item['name'] for item in uploaded)}。"
        )
        request_api(api, "POST", "/api/dialog/msg/sendtext", {
            "dialog_id": dialog_id, "text": comment, "text_type": "md",
        })
    state["published"] = {"files": uploaded, "commentSent": not comment_sent, "publishedAt": now()}
    write_json(state_path, state)
    return state["published"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project 任务执行过程归档工具")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="创建执行归档状态")
    start.add_argument("--project-id", type=int, required=True)
    start.add_argument("--task-id", type=int, required=True)
    start.add_argument("--source-tool", required=True, help="codex、claude 或其他执行工具")
    start.add_argument("--model")
    start.add_argument("--execution-id")
    start.add_argument("--lifecycle-file", type=Path, help="研发生命周期 JSON 快照")
    start.add_argument("--state", type=Path, help="默认写入当前目录 .project-execution-<task-id>.json")
    start.add_argument("--output-dir", type=Path, help="默认写入当前目录 .project-execution-<task-id>/")

    append = sub.add_parser("append", help="追加一条可获得的执行记录")
    append.add_argument("--state", type=Path, required=True)
    append.add_argument("--record-file", type=Path)
    append.add_argument("--role", default="event")
    append.add_argument("--kind", default="message")
    append.add_argument("--content")
    append.add_argument("--content-file", type=Path)
    append.add_argument("--metadata")

    finalize = sub.add_parser("finalize", help="生成 transcript 和 manifest")
    finalize.add_argument("--state", type=Path, required=True)
    finalize.add_argument("--summary")
    finalize.add_argument("--summary-file", type=Path)
    finalize.add_argument("--result")
    finalize.add_argument("--result-file", type=Path)
    finalize.add_argument("--lifecycle-file", type=Path, help="覆盖 start 阶段指定的生命周期快照")
    complete = finalize.add_mutually_exclusive_group()
    complete.add_argument("--complete", action="store_true")
    complete.add_argument("--incomplete", action="store_false", dest="complete")
    finalize.set_defaults(complete=None)
    finalize.add_argument("--missing", action="append", default=[])

    publish_cmd = sub.add_parser("publish", help="上传归档到任务并写入引用")
    publish_cmd.add_argument("--state", type=Path, required=True)
    publish_cmd.add_argument("--config", help="Project TOML 配置文件")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            workdir = Path.cwd()
            state_path = args.state or default_execution_state_path(workdir, args.task_id)
            output_dir = args.output_dir or default_execution_output_dir(workdir, args.task_id)
            lifecycle_file = args.lifecycle_file
            default_lifecycle = workdir / f".project-lifecycle-{args.task_id}.json"
            if lifecycle_file is None and default_lifecycle.is_file():
                lifecycle_file = default_lifecycle
            state = {
                "schema": SCHEMA,
                "project_id": args.project_id,
                "task_id": args.task_id,
                "execution_id": args.execution_id or str(uuid.uuid4()),
                "source_tool": args.source_tool,
                "model": args.model,
                "started_at": now(),
                "status": "running",
                "complete": False,
                "missing": ["execution completion"],
                "records": [],
                "attachments": [],
                "output_dir": str(output_dir),
                "lifecycle_file": str(lifecycle_file) if lifecycle_file else None,
                "commits": [],
                "pull_requests": [],
                "verification": [],
            }
            write_json(state_path, state)
            print(json.dumps({"executionId": state["execution_id"], "state": str(state_path)}, ensure_ascii=False, indent=2))
        elif args.command == "append":
            state = load_state(args.state)
            record = redact(content_from_args(args))
            if isinstance(record, list):
                state["records"].extend(record)
            else:
                state["records"].append(record)
            write_json(args.state, state)
            print(json.dumps({"records": len(state["records"]), "executionId": state["execution_id"]}, ensure_ascii=False, indent=2))
        elif args.command == "finalize":
            state = load_state(args.state)
            summary = args.summary_file.read_text(encoding="utf-8") if args.summary_file else args.summary
            result: Any = args.result_file.read_text(encoding="utf-8") if args.result_file else args.result
            if summary is not None:
                state["summary"] = redact(summary)
            if result is not None:
                state["result"] = redact(result)
            attach_lifecycle(state, args.lifecycle_file)
            if args.complete is not None:
                state["complete"] = args.complete
                state["missing"] = [] if args.complete else (args.missing or ["platform hidden context"])
            output_dir = Path(state["output_dir"])
            state = finalize_state(state, output_dir)
            write_json(args.state, state)
            print(json.dumps({"executionId": state["execution_id"], "archiveDir": str(output_dir), "files": state["archive_files"]}, ensure_ascii=False, indent=2))
        elif args.command == "publish":
            state = load_state(args.state)
            print(json.dumps(publish(args.state, state, args.config), ensure_ascii=False, indent=2))
        return 0
    except (ProjectApiError, OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
