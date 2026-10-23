#!/usr/bin/env python3
"""Translate a Claude Code hook payload into one normalized JSON event."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from typing import Any

from project_agent_context import public_event_metadata


TYPE_MAP = {
    "SessionStart": "session_start",
    "UserPromptSubmit": "user_message",
    "PreToolUse": "tool_call",
    "PostToolUse": "tool_result",
    "Stop": "session_end",
    "SubagentStop": "session_end",
    "SessionEnd": "session_end",
    "Notification": "event",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    hook_name = str(first(payload, "hook_event_name", "event", "type") or "event")
    event_type = TYPE_MAP.get(hook_name, hook_name.lower())
    session_id = first(payload, "session_id", "sessionId")
    tool_name = first(payload, "tool_name", "toolName")
    if event_type == "user_message":
        content = first(payload, "prompt", "user_prompt", "message", "content")
        role = "user"
    elif event_type == "tool_call":
        content = first(payload, "tool_input", "input", "content", "payload")
        role = "tool"
    elif event_type == "tool_result":
        content = first(payload, "tool_response", "tool_result", "output", "content", "payload")
        role = "tool"
    elif event_type == "session_end":
        content = first(payload, "stop_reason", "reason", "summary", "message", "content")
        role = "event"
    else:
        content = first(payload, "message", "content", "payload")
        role = "event"
    if content is None:
        content = {key: value for key, value in payload.items() if key not in {"transcript_path"}}
    metadata: dict[str, Any] = {"hook_event": hook_name}
    if tool_name is not None:
        metadata["tool_name"] = tool_name
    if payload.get("cwd") is not None:
        metadata["cwd"] = payload["cwd"]
    metadata.update(public_event_metadata(payload))
    seed = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    event_id = str(first(payload, "event_id", "eventId") or "claude-" + hashlib.sha256(seed.encode()).hexdigest()[:24])
    event: dict[str, Any] = {
        "event_id": event_id,
        "type": event_type,
        "timestamp": str(first(payload, "timestamp", "created_at") or now()),
        "role": role,
        "content": content,
        "metadata": metadata,
    }
    if session_id is not None:
        event["session_id"] = session_id
    return event


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook 输入必须是 JSON 对象")
        print(json.dumps(normalize(payload), ensure_ascii=False))
        return 0
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
