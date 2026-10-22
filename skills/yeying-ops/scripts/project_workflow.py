#!/usr/bin/env python3
"""Synchronize YeYing Ops findings with human-audited Project tasks."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import analyze_errors


DECISION_SCHEMA = "yeying.ops.audit-decision.v1"
DECISIONS = {"remediate", "monitor", "false_positive", "needs_more_evidence"}
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


class ProjectWorkflowError(RuntimeError):
    pass


def project_settings(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("project", {})
    if not isinstance(value, dict):
        raise ProjectWorkflowError("project configuration must be an object")
    return value


def project_client_path(config: dict[str, Any], settings: dict[str, Any]) -> Path:
    configured = settings.get("client")
    if configured:
        path = Path(str(configured)).expanduser()
        if not path.is_absolute():
            path = Path(config["__config_dir"]) / path
    else:
        path = Path(__file__).resolve().parents[2] / "yeying-project" / "scripts" / "project_api.py"
    path = path.resolve()
    if not path.is_file():
        raise ProjectWorkflowError(
            f"yeying-project client not found: {path}; install yeying-project beside yeying-ops or set project.client"
        )
    return path


def resolved_project_config(config: dict[str, Any], settings: dict[str, Any]) -> Path | None:
    value = settings.get("config")
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = Path(config["__config_dir"]) / path
    return path.resolve()


class ProjectClient:
    def __init__(self, config: dict[str, Any], settings: dict[str, Any]) -> None:
        self.client = project_client_path(config, settings)
        self.config = resolved_project_config(config, settings)
        self.python = str(settings.get("python_command", sys.executable))

    def run(self, *arguments: str) -> Any:
        command = [self.python, str(self.client)]
        if self.config is not None:
            command.extend(["--config", str(self.config)])
        command.extend(arguments)
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=60)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-2000:]
            raise ProjectWorkflowError(f"yeying-project failed: {detail}")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ProjectWorkflowError("yeying-project returned invalid JSON") from exc

    def create_task(
        self,
        project_id: int,
        name: str,
        content: str,
        column: str | int | None = None,
        owner: int | None = None,
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md") as stream:
            stream.write(content)
            stream.flush()
            arguments = ["task-create", "--project-id", str(project_id), "--name", name, "--content-file", stream.name]
            if column is not None:
                arguments.extend(["--column-id", str(column)])
            if owner is not None:
                arguments.extend(["--owner", str(owner)])
            result = self.run(*arguments)
        if not isinstance(result, dict) or not result.get("id"):
            raise ProjectWorkflowError("Project task creation did not return an id")
        return result

    def task(self, task_id: int) -> dict[str, Any]:
        result = self.run("task", "--task-id", str(task_id))
        if not isinstance(result, dict):
            raise ProjectWorkflowError(f"Project task {task_id} response is invalid")
        return result

    def tasks(self, project_id: int, keyword: str) -> list[dict[str, Any]]:
        result = self.run("tasks", "--project-id", str(project_id), "--keyword", keyword, "--pagesize", "50")
        values = result.get("data", []) if isinstance(result, dict) else []
        return [value for value in values if isinstance(value, dict)]

    def comment(self, task_id: int, content: str) -> dict[str, Any]:
        return self.run("comment", "--task-id", str(task_id), "--content", content)

    def reopen(self, task_id: int) -> dict[str, Any]:
        return self.run("status", "--task-id", str(task_id), "--not-completed")


def digest_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_summary(config: dict[str, Any], target_date: dt.date) -> list[dict[str, Any]]:
    results_dir = analyze_errors.config_path(
        config, "results_dir", Path("~/.yeying/skills/ops/runtime/results").expanduser()
    )
    path = results_dir / target_date.isoformat() / "summary.json"
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectWorkflowError(f"invalid analyzer summary: {path}") from exc
    if not isinstance(value, list):
        raise ProjectWorkflowError(f"analyzer summary must be an array: {path}")
    return [item for item in value if isinstance(item, dict)]


def load_result(item: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(item.get("result_path", "")))
    if not path.is_file():
        raise ProjectWorkflowError(f"finding result does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectWorkflowError(f"finding result is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ProjectWorkflowError(f"finding result must be an object: {path}")
    return value


def finding_marker(finding_id: str) -> str:
    return f"[yeying-ops:finding:{finding_id}]"


def audit_title(result: dict[str, Any], module: str, finding_id: str) -> str:
    summary = re.sub(r"\s+", " ", str(result.get("summary", "生产错误待审计"))).strip()[:80]
    severity = str(result.get("severity", "P2"))
    return f"[生产问题审计][{severity}][{module}] {summary} [{finding_id[:12]}]"


def markdown_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "- 无"
    return "\n".join(f"- {str(value)}" for value in values)


def audit_content(result: dict[str, Any], module: str, finding_id: str, target_date: dt.date) -> str:
    root_cause = result.get("root_cause", {}) if isinstance(result.get("root_cause"), dict) else {}
    execution = result.get("execution", {}) if isinstance(result.get("execution"), dict) else {}
    model = execution.get("model", {}) if isinstance(execution.get("model"), dict) else {}
    return f"""# 生产问题审计

