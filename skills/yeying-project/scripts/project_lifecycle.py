#!/usr/bin/env python3
"""Track and gate the Project task development lifecycle."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from project_agent_context import (
    add_agent_arguments,
    build_agent_context,
    context_from_args,
    ensure_state_agent_context,
    merge_state_agent_context,
    primary_model,
)
from project_api import ProjectApiError, ensure_task_dialog_id, load_config, markdown_to_task_html, request_api
from project_execution_archive import redact
from project_task_binding import task_marker_name


SCHEMA = "yeying.project.development-lifecycle.v1"
STAGES = (
    "intake",
    "analysis",
    "solution",
    "approval",
    "implementation",
    "verification",
    "delivery",
    "audit",
    "completed",
)
RECORD_KINDS = (
    "analysis",
    "solution",
    "decision",
    "implementation",
    "documentation",
    "verification",
    "pull_request",
    "review",
    "execution_archive",
)
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "analysis": ("understanding", "in_scope", "out_of_scope", "evidence", "constraints", "risks"),
    "solution": ("options", "comparison", "recommendation", "acceptance_criteria", "test_plan"),
    "documentation": ("paths", "status", "updated", "no_update_reason", "cross_project_impact"),
    "verification": ("commands", "environment", "passed", "results"),
    "pull_request": ("repository", "branch", "commit_sha", "url"),
    "execution_archive": ("execution_id", "complete", "published_at"),
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectApiError(f"无法读取 JSON 文件 {path}: {exc}") from exc


def load_state(path: Path) -> dict[str, Any]:
    state = read_json(path)
    if not isinstance(state, dict) or state.get("schema") != SCHEMA:
        raise ProjectApiError(f"生命周期文件不是 {SCHEMA}: {path}")
    return state


def default_state_path(workdir: Path, task_id: int) -> Path:
    return workdir / f".project-lifecycle-{task_id}.json"


def initialize(
    project_id: int,
    task_id: int,
    workdir: Path,
    state_path: Path,
    config_path: str | Path | None = None,
    agent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    task = request_api(config, "GET", "/api/project/task/one", {"task_id": task_id})
    task_project_id = int(task.get("project_id") or 0)
    if task_project_id != project_id:
        raise ProjectApiError(f"任务 {task_id} 属于 Project {task_project_id}，不是 {project_id}")
    workdir.mkdir(parents=True, exist_ok=True)
    marker = {"project_id": project_id, "task_id": task_id}
    marker_path = workdir / task_marker_name(task_id)
    if marker_path.is_file():
        existing_marker = read_json(marker_path)
        if existing_marker != marker:
            raise ProjectApiError(f"工作区已经绑定其他 Project 任务: {marker_path}")
    else:
        write_json(marker_path, marker)
    if state_path.is_file():
        existing_state = load_state(state_path)
        if int(existing_state.get("project_id") or 0) != project_id or int(existing_state.get("task_id") or 0) != task_id:
            raise ProjectApiError(f"生命周期状态已绑定其他 Project 任务: {state_path}")
        merge_state_agent_context(existing_state, agent)
        write_json(state_path, existing_state)
        return existing_state
    state = {
        "schema": SCHEMA,
        "project_id": project_id,
        "task_id": task_id,
        "task_name": task.get("name"),
        "stage": "intake",
        "created_at": now(),
        "updated_at": now(),
        "approval": None,
        "agent": agent or build_agent_context(model_missing_reason="host did not expose the active model"),
        "records": [],
        "history": [{"stage": "intake", "at": now()}],
    }
    write_json(state_path, state)
    return state


def load_record(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ProjectApiError("生命周期产物必须是 JSON 对象")
    return redact(payload)


def link_archive(state: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ProjectApiError("归档 manifest 必须是 JSON 对象")
    if int(manifest.get("projectId") or 0) != int(state["project_id"]) or int(manifest.get("taskId") or 0) != int(state["task_id"]):
        raise ProjectApiError("归档 manifest 的 Project/Task 与生命周期绑定不一致")
    archive_dir = manifest_path.parent
    for item in manifest.get("files", []):
        name = item.get("name")
        if not name or not (archive_dir / name).is_file():
            raise ProjectApiError(f"归档文件缺失，无法建立审计关联: {name}")
        actual = hashlib.sha256((archive_dir / name).read_bytes()).hexdigest()
        if actual != item.get("sha256"):
            raise ProjectApiError(f"归档文件摘要不匹配: {name}")
    payload = {
        "execution_id": manifest.get("executionId"),
        "source_tool": manifest.get("sourceTool"),
        "model": manifest.get("model"),
        "agent": manifest.get("agent") or build_agent_context(
            source_tool=manifest.get("sourceTool"),
            model=manifest.get("model"),
            model_source="manifest",
            model_missing_reason="archive manifest did not include a model",
            use_environment=False,
        ),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "complete": bool(manifest.get("complete")),
        "missing": manifest.get("missing", []),
        "archive_files": [item.get("name") for item in manifest.get("files", [])],
        "published_at": now(),
    }
    if not payload["execution_id"]:
        raise ProjectApiError("归档 manifest 缺少 executionId")
    return payload


def add_record(state: dict[str, Any], kind: str, payload: dict[str, Any], source: Path) -> dict[str, Any]:
    if kind not in RECORD_KINDS:
        raise ProjectApiError(f"不支持的产物类型: {kind}")
    missing = [field for field in REQUIRED_FIELDS.get(kind, ()) if field not in payload]
    if missing:
        raise ProjectApiError(f"{kind} 产物缺少字段: {', '.join(missing)}")
    if kind == "verification" and not isinstance(payload.get("passed"), bool):
        raise ProjectApiError("verification.passed 必须是布尔值")
    if kind == "pull_request" and not isinstance(payload.get("commit_sha"), str):
        raise ProjectApiError("pull_request.commit_sha 必须是字符串")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    record = {
        "kind": kind,
        "recorded_at": now(),
        "source_name": source.name,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "data": payload,
    }
    previous = next((item for item in state["records"] if item["kind"] == kind), None)
    if previous and previous["sha256"] == record["sha256"]:
        return previous
    if previous:
        state["records"].remove(previous)
    state["records"].append(record)
    state["updated_at"] = now()
    return record


def record_for(state: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return next((item for item in state.get("records", []) if item.get("kind") == kind), None)


def advance(state: dict[str, Any], target: str) -> None:
    if target not in STAGES:
        raise ProjectApiError(f"未知生命周期阶段: {target}")
    current = state["stage"]
    if current == target:
        return
    current_index = STAGES.index(current)
    target_index = STAGES.index(target)
    if target_index < current_index:
        rollback_pairs = {
            ("verification", "implementation"),
            ("delivery", "implementation"),
            ("audit", "delivery"),
        }
        if (current, target) not in rollback_pairs:
            raise ProjectApiError(f"不允许从 {current} 回退到 {target}")
        state["stage"] = target
        state["updated_at"] = now()
        state.setdefault("history", []).append({"stage": target, "at": state["updated_at"], "rollback": True})
        return
    if target_index != current_index + 1:
        raise ProjectApiError(f"阶段只能逐步推进，当前 {current}，目标 {target}")

    required: dict[str, str] = {
        "solution": "analysis",
        "approval": "solution",
        "verification": "implementation",
        "delivery": "verification",
        "audit": "pull_request",
        "completed": "execution_archive",
    }
    record_kind = required.get(target)
    if record_kind and not record_for(state, record_kind):
        raise ProjectApiError(f"进入 {target} 前必须记录 {record_kind} 产物")
    if target == "implementation" and not state.get("approval"):
        raise ProjectApiError("进入 implementation 前必须记录人工方案确认")
    if target == "verification":
        implementation = record_for(state, "implementation")
        documentation = record_for(state, "documentation")
        if not implementation:
            raise ProjectApiError("进入 verification 前必须记录 implementation 产物")
        if not documentation:
            raise ProjectApiError("进入 verification 前必须记录 documentation 产物")
    if target == "delivery":
        verification = record_for(state, "verification")
        if not verification or verification["data"].get("passed") is not True:
            raise ProjectApiError("验证未明确记录 passed=true，不能进入 PR 交付阶段")
    if target == "completed":
        pr = record_for(state, "pull_request")
        if not pr or not pr["data"].get("url") or not pr["data"].get("commit_sha"):
            raise ProjectApiError("完成审计前必须记录 PR URL 和 commit SHA")

    state["stage"] = target
    state["updated_at"] = now()
    state.setdefault("history", []).append({"stage": target, "at": state["updated_at"]})


def render_record_comment(state: dict[str, Any], record: dict[str, Any]) -> str:
    marker = f"[lifecycle:{state['task_id']}:{record['kind']}:{record['sha256'][:16]}]"
    data = record["data"]
    summary = record_summary(record["kind"], data)
    return (
        f"{marker} 研发流程记录：{record['kind']}\n\n"
        f"阶段：{state['stage']}\n"
        f"记录时间：{record['recorded_at']}\n\n"
        f"{summary}\n\n"
        "<details>\n<summary>查看结构化原始记录</summary>\n\n"
        "```json\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
        + "\n```\n\n</details>"
    )


def record_summary(kind: str, data: dict[str, Any]) -> str:
    """Render a compact, scannable task update without hiding its raw record."""
    if kind == "analysis":
        return f"**需求理解**：{data.get('understanding', '')}\n\n**范围**：{len(data.get('in_scope', []))} 项；**风险**：{len(data.get('risks', []))} 项。"
    if kind == "solution":
        return f"**推荐方案**：{data.get('recommendation', '')}\n\n**验收标准**：{len(data.get('acceptance_criteria', []))} 项；**测试计划**：{len(data.get('test_plan', []))} 项。"
    if kind == "documentation":
        return f"**文档收口**：{data.get('status', '')}\n\n**检查路径**：{len(data.get('paths', []))} 个；**跨项目影响**：{data.get('cross_project_impact', '')}"
    if kind == "verification":
        return f"**验证结果**：{'通过' if data.get('passed') is True else '未通过'}\n\n**环境**：{data.get('environment', '')}"
    if kind == "pull_request":
        return f"**交付**：[{data.get('branch', '')}]({data.get('url', '')})\n\n**Commit**：`{data.get('commit_sha', '')}`"
    if kind == "execution_archive":
        model_name = primary_model(data.get("agent")) or data.get("model") or "unknown"
        return (
            f"**执行归档**：`{data.get('execution_id', '')}`，完整：`{str(data.get('complete', False)).lower()}`\n\n"
            f"**执行工具**：`{data.get('source_tool') or 'unknown'}`；**主模型**：`{model_name}`"
        )
    return f"**记录类型**：`{kind}`"


def publish_record(state: dict[str, Any], record: dict[str, Any], config_path: str | Path | None = None) -> bool:
    api = load_config(config_path)
    dialog_id = ensure_task_dialog_id(api, int(state["task_id"]))
    messages = request_api(api, "GET", "/api/dialog/msg/list", {"dialog_id": dialog_id, "take": 100})
    text = json.dumps(messages, ensure_ascii=False)
    marker = f"[lifecycle:{state['task_id']}:{record['kind']}:{record['sha256'][:16]}]"
    if marker in text:
        return False
    agent = record["data"].get("agent") if record["kind"] == "execution_archive" else state.get("agent")
    model_name = primary_model(agent) or record["data"].get("model")
    params = {
        "dialog_id": dialog_id,
        "text": render_record_comment(state, record),
        "text_type": "md",
    }
    if model_name:
        params["model_name"] = model_name
    request_api(api, "POST", "/api/dialog/msg/sendtext", params)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project 研发任务生命周期与门禁")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="在 Project 创建任务并绑定本地工作区")
    create.add_argument("--project-id", type=int, required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--workdir", type=Path, required=True)
    create.add_argument("--state", type=Path, help="默认写入工作区 .project-lifecycle-<task-id>.json")
    create.add_argument("--column-id")
    create.add_argument("--content-file", type=Path)
    create.add_argument("--config", help="Project TOML 配置文件")
    add_agent_arguments(create, include_source_tool=True)

    bind = sub.add_parser("bind", help="绑定已有 Project 任务到本地工作区")
    bind.add_argument("--project-id", type=int, required=True)
    bind.add_argument("--task-id", type=int, required=True)
    bind.add_argument("--workdir", type=Path, required=True)
    bind.add_argument("--state", type=Path, help="默认写入工作区 .project-lifecycle-<task-id>.json")
    bind.add_argument("--config", help="Project TOML 配置文件")
    add_agent_arguments(bind, include_source_tool=True)

    record = sub.add_parser("record", help="记录分析、方案、验证、PR 或其他生命周期产物")
    record.add_argument("--state", type=Path, required=True)
    record.add_argument("--kind", choices=RECORD_KINDS, required=True)
    record.add_argument("--file", type=Path, required=True, help="包含 JSON 对象的 UTF-8 文件")
    record.add_argument("--publish", action="store_true", help="将该产物发布到 Project 任务讨论")
    record.add_argument("--config", help="Project TOML 配置文件")
    add_agent_arguments(record, include_source_tool=True)

    archive = sub.add_parser("archive-link", help="校验并关联已生成的执行归档 manifest")
    archive.add_argument("--state", type=Path, required=True)
    archive.add_argument("--manifest", type=Path, required=True)
    archive.add_argument("--publish", action="store_true", help="将审计关联发布到 Project 任务讨论")
    archive.add_argument("--config", help="Project TOML 配置文件")
    add_agent_arguments(archive, include_source_tool=True)

    approve = sub.add_parser("approve", help="记录外部负责人对方案的明确确认")
    approve.add_argument("--state", type=Path, required=True)
    approve.add_argument("--by", required=True, help="确认人名称或 Project 用户 ID")
    approve.add_argument("--reference", required=True, help="确认评论、决策或会议记录的可追溯引用")

    stage = sub.add_parser("advance", help="通过门禁推进一个生命周期阶段")
    stage.add_argument("--state", type=Path, required=True)
    stage.add_argument("--to", choices=STAGES, required=True)

    show = sub.add_parser("show", help="查看当前生命周期状态")
    show.add_argument("--state", type=Path, required=True)

    export = sub.add_parser("export", help="输出给执行归档使用的生命周期快照")
    export.add_argument("--state", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command in ("create", "bind"):
            if args.command == "create":
                api = load_config(args.config)
                params: dict[str, Any] = {"project_id": args.project_id, "name": args.name}
                if args.column_id:
                    params["column_id"] = args.column_id
                if args.content_file:
                    params["content"] = markdown_to_task_html(args.content_file.read_text(encoding="utf-8"))
                task = request_api(api, "POST", "/api/project/task/add", params)
                task_id = int(task["id"])
            else:
                task_id = args.task_id
            state_path = args.state or default_state_path(args.workdir, task_id)
            state = initialize(
                args.project_id,
                task_id,
                args.workdir,
                state_path,
                args.config,
                context_from_args(args, missing_reason="host did not expose the active model"),
            )
            result = {"projectId": args.project_id, "taskId": task_id, "stage": state["stage"], "state": str(state_path)}
        elif args.command == "record":
            state = load_state(args.state)
            merge_state_agent_context(state, context_from_args(args))
            payload = load_record(args.file)
            record = add_record(state, args.kind, payload, args.file)
            if args.publish:
                record["published"] = publish_record(state, record, args.config)
            write_json(args.state, state)
            result = {"kind": record["kind"], "sha256": record["sha256"], "published": bool(record.get("published"))}
        elif args.command == "archive-link":
            state = load_state(args.state)
            merge_state_agent_context(state, context_from_args(args))
            payload = link_archive(state, args.manifest)
            merge_state_agent_context(state, payload.get("agent"))
            record = add_record(state, "execution_archive", payload, args.manifest)
            if args.publish:
                record["published"] = publish_record(state, record, args.config)
            write_json(args.state, state)
            result = {"kind": record["kind"], "executionId": payload["execution_id"], "manifestSha256": payload["manifest_sha256"], "published": bool(record.get("published"))}
        elif args.command == "approve":
            state = load_state(args.state)
            if state["stage"] not in ("approval", "solution"):
                raise ProjectApiError("只有方案阶段可以记录批准")
            state["approval"] = {"by": args.by, "reference": args.reference, "approved_at": now()}
            state["updated_at"] = now()
            write_json(args.state, state)
            result = {"approved": True, "by": args.by, "reference": args.reference}
        elif args.command == "advance":
            state = load_state(args.state)
            advance(state, args.to)
            write_json(args.state, state)
            result = {"stage": state["stage"], "updatedAt": state["updated_at"]}
        elif args.command == "show":
            result = load_state(args.state)
        elif args.command == "export":
            state = load_state(args.state)
            write_json(args.output, state)
            result = {"output": str(args.output), "stage": state["stage"], "records": len(state["records"])}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ProjectApiError, OSError, KeyError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
