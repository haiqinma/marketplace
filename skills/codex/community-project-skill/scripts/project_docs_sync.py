#!/usr/bin/env python3
"""Publish configured local Markdown files to the Project file cabinet."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from project_api import ProjectApiError, load_config, request_api


SENSITIVE = re.compile(
    r"(?im)(AK|SK|APP_KEY|SECRET_KEY|PRIVATE_KEY|PASSWORD|TOKEN|COOKIE)\s*[=:]"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("files"), list):
        raise ProjectApiError("配置必须包含 files 数组")
    return data


def find_child(items: Any, name: str, parent: int) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if item.get("name") == name and int(item.get("pid", parent) or parent) == parent:
            return item
    return None


def resolve_target(config: dict[str, str], item: dict[str, Any], root: int) -> tuple[int, dict[str, Any] | None]:
    parent = root
    target = item.get("target", item["source"])
    parts = Path(target).parts
    for folder in parts[:-1]:
        listing = request_api(config, "GET", "/api/file/lists", {"pid": parent})
        found = find_child(listing, folder, parent)
        if not found:
            return parent, None
        parent = int(found["id"])
    listing = request_api(config, "GET", "/api/file/lists", {"pid": parent})
    return parent, find_child(listing, parts[-1], parent)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步本地文档到 Project 文件柜")
    parser.add_argument("mode", choices=("check", "plan", "apply"))
    parser.add_argument("--config", type=Path, required=True, help="同步清单 JSON")
    parser.add_argument("--state", type=Path, help="同步状态 JSON")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.config)
        root = int(manifest.get("project_root_id", 0))
        state_path = args.state or args.config.with_suffix(".state.json")
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        api = load_config() if args.mode in ("plan", "apply") else None
        results: list[dict[str, Any]] = []
        for spec in manifest["files"]:
            source = Path(spec["source"]).expanduser().resolve()
            if not source.is_file():
                raise ProjectApiError(f"源文件不存在: {source}")
            text = source.read_text(encoding="utf-8")
            if SENSITIVE.search(text):
                raise ProjectApiError(f"源文件疑似包含敏感信息，已拒绝: {source}")
            item_state = state.get(str(source), {})
            result = {"source": str(source), "action": "check", "sha256": digest(source)}
            if api is not None:
                parent, target = resolve_target(api, spec, root)
                target_id = int(spec.get("target_file_id") or item_state.get("target_file_id") or 0)
                if target:
                    target_id = int(target["id"])
                if target_id:
                    result.update(target_file_id=target_id, action="update")
                    previous = item_state.get("sha256")
                    if previous and previous != result["sha256"]:
                        current = request_api(api, "GET", "/api/file/content", {"id": target_id, "down": "no"})
                        current_text = json.dumps(current, ensure_ascii=False)
                        if item_state.get("target_digest") and item_state["target_digest"] not in current_text:
                            result["action"] = "conflict"
                            results.append(result)
                            continue
                else:
                    result.update(parent_id=parent, action="create")
                if args.mode == "apply" and result["action"] != "conflict":
                    if not target_id:
                        name = Path(spec.get("target", spec["source"])).name
                        created = request_api(api, "GET", "/api/file/add", {"name": name, "type": "document", "pid": parent})
                        target_id = int(created["id"])
                    payload = json.dumps({"type": "md", "content": text}, ensure_ascii=False)
                    request_api(api, "POST", "/api/file/content/save", {"id": target_id, "content": payload})
                    verified = request_api(api, "GET", "/api/file/content", {"id": target_id, "down": "no"})
                    result["verified"] = bool(verified)
                    result["target_file_id"] = target_id
                    state[str(source)] = {"target_file_id": target_id, "sha256": result["sha256"]}
            results.append(result)
        if args.mode == "apply":
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"mode": args.mode, "results": results}, ensure_ascii=False, indent=2))
        return 0 if not any(item["action"] == "conflict" for item in results) else 2
    except (ProjectApiError, OSError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