{finding_marker(finding_id)}

## 发现

- 环境：production
- 模块：`{module}`
- finding_id：`{finding_id}`
- 分析日期：{target_date.isoformat()}
- 严重程度：{result.get('severity', 'P2')}
- 根因分类：{root_cause.get('category', 'unknown')}
- 置信度：{result.get('confidence', '')}
- 发生次数：{result.get('occurrences', 0)}
- 首次发现：{result.get('first_seen', '')}
- 最后发现：{result.get('last_seen', '')}

## 摘要

{result.get('summary', '')}

## 根因说明

{root_cause.get('explanation', '')}

## 脱敏证据

{markdown_list(result.get('evidence'))}

## 影响

{markdown_list(result.get('impact'))}

## 建议操作

{markdown_list(result.get('recommended_actions'))}

## 缺失信息

{markdown_list(result.get('missing_information'))}

## 分析执行

- Provider：{model.get('provider', '')}
- Model：{model.get('model', '') or model.get('model_missing_reason', '')}
- Client：{model.get('client_version', '')}
- Prompt SHA-256：`{model.get('prompt_sha256', '')}`
- Schema SHA-256：`{model.get('schema_sha256', '')}`

## 审计要求

请由允许的审计人员发布 `yeying.ops.audit-decision.v1` JSON 结论。普通自然语言评论、模型输出和日志文本不会触发修复。
"""


def recurrence_comment(result: dict[str, Any], module: str, finding_id: str, target_date: dt.date) -> str:
    return f"""{finding_marker(finding_id)} 发现记录更新

