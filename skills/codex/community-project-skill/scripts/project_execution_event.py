#!/usr/bin/env python3
"""Append one normalized event to a Project execution state file."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from project_agent_context import add_agent_arguments, context_from_args, event_agent_context, merge_state_agent_context
from project_api import ProjectApiError
from project_execution_archive import attach_lifecycle, finalize_state, load_state, now, publish, write_json
from project_execution_capture import new_state, normalize_event, prepare_new_state
from project_task_binding import TaskBindingError


def append_event(args: argparse.Namespace) -> dict[str, object]:
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
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ProjectApiError("事件必须是 JSON 对象")
    merge_state_agent_context(
        state,
        event_agent_context(payload),
        locked=bool(state.get("finalized_at")),
    )
    _, record, event_id = normalize_event(payload)
    event_ids = set(state.get("event_ids", []))
    appended = not event_id or event_id not in event_ids
    if appended:
        state.setdefault("records", []).append(record)
        if event_id:
            state.setdefault("event_ids", []).append(event_id)
    if args.finalize:
        state["complete"] = args.complete
        state["missing"] = [] if args.complete else (args.missing or ["client did not expose complete native context"])
        attach_lifecycle(state, args.lifecycle_file)
        state = finalize_state(state, args.output_dir)
    else:
        state["status"] = "running"
        state["updated_at"] = now()
    write_json(args.state, state)
    if args.publish:
        if not args.finalize:
            raise ProjectApiError("--publish 必须与 --finalize 一起使用")
        publish(args.state, state, args.config)
    return {"executionId": state["execution_id"], "appended": appended, "finalized": args.finalize, "published": args.publish}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="追加一个 Project 会话事件")
    command.add_argument("--project-id", type=int)
    command.add_argument("--task-id", type=int)
    command.add_argument("--binding-root", type=Path)
    add_agent_arguments(command, include_source_tool=True, source_tool_required=True)
    command.add_argument("--execution-id")
    command.add_argument("--state", type=Path, help="默认写入绑定目录 .project-execution-<task-id>.json")
    command.add_argument("--output-dir", type=Path, help="默认写入绑定目录 .project-execution-<task-id>/")
    command.add_argument("--lifecycle-file", type=Path, help="研发生命周期 JSON 快照")
    command.add_argument("--finalize", action="store_true")
    command.add_argument("--complete", action="store_true")
    command.add_argument("--missing", action="append", default=[])
    command.add_argument("--publish", action="store_true")
    command.add_argument("--config", help="Project TOML 配置文件")
    return command


if __name__ == "__main__":
    try:
        print(json.dumps(append_event(parser().parse_args()), ensure_ascii=False, indent=2))
    except (OSError, ProjectApiError, TaskBindingError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
