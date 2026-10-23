#!/usr/bin/env python3
"""Normalize Codex or other Agent JSONL events for the Project capture bridge."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from typing import Any

from project_agent_context import public_event_metadata


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def normalize(payload: dict[str, Any], line_number: int = 0) -> dict[str, Any]:
    raw_type = str(value(payload, "type", "event", "kind") or "event")
    type_aliases = {
        "message": "assistant_message",
        "user": "user_message",
        "assistant": "assistant_message",
        "tool_call": "tool_call",
        "tool_result": "tool_result",
        "error": "session_error",
        "done": "session_end",
    }
    event_type = type_aliases.get(raw_type, raw_type)
    role = value(payload, "role")
    if role is None:
        role = "user" if event_type == "user_message" else "tool" if event_type in {"tool_call", "tool_result"} else "assistant" if event_type == "assistant_message" else "event"
    content = value(payload, "content", "message", "text", "payload", "input", "output", "result")
    if content is None:
        content = payload
    event_id = value(payload, "event_id", "eventId", "id")
    if event_id is None:
        seed = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        # Content-derived IDs remain stable when a client retries or reorders a JSONL batch.
        event_id = "codex-" + hashlib.sha256(seed.encode()).hexdigest()[:24]
    event: dict[str, Any] = {
        "event_id": str(event_id),
        "type": event_type,
        "timestamp": str(value(payload, "timestamp", "created_at") or now()),
        "role": role,
        "content": content,
    }
    session_id = value(payload, "session_id", "sessionId")
    if session_id is not None:
        event["session_id"] = session_id
    metadata = value(payload, "metadata")
    normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    normalized_metadata.update(public_event_metadata(payload))
    if normalized_metadata:
        event["metadata"] = normalized_metadata
    return event


def main() -> int:
    try:
        for line_number, line in enumerate(sys.stdin, 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"第 {line_number} 行必须是 JSON 对象")
            print(json.dumps(normalize(payload, line_number), ensure_ascii=False))
        return 0
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