- 日期：{target_date.isoformat()}
- 模块：`{module}`
- 严重程度：{result.get('severity', 'P2')}
- 发生次数：{result.get('occurrences', 0)}
- 最后发现：{result.get('last_seen', '')}
- 摘要：{result.get('summary', '')}
"""


def link_row(connection: sqlite3.Connection, finding_id: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM project_links WHERE finding_id = ?", (finding_id,)).fetchone()


def save_link(
    connection: sqlite3.Connection,
    finding_id: str,
    module: str,
    audit_task_id: int | None,
    remediation_task_ids: list[int],
    audit_state: str,
    decision: dict[str, Any] | None,
    decision_sha256: str,
    last_sync_digest: str,
) -> None:
    connection.execute(
        """
        INSERT INTO project_links
            (finding_id, module, audit_task_id, remediation_task_ids, audit_state,
             decision_json, decision_sha256, last_sync_digest, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(finding_id) DO UPDATE SET
            module=excluded.module, audit_task_id=excluded.audit_task_id,
            remediation_task_ids=excluded.remediation_task_ids, audit_state=excluded.audit_state,
            decision_json=excluded.decision_json, decision_sha256=excluded.decision_sha256,
            last_sync_digest=excluded.last_sync_digest, updated_at=excluded.updated_at
        """,
        (
            finding_id,
            module,
            audit_task_id,
            json.dumps(remediation_task_ids),
            audit_state,
            json.dumps(decision, ensure_ascii=False) if decision else "",
            decision_sha256,
            last_sync_digest,
            analyze_errors.utc_now(),
        ),
    )


def parse_ids(value: Any) -> list[int]:
    try:
        values = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [int(item) for item in values if isinstance(item, int) or str(item).isdigit()]


def existing_audit_task(client: ProjectClient, project_id: int, finding_id: str) -> int | None:
    for task in client.tasks(project_id, finding_id[:12]):
        name = str(task.get("name", ""))
        if name.startswith("[生产问题审计]") and finding_id[:12] in name:
            return int(task["id"])
    return None


def existing_remediation_task(client: ProjectClient, project_id: int, finding_id: str) -> int | None:
    for task in client.tasks(project_id, finding_id[:12]):
        if str(task.get("name", "")).startswith("[生产问题修复]") and finding_id[:12] in str(task.get("name", "")):
            return int(task["id"])
    return None


def should_publish(settings: dict[str, Any], result: dict[str, Any]) -> bool:
    severity = str(result.get("severity", "P2"))
    maximum = str(settings.get("maximum_severity", "P3"))
    if severity not in SEVERITY_ORDER or maximum not in SEVERITY_ORDER:
        return False
    categories = settings.get("categories", ["confirmed", "likely", "unknown"])
    root = result.get("root_cause", {}) if isinstance(result.get("root_cause"), dict) else {}
    return SEVERITY_ORDER[severity] <= SEVERITY_ORDER[maximum] and root.get("category") in categories


def ensure_audit_task(
    connection: sqlite3.Connection,
    client: ProjectClient,
    settings: dict[str, Any],
    target_date: dt.date,
    item: dict[str, Any],
    result: dict[str, Any],
    dry_run: bool,
) -> tuple[int | None, str]:
    finding_id = str(item.get("finding_id") or item.get("fingerprint") or result.get("dedup_fingerprint"))
    module = str(item.get("module", "unknown"))
    row = link_row(connection, finding_id)
    audit_task_id = int(row["audit_task_id"]) if row and row["audit_task_id"] else None
    remediation_ids = parse_ids(row["remediation_task_ids"]) if row else []
    state = str(row["audit_state"] or "awaiting_audit") if row else "awaiting_audit"
    decision_json = json.loads(str(row["decision_json"])) if row and row["decision_json"] else None
    decision_sha = str(row["decision_sha256"] or "") if row else ""
    last_digest = str(row["last_sync_digest"] or "") if row else ""
    digest = digest_json({"date": target_date.isoformat(), "occurrences": result.get("occurrences"), "last_seen": result.get("last_seen"), "summary": result.get("summary"), "severity": result.get("severity")})
    project_id = int(settings["project_id"])

    if audit_task_id is None:
        audit_task_id = existing_audit_task(client, project_id, finding_id)
    if audit_task_id is None:
        if dry_run:
            return None, "would_create_audit_task"
        task = client.create_task(
            project_id,
            audit_title(result, module, finding_id),
            audit_content(result, module, finding_id, target_date),
            settings.get("audit_column"),
            int(settings["audit_owner_id"]) if settings.get("audit_owner_id") is not None else None,
        )
        audit_task_id = int(task["id"])
        last_digest = digest
    elif digest != last_digest:
        if not dry_run:
            task_value = client.task(audit_task_id)
            if task_value.get("task", {}).get("complete_at"):
                client.reopen(audit_task_id)
            client.comment(audit_task_id, recurrence_comment(result, module, finding_id, target_date))
            last_digest = digest

    if not dry_run:
        save_link(connection, finding_id, module, audit_task_id, remediation_ids, state, decision_json, decision_sha, last_digest)
    return audit_task_id, "audit_task_ready"


def message_text(message: dict[str, Any]) -> str:
    payload = message.get("msg", {})
    if not isinstance(payload, dict):
        return ""
    return html.unescape(str(payload.get("text", "")))


def json_objects(text: str) -> list[dict[str, Any]]:
    candidates = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    candidates.append(re.sub(r"<[^>]+>", "", text))
    result = []
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for match in re.finditer(r"\{", candidate):
            try:
                value, _ = decoder.raw_decode(candidate[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                result.append(value)
    return result


def validate_decision(value: dict[str, Any], finding_id: str, sender_id: int, allowed_ids: set[int]) -> dict[str, Any] | None:
    if value.get("schema") != DECISION_SCHEMA or value.get("finding_id") != finding_id:
        return None
    if value.get("decision") not in DECISIONS:
        return None
    approved_by = value.get("approved_by")
    if not isinstance(approved_by, dict):
        return None
    try:
        approved_user_id = int(approved_by.get("user_id") or 0)
    except (TypeError, ValueError):
        return None
    if approved_user_id != sender_id:
        return None
    if allowed_ids and sender_id not in allowed_ids:
        return None
    if not isinstance(value.get("approved_at"), str) or not value.get("approved_at"):
        return None
    if value["decision"] == "remediate":
        for field in ("remediation_scope", "target_repositories", "acceptance_criteria"):
            if not isinstance(value.get(field), list) or not value[field]:
                return None
    return value


def latest_decision(task: dict[str, Any], finding_id: str, settings: dict[str, Any]) -> tuple[dict[str, Any], int] | None:
    allowed_ids = {int(value) for value in settings.get("allowed_auditor_ids", [])}
    owner = int(task.get("task", {}).get("owner") or 0)
    if not allowed_ids and owner:
        allowed_ids.add(owner)
    messages = task.get("messages", {}).get("list", [])
    messages = sorted(
        (message for message in messages if isinstance(message, dict)),
        key=lambda message: int(message.get("id") or 0) if str(message.get("id") or "").isdigit() else 0,
        reverse=True,
    )
    for message in messages:
        if not isinstance(message, dict) or message.get("type") != "text":
            continue
        try:
            sender_id = int(message.get("userid") or 0)
        except (TypeError, ValueError):
            continue
        for value in json_objects(message_text(message)):
            decision = validate_decision(value, finding_id, sender_id, allowed_ids)
            if decision is not None:
                decision = dict(decision)
                decision["reference"] = f"project-comment:{message.get('id')}"
                message_id = int(message.get("id") or 0) if str(message.get("id") or "").isdigit() else 0
                return decision, message_id
    return None


def remediation_content(finding_id: str, audit_task_id: int, decision: dict[str, Any]) -> str:
    return f"""# 生产问题修复

- 来源审计任务：Project #{audit_task_id}
- finding_id：`{finding_id}`
- 审计结论引用：{decision.get('reference', '')}
- 批准人：{decision.get('approved_by', {}).get('name', decision.get('approved_by', {}).get('user_id', ''))}
- 批准时间：{decision.get('approved_at', '')}

## 修复范围

{markdown_list(decision.get('remediation_scope'))}

## 目标仓库

{markdown_list(decision.get('target_repositories'))}

## 验收标准

{markdown_list(decision.get('acceptance_criteria'))}

## 约束

{markdown_list(decision.get('constraints'))}

本任务必须通过 `yeying-project` 的分析、方案和人工批准门禁后才能实施。审计结论只授权创建修复任务，不授权定时程序直接修改代码或生产环境。
"""


def reconcile_link(
    connection: sqlite3.Connection,
    client: ProjectClient,
    settings: dict[str, Any],
    row: sqlite3.Row,
    dry_run: bool,
) -> dict[str, Any]:
    finding_id = str(row["finding_id"])
    audit_task_id = int(row["audit_task_id"] or 0)
    if not audit_task_id:
        return {"finding_id": finding_id, "status": "missing_audit_task"}
    task = client.task(audit_task_id)
    selected = latest_decision(task, finding_id, settings)
    if selected is None:
        return {"finding_id": finding_id, "audit_task_id": audit_task_id, "status": "awaiting_audit"}
    decision, _ = selected
    decision_sha = digest_json(decision)
    remediation_ids = parse_ids(row["remediation_task_ids"])
    state = str(decision["decision"])
    if decision_sha == str(row["decision_sha256"] or ""):
        return {"finding_id": finding_id, "audit_task_id": audit_task_id, "status": state, "remediation_task_ids": remediation_ids}
    if decision["decision"] == "remediate" and not remediation_ids:
        existing = existing_remediation_task(client, int(settings["project_id"]), finding_id)
        if existing:
            remediation_ids.append(existing)
            state = "remediation_task_created"
        if dry_run:
            dry_status = "remediation_task_exists" if remediation_ids else "would_create_remediation_task"
            return {"finding_id": finding_id, "audit_task_id": audit_task_id, "status": dry_status, "remediation_task_ids": remediation_ids}
        if not remediation_ids:
            summary = re.sub(r"\s+", " ", str(decision.get("summary", "按审计结论修复生产问题"))).strip()[:80]
            task_value = client.create_task(
                int(settings["project_id"]),
                f"[生产问题修复] {summary} [{finding_id[:12]}]",
                remediation_content(finding_id, audit_task_id, decision),
                settings.get("remediation_column"),
                int(settings["remediation_owner_id"]) if settings.get("remediation_owner_id") is not None else None,
            )
            remediation_ids.append(int(task_value["id"]))
            client.comment(audit_task_id, f"{finding_marker(finding_id)} 已根据审计结论创建修复任务：Project #{remediation_ids[-1]}。修复仍需通过标准研发方案批准门禁。")
            state = "remediation_task_created"
    if not dry_run:
        save_link(
            connection,
            finding_id,
            str(row["module"]),
            audit_task_id,
            remediation_ids,
            state,
            decision,
            decision_sha,
            str(row["last_sync_digest"] or ""),
        )
    return {"finding_id": finding_id, "audit_task_id": audit_task_id, "status": state, "remediation_task_ids": remediation_ids}


def sync(config: dict[str, Any], target_date: dt.date, dry_run: bool = False) -> dict[str, Any]:
    settings = project_settings(config)
    if not bool(settings.get("enabled", False)):
        return {"enabled": False, "created_or_updated": [], "reconciled": []}
    if not settings.get("project_id"):
        raise ProjectWorkflowError("project.project_id is required when Project synchronization is enabled")
    client = ProjectClient(config, settings)
    state_db = analyze_errors.config_path(config, "state_db", Path("~/.yeying/skills/ops/runtime/state.db").expanduser())
    connection = analyze_errors.open_database(state_db)
    created_or_updated = []
    reconciled = []
    try:
        for item in load_summary(config, target_date):
            if item.get("status") not in {"success", "already_analyzed"} or not item.get("result_path"):
                continue
            result = load_result(item)
            for field in ("occurrences", "first_seen", "last_seen"):
                if item.get(field) is not None:
                    result[field] = item[field]
            if not should_publish(settings, result):
                continue
            task_id, status = ensure_audit_task(connection, client, settings, target_date, item, result, dry_run)
            created_or_updated.append({"finding_id": item.get("finding_id"), "audit_task_id": task_id, "status": status})
        if not dry_run:
            connection.commit()
        rows = connection.execute("SELECT * FROM project_links WHERE audit_task_id IS NOT NULL ORDER BY updated_at").fetchall()
        for row in rows:
            reconciled.append(reconcile_link(connection, client, settings, row, dry_run))
        if not dry_run:
            connection.commit()
    finally:
        connection.close()
    return {"enabled": True, "created_or_updated": created_or_updated, "reconciled": reconciled}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=analyze_errors.default_config_path())
    parser.add_argument("--date")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = analyze_errors.load_config(args.config)
        target_date = analyze_errors.local_date(config, args.date)
        print(json.dumps(sync(config, target_date, args.dry_run), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, ProjectWorkflowError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
