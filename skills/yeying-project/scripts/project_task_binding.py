#!/usr/bin/env python3
"""Resolve a Project task binding without embedding credentials in the workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


class TaskBindingError(ValueError):
    pass


TASK_MARKER_PATTERN = re.compile(r"^task-(\d+)\.json$")
LEGACY_TASK_MARKER_PATTERN = re.compile(r"^\.project-task-(\d+)\.json$")
PROJECT_STATE_DIR = ".project"


def _positive_int(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise TaskBindingError(f"{name} 必须是正整数") from exc
    if result <= 0:
        raise TaskBindingError(f"{name} 必须是正整数")
    return result


def _read_marker(path: Path) -> tuple[int | None, int | None]:
    if path.name == ".project-task":
        data: Any = {"task_id": path.read_text(encoding="utf-8").strip()}
    else:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TaskBindingError(f"任务绑定文件无效: {path}") from exc
    if not isinstance(data, dict):
        raise TaskBindingError(f"任务绑定文件必须是 JSON 对象: {path}")
    project_id = _positive_int(data.get("project_id"), "project_id")
    task_id = _positive_int(data.get("task_id"), "task_id")
    match = TASK_MARKER_PATTERN.fullmatch(path.name) or LEGACY_TASK_MARKER_PATTERN.fullmatch(path.name)
    if match and task_id != int(match.group(1)):
        raise TaskBindingError(f"任务绑定文件名与 task_id 不一致: {path}")
    return project_id, task_id


def task_marker_name(task_id: int | str) -> str:
    resolved_task_id = _positive_int(task_id, "task_id")
    return f"task-{resolved_task_id}.json"


def project_state_dir(workdir: Path) -> Path:
    return workdir / PROJECT_STATE_DIR


def _default_artifact_path(workdir: Path, name: str, legacy_name: str) -> Path:
    current = project_state_dir(workdir) / name
    legacy = workdir / legacy_name
    return legacy if not current.exists() and legacy.exists() else current


def task_marker_path(workdir: Path, task_id: int | str) -> Path:
    name = task_marker_name(task_id)
    legacy_name = f".project-task-{_positive_int(task_id, 'task_id')}.json"
    return _default_artifact_path(workdir, name, legacy_name)


def lifecycle_state_path(workdir: Path, task_id: int | str) -> Path:
    resolved_task_id = _positive_int(task_id, "task_id")
    return _default_artifact_path(
        workdir,
        f"lifecycle-{resolved_task_id}.json",
        f".project-lifecycle-{resolved_task_id}.json",
    )


def execution_state_path(workdir: Path, task_id: int | str) -> Path:
    resolved_task_id = _positive_int(task_id, "task_id")
    return _default_artifact_path(
        workdir,
        f"execution-{resolved_task_id}.json",
        f".project-execution-{resolved_task_id}.json",
    )


def execution_output_dir(workdir: Path, task_id: int | str) -> Path:
    resolved_task_id = _positive_int(task_id, "task_id")
    return _default_artifact_path(
        workdir,
        f"execution-{resolved_task_id}",
        f".project-execution-{resolved_task_id}",
    )


def _marker_candidates(directory: Path) -> list[Path]:
    if directory.name == PROJECT_STATE_DIR:
        metadata_dir = directory
        legacy_dir = directory.parent
    else:
        metadata_dir = directory / PROJECT_STATE_DIR
        legacy_dir = directory
    task_markers = sorted(
        path for path in metadata_dir.glob("task-*.json")
        if TASK_MARKER_PATTERN.fullmatch(path.name) and path.is_file()
    )
    task_markers.extend(
        path for path in sorted(legacy_dir.glob(".project-task-*.json"))
        if LEGACY_TASK_MARKER_PATTERN.fullmatch(path.name) and path.is_file()
    )
    legacy_markers = [
        path for name in (".project-task.json", ".project-task")
        if (path := legacy_dir / name).is_file()
    ]
    if (path := metadata_dir / "task.json").is_file():
        legacy_markers.append(path)
    return task_markers + legacy_markers


def _find_marker(root: Path, preferred_task_id: int | None) -> tuple[Path | None, int | None, int | None]:
    for directory in (root, *root.parents):
        candidates = _marker_candidates(directory)
        if not candidates:
            continue
        parsed = [(path, *_read_marker(path)) for path in candidates]
        if preferred_task_id is not None:
            matches = [item for item in parsed if item[2] == preferred_task_id]
            if matches:
                if len({item[1] for item in matches}) > 1:
                    names = ", ".join(str(item[0]) for item in matches)
                    raise TaskBindingError(f"任务 {preferred_task_id} 的 Project 绑定不一致: {names}")
                return matches[0]
            continue
        by_task: dict[int | None, tuple[Path, int | None, int | None]] = {}
        for item in parsed:
            previous = by_task.get(item[2])
            if previous and previous[1] != item[1]:
                raise TaskBindingError(f"同一任务的 Project 绑定不一致: {previous[0]} 与 {item[0]}")
            by_task.setdefault(item[2], item)
        if len(by_task) > 1:
            names = ", ".join(path.name for path, _, _ in by_task.values())
            raise TaskBindingError(
                f"工作区存在多个 Project 任务绑定 ({names})；请显式传入 --task-id，"
                "或设置 YEYING_PROJECT_TASK_ID"
            )
        return next(iter(by_task.values()))
    return None, None, None


def resolve_binding(
    project_id: int | str | None = None,
    task_id: int | str | None = None,
    start_dir: Path | None = None,
) -> dict[str, Any]:
    """Resolve explicit values, environment, then the nearest workspace marker."""
    explicit_project = _positive_int(project_id, "project_id")
    explicit_task = _positive_int(task_id, "task_id")
    env_project = _positive_int(os.environ.get("YEYING_PROJECT_ID"), "YEYING_PROJECT_ID")
    env_task = _positive_int(os.environ.get("YEYING_PROJECT_TASK_ID"), "YEYING_PROJECT_TASK_ID")
    root = (start_dir or Path.cwd()).expanduser().resolve()
    if root.is_file():
        root = root.parent
    marker: Path | None = None
    marker_project = marker_task = None
    known_project = explicit_project or env_project
    known_task = explicit_task or env_task
    if known_project is None or known_task is None:
        marker, marker_project, marker_task = _find_marker(root, known_task)
        if known_project is not None and marker_project is not None and known_project != marker_project:
            raise TaskBindingError(f"任务绑定文件的 project_id 与显式配置不一致: {marker}")
        if known_task is not None and marker_task is not None and known_task != marker_task:
            raise TaskBindingError(f"任务绑定文件的 task_id 与显式配置不一致: {marker}")
    resolved_project = explicit_project or env_project or marker_project
    resolved_task = explicit_task or env_task or marker_task
    missing = [name for name, value in (("project_id", resolved_project), ("task_id", resolved_task)) if value is None]
    if missing:
        raise TaskBindingError(
            "无法确定 Project 任务绑定，缺少 " + ", ".join(missing)
            + "; 请传入参数、设置 YEYING_PROJECT_ID/YEYING_PROJECT_TASK_ID，"
            + "或在工作区 .project/ 中创建 task-<task-id>.json"
        )
    source = "arguments" if explicit_project or explicit_task else "environment" if env_project or env_task else str(marker)
    return {"project_id": resolved_project, "task_id": resolved_task, "source": source}


def main() -> int:
    parser = argparse.ArgumentParser(description="解析当前工作区的 Project 任务绑定")
    parser.add_argument("--project-id")
    parser.add_argument("--task-id")
    parser.add_argument("--start-dir", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(resolve_binding(args.project_id, args.task_id, args.start_dir), ensure_ascii=False, indent=2))
        return 0
    except (OSError, TaskBindingError) as exc:
        print(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
