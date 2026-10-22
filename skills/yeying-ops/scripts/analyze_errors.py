#!/usr/bin/env python3
"""Collect, sanitize, group, and analyze incremental service error logs."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator
from zoneinfo import ZoneInfo

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT = SCRIPT_DIR / "prompt.txt"
DEFAULT_SCHEMA = SCRIPT_DIR / "root-cause.schema.json"

TIMESTAMP_PATTERNS = (
    re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"),
    re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"),
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization\s*:\s*bearer|bearer|token|api[_-]?key|access[_-]?key|secret[_-]?key|cookie|password|passwd|client[_-]?secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\b(?:sk-[a-z0-9_-]{8,}|ak-[a-z0-9_-]{8,}|gh[pousr]_[a-z0-9_]{20,}|github_pat_[a-z0-9_]{20,})\b"),
    re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----"),
)
ID_PATTERNS = (
    re.compile(r"(?i)\b(?:request|trace|correlation|session)[\s_-]?id\s*[:=]\s*[\"']?[\w.-]+[\"']?"),
    re.compile(r"(?i)\b(?:user|token|channel|account|device)[\s_-]?id\s*[:=]\s*[\"']?[\w.-]+[\"']?"),
    re.compile(r"(?i)\bgroup\s*[:=]\s*[\"']?[0-9a-f]{16,}[\"']?"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", re.IGNORECASE),
    re.compile(r"\b0x[0-9a-f]+\b", re.IGNORECASE),
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
IPV4_PATTERN = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?![\w.])")
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@")
URL_SECRET_QUERY_PATTERN = re.compile(r"(?i)([?&](?:token|access_token|api_key|apikey|key|secret|password|signature|sig)=)[^&#\s]+")
UNIX_PATH_PATTERN = re.compile(r"(?<![\w])(?:/[A-Za-z0-9._-]+){2,}(?:\.[A-Za-z0-9_-]+)?")
WINDOWS_PATH_PATTERN = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]+")
NUMBER_PATTERN = re.compile(r"\b\d+\b")
SPACE_PATTERN = re.compile(r"\s+")
ERROR_PATTERN = re.compile(r"(?i)\b(?:error|fatal|panic|exception|traceback)\b")
DATE_PATTERN = re.compile(r"(?P<year>\d{4})[-/](?P<month>\d{2})[-/](?P<day>\d{2})")
ALLOWED_CATEGORIES = {"confirmed", "likely", "unknown"}
ALLOWED_SEVERITIES = {"P0", "P1", "P2", "P3"}
RESULT_FIELDS = {
    "summary", "severity", "root_cause", "confidence", "evidence", "impact",
    "recommended_actions", "missing_information", "dedup_fingerprint",
    "occurrences", "first_seen", "last_seen",
}


@dataclass(frozen=True)
class ErrorGroup:
    module: str
    fingerprint: str
    normalized: str
    samples: tuple[str, ...]
    occurrences: int
    first_seen: str
    last_seen: str


def default_config_path() -> Path:
    explicit = os.environ.get("YEYING_OPS_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    user_config = Path("~/.yeying/skills/ops/config.json").expanduser()
    return user_config if user_config.exists() else SCRIPT_DIR / "analyzer.conf"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--date", help="analysis date in YYYY-MM-DD; defaults to configured local date")
    parser.add_argument("--module", action="append", help="restrict analysis to one or more modules")
    parser.add_argument("--dry-run", action="store_true", help="collect groups without invoking Codex or advancing cursors")
    parser.add_argument("--no-lock", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def load_config(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"config file does not exist: {path}")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON config: {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise RuntimeError("config root must be an object")
    config["__config_dir"] = str(path.parent)
    config["__config_path"] = str(path)
    return config


def config_path(config: dict[str, Any], key: str, default: Path) -> Path:
    value = config.get(key)
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        path = Path(config.get("__config_dir", Path.cwd())) / path
    return path.resolve()


def get_timezone(config: dict[str, Any]) -> ZoneInfo:
    try:
        return ZoneInfo(str(config.get("timezone", "Asia/Shanghai")))
    except Exception as exc:
        raise RuntimeError(f"invalid timezone: {config.get('timezone')}") from exc


def local_date(config: dict[str, Any], date_arg: str | None) -> dt.date:
    if date_arg:
        try:
            return dt.date.fromisoformat(date_arg)
        except ValueError as exc:
            raise RuntimeError(f"invalid --date: {date_arg}") from exc
    return dt.datetime.now(get_timezone(config)).date()


def discover_deploy_dir(deploy_root: Path, module: str) -> Path | None:
    active = deploy_root / module
    if active.is_symlink() or active.is_dir():
        resolved = active.resolve()
        if resolved.is_dir():
            return resolved
    candidates = []
    for candidate in deploy_root.glob(f"{module}-*"):
        if candidate.is_dir():
            match = re.match(rf"^{re.escape(module)}-v?(\d+(?:\.\d+)*)-([0-9a-f]+)$", candidate.name)
            if match:
                version = tuple(int(part) for part in match.group(1).split("."))
                candidates.append((version, candidate.name, candidate))
    return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def iter_modules(config: dict[str, Any], requested: list[str] | None) -> list[str]:
    if requested:
        return list(dict.fromkeys(requested))
    modules_file = config_path(config, "modules_file", SCRIPT_DIR / "modules.conf")
    if not modules_file.exists():
        raise RuntimeError(f"modules file does not exist: {modules_file}")
    modules = []
    for line in modules_file.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            modules.append(value)
    if not modules:
        raise RuntimeError(f"modules file is empty: {modules_file}")
    return list(dict.fromkeys(modules))


def sanitize_for_model(text: str) -> str:
    result = URL_CREDENTIAL_PATTERN.sub(r"\1[USER]:[REDACTED]@", text)
    result = URL_SECRET_QUERY_PATTERN.sub(r"\1[REDACTED]", result)
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[SECRET_REDACTED]", result)
    for pattern in ID_PATTERNS:
        result = pattern.sub("[ID_REDACTED]", result)
    result = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", result)
    result = IPV4_PATTERN.sub("[IP_REDACTED]", result)
    for pattern in TIMESTAMP_PATTERNS:
        result = pattern.sub("[TIME]", result)
    result = WINDOWS_PATH_PATTERN.sub("[PATH]", result)
    return UNIX_PATH_PATTERN.sub("[PATH]", result)


def redact(text: str) -> str:
    return sanitize_for_model(text)


def normalize_error(text: str) -> str:
    result = NUMBER_PATTERN.sub("[N]", sanitize_for_model(text.strip()))
    return SPACE_PATTERN.sub(" ", result).strip().lower()


def extract_date(text: str) -> dt.date | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    try:
        return dt.date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
    except ValueError:
        return None


def extract_timestamp(text: str, fallback: dt.datetime) -> dt.datetime:
    match = re.search(r"(?P<date>\d{4}[-/]\d{2}[-/]\d{2})[ T-]+(?P<time>\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)", text)
    if not match:
        return fallback
    try:
        parsed = dt.datetime.fromisoformat(f"{match.group('date').replace('/', '-')} {match.group('time').replace(',', '.')}")
        return parsed.replace(tzinfo=fallback.tzinfo)
    except ValueError:
        return fallback


def group_error_lines(
    module: str,
    lines: Iterable[str],
    target_date: dt.date,
    timezone: ZoneInfo,
    samples_per_group: int,
    sample_chars: int,
    include_undated: bool = True,
) -> list[ErrorGroup]:
    groups: dict[str, dict[str, Any]] = {}
    fallback = dt.datetime.combine(target_date, dt.time.min, tzinfo=timezone)
    for raw_line in lines:
        if not ERROR_PATTERN.search(raw_line):
            continue
        line_date = extract_date(raw_line)
        if line_date is not None and line_date != target_date:
            continue
        if line_date is None and not include_undated:
            continue
        timestamp = extract_timestamp(raw_line, fallback)
        cleaned = sanitize_for_model(raw_line.strip())
        normalized = normalize_error(raw_line)
        if not cleaned or not normalized:
            continue
        item = groups.setdefault(normalized, {"samples": [], "occurrences": 0, "first_seen": timestamp.isoformat(), "last_seen": timestamp.isoformat()})
        item["occurrences"] += 1
        item["first_seen"] = min(item["first_seen"], timestamp.isoformat())
        item["last_seen"] = max(item["last_seen"], timestamp.isoformat())
        if len(item["samples"]) < samples_per_group:
            sample = cleaned if len(cleaned) <= sample_chars else cleaned[:sample_chars] + " ...[TRUNCATED]"
            if sample not in item["samples"]:
                item["samples"].append(sample)
    result = []
    for normalized, item in groups.items():
        fingerprint = hashlib.sha256(f"{module}\0{normalized}".encode("utf-8")).hexdigest()
        result.append(ErrorGroup(module, fingerprint, normalized, tuple(item["samples"]), item["occurrences"], item["first_seen"], item["last_seen"]))
    return sorted(result, key=lambda group: (-group.occurrences, group.fingerprint))


def read_log_chunk(error_log: Path, start_offset: int) -> tuple[list[str], int, os.stat_result]:
    stat = error_log.stat()
    if start_offset < 0 or start_offset > stat.st_size:
        start_offset = 0
    with error_log.open("rb") as stream:
        stream.seek(start_offset)
        data = stream.read()
    if not data:
        return [], start_offset, stat
    complete_length = len(data)
    if not data.endswith((b"\n", b"\r")):
        last_newline = max(data.rfind(b"\n"), data.rfind(b"\r"))
        complete_length = last_newline + 1 if last_newline >= 0 else 0
    complete = data[:complete_length]
    return complete.decode("utf-8", errors="replace").splitlines(), start_offset + complete_length, stat


def read_error_groups(module: str, error_log: Path, target_date: dt.date, timezone: ZoneInfo, samples_per_group: int, sample_chars: int) -> list[ErrorGroup]:
    if not error_log.exists():
        return []
    lines, _, _ = read_log_chunk(error_log, 0)
    return group_error_lines(module, lines, target_date, timezone, samples_per_group, sample_chars)


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def ensure_column(connection: sqlite3.Connection, table: str, name: str, declaration: str) -> None:
    if name not in table_columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS error_groups (
            fingerprint TEXT PRIMARY KEY, module TEXT NOT NULL, first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL, occurrences INTEGER NOT NULL, status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
            result_path TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
        )
    """)
    for name, declaration in (
        ("last_analyzed_date", "TEXT NOT NULL DEFAULT ''"),
        ("analyzed_occurrences", "INTEGER NOT NULL DEFAULT 0"),
        ("normalized", "TEXT NOT NULL DEFAULT ''"),
        ("samples_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("root_cause_category", "TEXT NOT NULL DEFAULT ''"),
        ("audit_task_id", "INTEGER"),
        ("remediation_task_ids", "TEXT NOT NULL DEFAULT '[]'"),
        ("audit_state", "TEXT NOT NULL DEFAULT ''"),
        ("last_observed_at", "TEXT NOT NULL DEFAULT ''"),
    ):
        ensure_column(connection, "error_groups", name, declaration)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS daily_observations (
            target_date TEXT NOT NULL, module TEXT NOT NULL, fingerprint TEXT NOT NULL,
            normalized TEXT NOT NULL, samples_json TEXT NOT NULL, occurrences INTEGER NOT NULL,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY (target_date, module, fingerprint)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS log_cursors (
            module TEXT NOT NULL, log_path TEXT NOT NULL, device INTEGER NOT NULL,
            inode INTEGER NOT NULL, offset INTEGER NOT NULL, size INTEGER NOT NULL,
            updated_at TEXT NOT NULL, PRIMARY KEY (module, log_path)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS project_links (
            finding_id TEXT PRIMARY KEY, module TEXT NOT NULL, audit_task_id INTEGER,
            remediation_task_ids TEXT NOT NULL DEFAULT '[]', audit_state TEXT NOT NULL DEFAULT '',
            decision_json TEXT NOT NULL DEFAULT '', decision_sha256 TEXT NOT NULL DEFAULT '',
            last_sync_digest TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
        )
    """)
    connection.commit()
    return connection


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def cursor_offset(connection: sqlite3.Connection, module: str, path: Path, stat: os.stat_result) -> int:
    row = connection.execute("SELECT device, inode, offset, size FROM log_cursors WHERE module = ? AND log_path = ?", (module, str(path))).fetchone()
    if row is None or int(row["device"]) != int(stat.st_dev) or int(row["inode"]) != int(stat.st_ino):
        return 0
    if stat.st_size < int(row["offset"]) or stat.st_size < int(row["size"]):
        return 0
    return int(row["offset"])


def save_cursor(connection: sqlite3.Connection, module: str, path: Path, stat: os.stat_result, offset: int) -> None:
    connection.execute("""
        INSERT INTO log_cursors (module, log_path, device, inode, offset, size, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(module, log_path) DO UPDATE SET device=excluded.device, inode=excluded.inode,
            offset=excluded.offset, size=excluded.size, updated_at=excluded.updated_at
    """, (module, str(path), int(stat.st_dev), int(stat.st_ino), offset, int(stat.st_size), utc_now()))


def merge_samples(existing: str, incoming: tuple[str, ...], limit: int) -> str:
    try:
        values = json.loads(existing)
    except (TypeError, json.JSONDecodeError):
        values = []
    merged = [value for value in values if isinstance(value, str)]
    for value in incoming:
        if value not in merged and len(merged) < limit:
            merged.append(value)
    return json.dumps(merged, ensure_ascii=False)


def store_observations(connection: sqlite3.Connection, target_date: dt.date, groups: list[ErrorGroup], samples_per_group: int, replace_module: str | None = None) -> None:
    date_value = target_date.isoformat()
    if replace_module is not None:
        connection.execute("DELETE FROM daily_observations WHERE target_date = ? AND module = ?", (date_value, replace_module))
    for group in groups:
        row = connection.execute("SELECT samples_json, occurrences, first_seen, last_seen FROM daily_observations WHERE target_date = ? AND module = ? AND fingerprint = ?", (date_value, group.module, group.fingerprint)).fetchone()
        if row is None:
            samples_json = json.dumps(list(group.samples), ensure_ascii=False)
            occurrences, first_seen, last_seen = group.occurrences, group.first_seen, group.last_seen
        else:
            samples_json = merge_samples(str(row["samples_json"]), group.samples, samples_per_group)
            occurrences = int(row["occurrences"]) + group.occurrences
            first_seen = min(str(row["first_seen"]), group.first_seen)
            last_seen = max(str(row["last_seen"]), group.last_seen)
        connection.execute("""
            INSERT INTO daily_observations (target_date, module, fingerprint, normalized, samples_json, occurrences, first_seen, last_seen, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_date, module, fingerprint) DO UPDATE SET normalized=excluded.normalized,
                samples_json=excluded.samples_json, occurrences=excluded.occurrences,
                first_seen=excluded.first_seen, last_seen=excluded.last_seen, updated_at=excluded.updated_at
        """, (date_value, group.module, group.fingerprint, group.normalized, samples_json, occurrences, first_seen, last_seen, utc_now()))


def observation_groups(connection: sqlite3.Connection, target_date: dt.date, module: str) -> list[ErrorGroup]:
    rows = connection.execute("SELECT module, fingerprint, normalized, samples_json, occurrences, first_seen, last_seen FROM daily_observations WHERE target_date = ? AND module = ? ORDER BY occurrences DESC, fingerprint", (target_date.isoformat(), module)).fetchall()
    groups = []
    for row in rows:
        try:
            samples = tuple(value for value in json.loads(str(row["samples_json"])) if isinstance(value, str))
        except json.JSONDecodeError:
            samples = ()
        groups.append(ErrorGroup(str(row["module"]), str(row["fingerprint"]), str(row["normalized"]), samples, int(row["occurrences"]), str(row["first_seen"]), str(row["last_seen"])))
    return groups


def should_analyze(connection: sqlite3.Connection, group: ErrorGroup, retry_after: int, target_date: dt.date | None = None) -> bool:
    row = connection.execute("SELECT status, updated_at, last_analyzed_date, analyzed_occurrences FROM error_groups WHERE fingerprint = ?", (group.fingerprint,)).fetchone()
    if row is None:
        return True
    date_value = target_date.isoformat() if target_date else ""
    if row["status"] == "success" and str(row["last_analyzed_date"] or "") == date_value:
        return group.occurrences > int(row["analyzed_occurrences"] or 0)
    if row["status"] in {"failed", "skipped"}:
        try:
            updated = dt.datetime.fromisoformat(str(row["updated_at"]))
            return (dt.datetime.now(dt.timezone.utc) - updated).total_seconds() >= retry_after
        except ValueError:
            return True
    return True


def finding_state(connection: sqlite3.Connection, fingerprint: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT result_path, root_cause_category, last_analyzed_date FROM error_groups WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()


def upsert_group(connection: sqlite3.Connection, group: ErrorGroup, status: str, result_path: str = "", last_error: str = "", increment_attempt: bool = False, target_date: dt.date | None = None, category: str = "") -> None:
    analyzed_date = target_date.isoformat() if target_date and status == "success" else ""
    analyzed_occurrences = group.occurrences if status == "success" else 0
    connection.execute("""
        INSERT INTO error_groups
            (fingerprint, module, first_seen, last_seen, occurrences, status, attempts,
             last_error, result_path, updated_at, last_analyzed_date, analyzed_occurrences,
             normalized, samples_json, root_cause_category, last_observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
            module=excluded.module, first_seen=min(error_groups.first_seen, excluded.first_seen),
            last_seen=max(error_groups.last_seen, excluded.last_seen), occurrences=excluded.occurrences,
            status=excluded.status, attempts=error_groups.attempts + excluded.attempts,
            last_error=excluded.last_error,
            result_path=CASE WHEN excluded.result_path = '' THEN error_groups.result_path ELSE excluded.result_path END,
            updated_at=excluded.updated_at,
            last_analyzed_date=CASE WHEN excluded.last_analyzed_date = '' THEN error_groups.last_analyzed_date ELSE excluded.last_analyzed_date END,
            analyzed_occurrences=CASE WHEN excluded.last_analyzed_date = '' THEN error_groups.analyzed_occurrences ELSE excluded.analyzed_occurrences END,
            normalized=excluded.normalized, samples_json=excluded.samples_json,
            root_cause_category=CASE WHEN excluded.root_cause_category = '' THEN error_groups.root_cause_category ELSE excluded.root_cause_category END,
            last_observed_at=excluded.last_observed_at
    """, (group.fingerprint, group.module, group.first_seen, group.last_seen, group.occurrences, status, 1 if increment_attempt else 0, last_error, result_path, utc_now(), analyzed_date, analyzed_occurrences, group.normalized, json.dumps(list(group.samples), ensure_ascii=False), category, utc_now()))


def load_prompt(path: Path, group: ErrorGroup) -> str:
    template = path.read_text(encoding="utf-8").rstrip()
    case = {"module": group.module, "dedup_fingerprint": group.fingerprint, "occurrences": group.occurrences, "first_seen": group.first_seen, "last_seen": group.last_seen, "normalized_error": group.normalized, "samples": list(group.samples)}
    return template + "\n\nINPUT_CASE_JSON:\n" + json.dumps(case, ensure_ascii=False, indent=2) + "\n"


def require_string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return value


def validate_result(value: Any, group: ErrorGroup) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Codex result must be a JSON object")
    missing = sorted(RESULT_FIELDS - set(value))
    if missing:
        raise ValueError(f"Codex result missing fields: {', '.join(missing)}")
    extra = sorted(set(value) - RESULT_FIELDS)
    if extra:
        raise ValueError(f"Codex result contains unsupported fields: {', '.join(extra)}")
    if not isinstance(value["summary"], str) or not value["summary"].strip() or len(value["summary"]) > 240:
        raise ValueError("summary must be a non-empty string of at most 240 characters")
    if value["severity"] not in ALLOWED_SEVERITIES:
        raise ValueError("severity must be P0, P1, P2, or P3")
    root_cause = value["root_cause"]
    if not isinstance(root_cause, dict) or set(root_cause) != {"category", "explanation"}:
        raise ValueError("root_cause must contain only category and explanation")
    if root_cause["category"] not in ALLOWED_CATEGORIES or not isinstance(root_cause["explanation"], str):
        raise ValueError("root_cause category or explanation is invalid")
    try:
        confidence = float(value["confidence"])
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    for name in ("evidence", "impact", "recommended_actions", "missing_information"):
        require_string_list(value[name], name)
    result = dict(value)
    result.update({"confidence": confidence, "dedup_fingerprint": group.fingerprint, "occurrences": group.occurrences, "first_seen": group.first_seen, "last_seen": group.last_seen})
    return result


def parse_codex_result(result_file: Path, stdout: str) -> Any:
    candidates = []
    if result_file.exists():
        candidates.append(result_file.read_text(encoding="utf-8", errors="replace").strip())
    candidates.append(stdout.strip())
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            for line in reversed(candidate.splitlines()):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and set(RESULT_FIELDS).issubset(event):
                    return event
    raise ValueError("Codex output is not a valid root-cause JSON object")


def command_version(command: str) -> str:
    try:
        completed = subprocess.run([command, "--version"], text=True, capture_output=True, timeout=10, check=False)
        return (completed.stdout or completed.stderr).strip()[:200]
    except (OSError, subprocess.TimeoutExpired):
        return ""


def run_codex(config: dict[str, Any], prompt: str, work_dir: Path, result_file: Path, schema_file: Path) -> tuple[Any, str, float, dict[str, Any]]:
    codex = str(config.get("codex_command", "codex"))
    timeout = int(config.get("timeout_seconds", 300))
    command = [codex, "exec", "--json", "--ephemeral", "--ignore-rules", "--skip-git-repo-check", "--sandbox", str(config.get("sandbox", "read-only")), "--output-schema", str(schema_file), "--output-last-message", str(result_file)]
    if bool(config.get("ignore_user_config", True)):
        command.append("--ignore-user-config")
    if config.get("model"):
        command.extend(["--model", str(config["model"])])
    command.append("-")
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=work_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr) from exc
    elapsed = time.monotonic() - started
    if process.returncode != 0:
        raise RuntimeError(f"codex exited {process.returncode}: {(stderr or stdout).strip()[-2000:]}")
    metadata = {
        "provider": str(config.get("model_provider", "openai")),
        "model": str(config.get("model", "")),
        "model_missing_reason": "" if config.get("model") else "batch configuration did not specify a model",
        "client_version": command_version(codex),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(schema_file.read_bytes()).hexdigest(),
    }
    return parse_codex_result(result_file, stdout), stderr[-2000:], elapsed, metadata


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    os.replace(temporary, path)


def write_result(results_dir: Path, target_date: dt.date, group: ErrorGroup, result: dict[str, Any]) -> Path:
    target = results_dir / target_date.isoformat() / group.module / f"{group.fingerprint}.json"
    atomic_write(target, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return target


def write_summary(results_dir: Path, target_date: dt.date, summary: list[dict[str, Any]]) -> None:
    target_dir = results_dir / target_date.isoformat()
    atomic_write(target_dir / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = [f"# ERROR 根因分析 {target_date.isoformat()}", ""]
    for item in summary:
        fingerprint = str(item.get("fingerprint", ""))
        identity = f" / `{fingerprint[:12]}`" if fingerprint else ""
        lines.extend([
            f"## {item.get('module', 'unknown')}{identity}",
            f"- 状态：{item.get('status', 'unknown')}",
            f"- 次数：{item.get('occurrences', 0)}",
            *([f"- 严重程度：{item['severity']}"] if item.get("severity") else []),
            *([f"- 根因分类：{item['category']}"] if item.get("category") else []),
            f"- 摘要：{item.get('summary', item.get('reason', ''))}", "",
        ])
    atomic_write(target_dir / "summary.md", "\n".join(lines))


@contextlib.contextmanager
def exclusive_lock(path: Path, blocking: bool = False) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+")
    try:
        if fcntl is None:
            raise RuntimeError("file locking is unavailable on this platform")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise RuntimeError(f"another yeying-ops run holds lock: {path}") from exc
        yield
    finally:
        if fcntl is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def analyze(config: dict[str, Any], args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    timezone = get_timezone(config)
    target_date = local_date(config, args.date)
    modules = iter_modules(config, args.module)
    state_db = config_path(config, "state_db", Path("~/.yeying/skills/ops/runtime/state.db").expanduser())
    results_dir = config_path(config, "results_dir", Path("~/.yeying/skills/ops/runtime/results").expanduser())
    work_dir = config_path(config, "work_dir", Path("~/.yeying/skills/ops/runtime/work").expanduser())
    prompt_file = config_path(config, "prompt_file", DEFAULT_PROMPT)
    schema_file = config_path(config, "schema_file", DEFAULT_SCHEMA)
    deploy_root = config_path(config, "deploy_root", Path("deploy"))
    samples_per_group = max(1, int(config.get("samples_per_group", 3)))
    sample_chars = max(100, int(config.get("sample_chars", 4000)))
    daily_groups = max(0, int(config.get("daily_groups", 20)))
    total_chars = max(0, int(config.get("total_chars", 60000)))
    retry_after = max(0, int(config.get("retry_after_seconds", 3600)))
    error_log_name = str(config.get("error_log_name", "logs/error.log"))
    include_undated = bool(config.get("include_undated_lines", True))

    work_dir.mkdir(parents=True, exist_ok=True)
    connection = open_database(state_db)
    summary: list[dict[str, Any]] = []
    analyzed = 0
    input_chars = 0
    try:
        for module in modules:
            deploy_dir = discover_deploy_dir(deploy_root, module)
            if deploy_dir is None:
                summary.append({"module": module, "status": "missing_deploy_dir", "occurrences": 0, "reason": str(deploy_root)})
                continue
            error_log = deploy_dir / error_log_name
            if not error_log.exists():
                summary.append({"module": module, "status": "missing_log", "occurrences": 0, "reason": str(error_log)})
                continue
            stat = error_log.stat()
            historical = args.date is not None
            start_offset = 0 if historical else cursor_offset(connection, module, error_log, stat)
            lines, end_offset, final_stat = read_log_chunk(error_log, start_offset)
            new_groups = group_error_lines(module, lines, target_date, timezone, samples_per_group, sample_chars, include_undated)
            if args.dry_run:
                groups = new_groups
            else:
                store_observations(connection, target_date, new_groups, samples_per_group, replace_module=module if historical else None)
                if not historical:
                    save_cursor(connection, module, error_log, final_stat, end_offset)
                connection.commit()
                groups = observation_groups(connection, target_date, module)
            for group in groups:
                if not should_analyze(connection, group, retry_after, target_date):
                    state = finding_state(connection, group.fingerprint)
                    summary.append({
                        "module": module,
                        "fingerprint": group.fingerprint,
                        "finding_id": group.fingerprint,
                        "status": "already_analyzed",
                        "occurrences": group.occurrences,
                        "first_seen": group.first_seen,
                        "last_seen": group.last_seen,
                        "category": str(state["root_cause_category"] or "") if state else "",
                        "result_path": str(state["result_path"] or "") if state else "",
                    })
                    continue
                prompt = load_prompt(prompt_file, group)
                group_chars = len(prompt)
                if analyzed >= daily_groups or input_chars + group_chars > total_chars:
                    if not args.dry_run:
                        upsert_group(connection, group, "skipped", last_error="daily budget exceeded")
                        connection.commit()
                    summary.append({"module": module, "fingerprint": group.fingerprint, "status": "skipped", "reason": "daily budget exceeded", "occurrences": group.occurrences})
                    continue
                if args.dry_run:
                    summary.append({"module": module, "fingerprint": group.fingerprint, "status": "pending", "occurrences": group.occurrences})
                    analyzed += 1
                    input_chars += group_chars
                    continue
                result_file = work_dir / f"{group.fingerprint}.{os.getpid()}.result.json"
                try:
                    value, stderr, elapsed, model = run_codex(config, prompt, work_dir, result_file, schema_file)
                    result = validate_result(value, group)
                    result["execution"] = {"elapsed_seconds": round(elapsed, 3), "stderr": stderr, "model": model, "analyzer_schema": "yeying.ops.finding.v1"}
                    result_path = write_result(results_dir, target_date, group, result)
                    category = str(result["root_cause"]["category"])
                    upsert_group(connection, group, "success", result_path=str(result_path), target_date=target_date, category=category)
                    summary.append({"module": module, "fingerprint": group.fingerprint, "finding_id": group.fingerprint, "status": "success", "occurrences": group.occurrences, "summary": result["summary"], "severity": result["severity"], "category": category, "confidence": result["confidence"], "result_path": str(result_path)})
                except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
                    upsert_group(connection, group, "failed", last_error=str(exc), increment_attempt=True)
                    summary.append({"module": module, "fingerprint": group.fingerprint, "status": "failed", "occurrences": group.occurrences, "reason": str(exc)})
                finally:
                    result_file.unlink(missing_ok=True)
                connection.commit()
                analyzed += 1
                input_chars += group_chars
        write_summary(results_dir, target_date, summary)
    finally:
        connection.close()
    counts: dict[str, int] = {}
    for item in summary:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    output = {"date": target_date.isoformat(), "dry_run": args.dry_run, "total_groups": len(summary), "status_counts": counts}
    failed_statuses = {"failed", "missing_deploy_dir", "missing_log"}
    return (1 if any(item["status"] in failed_statuses for item in summary) else 0), output


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        state_db = config_path(config, "state_db", Path("~/.yeying/skills/ops/runtime/state.db").expanduser())
        lock_file = config_path(config, "lock_file", state_db.with_suffix(".lock"))
        manager = contextlib.nullcontext() if args.no_lock else exclusive_lock(lock_file)
        with manager:
            status, output = analyze(config, args)
        print(json.dumps(output, ensure_ascii=False))
        return status
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
