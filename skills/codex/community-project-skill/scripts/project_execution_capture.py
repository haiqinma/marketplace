#!/usr/bin/env python3
"""Convert client-neutral JSONL events into a Project execution archive."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from project_agent_context import (
    add_agent_arguments,
    context_from_args,
    event_agent_context,
    merge_state_agent_context,
    primary_model,
)
from project_api import ProjectApiError
from project_execution_archive import (
    SCHEMA,
    attach_lifecycle,
    default_execution_output_dir,
    default_execution_state_path,
    finalize_state,
    load_state,
    now,
    publish,
    redact,
    write_json,
)
from project_task_binding import TaskBindingError, resolve_binding


ROLE_BY_TYPE = {
    "user_message": "user",
    "assistant_message": "assistant",
    "tool_call": "tool",
    "tool_result": "tool",
}


def _binding_workdir(args: argparse.Namespace, binding: dict[str, Any]) -> Path:
    source = str(binding.get("source") or "")
    if source not in ("arguments", "environment"):
        return Path(source).expanduser().resolve().parent
    root = (args.binding_root or Path.cwd()).expanduser().resolve()
    return root.parent if root.is_file() else root


def prepare_new_state(args: argparse.Namespace) -> dict[str, Any]:
    binding = resolve_binding(args.project_id, args.task_id, args.binding_root)
    workdir = _binding_workdir(args, binding)
    args.state = args.state or default_execution_state_path(workdir, binding["task_id"])
    args.output_dir = args.output_dir or default_execution_output_dir(workdir, binding["task_id"])
    default_lifecycle = workdir / f".project-lifecycle-{binding['task_id']}.json"
    if args.lifecycle_file is None and default_lifecycle.is_file():
        args.lifecycle_file = default_lifecycle
    return binding


def new_state(args: argparse.Namespace, binding: dict[str, Any] | None = None) -> dict[str, Any]:
    binding = binding or prepare_new_state(args)
    agent = context_from_args(args, missing_reason="host did not expose the active model")
    return {
        "schema": SCHEMA,
        "project_id": binding["project_id"],
        "task_id": binding["task_id"],
        "binding_source": binding["source"],
        "execution_id": args.execution_id or str(uuid.uuid4()),
        "source_tool": agent.get("source_tool") or args.source_tool,
        "model": primary_model(agent),
        "agent": agent,
        "started_at": now(),
        "status": "running",
        "complete": False,
        "missing": ["execution completion"],
        "records": [],
        "attachments": [],
        "event_ids": [],
        "output_dir": str(args.output_dir),
        "lifecycle_file": str(args.lifecycle_file) if args.lifecycle_file else None,
    }


def normalize_event(event: dict[str, Any]) -> tuple[str, dict[str, Any], str | None]:
    event_type = str(event.get("type") or "event")
    role = str(event.get("role") or ROLE_BY_TYPE.get(event_type) or "event")
    content = event.get("content", event.get("payload", event))
    metadata = event.get("metadata")
    record: dict[str, Any] = {"role": role, "kind": event_type, "content": content}
    if isinstance(metadata, dict):
        record["metadata"] = metadata
    elif metadata is not None:
        record["metadata"] = {"client_metadata": metadata}
    for key in ("timestamp", "session_id"):
        if event.get(key) is not None:
            record.setdefault("metadata", {})[key] = event[key]
    return event_type, redact(record), str(event["event_id"]) if event.get("event_id") else None


def capture(args: argparse.Namespace) -> dict[str, Any]:
    if args.state is not None and args.state.exists():
        state = load_state(args.state)
        args.output_dir = args.output_dir or Path(state["output_dir"])
        merge_state_agent_context(
            state,
            context_from_args(args),
            locked=bool(state.get("finalized_at")),
        )
    else:
        binding = prepare_new_state(args)
        state = new_state(args, binding)
    event_ids = set(state.get("event_ids", []))
    source = args.input_file.open(encoding="utf-8") if args.input_file else sys.stdin
    try:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProjectApiError(f"第 {line_number} 行不是有效 JSON") from exc
            if not isinstance(event, dict):
                raise ProjectApiError(f"第 {line_number} 行必须是 JSON 对象")
            merge_state_agent_context(
                state,
                event_agent_context(event),
                locked=bool(state.get("finalized_at")),
            )
            _, record, event_id = normalize_event(event)
            if event_id and event_id in event_ids:
                continue
            state["records"].append(record)
            if event_id:
                event_ids.add(event_id)
                state.setdefault("event_ids", []).append(event_id)
            write_json(args.state, state)
    finally:
        if args.input_file:
            source.close()
    state["complete"] = args.complete
    state["missing"] = [] if args.complete else (args.missing or ["client did not expose complete native context"])
    attach_lifecycle(state, args.lifecycle_file)
    state = finalize_state(state, args.output_dir)
    write_json(args.state, state)
    if args.publish:
        publish(args.state, state, args.config)
    return {"executionId": state["execution_id"], "records": len(state["records"]), "published": bool(args.publish)}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="把客户端 JSONL 会话事件归档到 Project 任务")
    command.add_argument("--project-id", type=int)
    command.add_argument("--task-id", type=int)
    command.add_argument("--binding-root", type=Path, help="任务绑定文件搜索起点，默认当前目录")
    add_agent_arguments(command, include_source_tool=True, source_tool_required=True)
    command.add_argument("--execution-id", default=None)
    command.add_argument("--state", type=Path, help="默认写入绑定目录 .project-execution-<task-id>.json")
    command.add_argument("--output-dir", type=Path, help="默认写入绑定目录 .project-execution-<task-id>/")
    command.add_argument("--lifecycle-file", type=Path, help="研发生命周期 JSON 快照")
    command.add_argument("--input-file", type=Path)
    completion = command.add_mutually_exclusive_group()
    completion.add_argument("--complete", action="store_true")
    completion.add_argument("--incomplete", action="store_false", dest="complete")
    command.set_defaults(complete=False)
    command.add_argument("--missing", action="append", default=[])
    command.add_argument("--publish", action="store_true")
    command.add_argument("--config", help="Project TOML 配置文件")
    return command


if __name__ == "__main__":
    try:
        print(json.dumps(capture(parser().parse_args()), ensure_ascii=False, indent=2))
    except (OSError, ProjectApiError, TaskBindingError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
