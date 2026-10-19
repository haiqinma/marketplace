"""Shared configuration loading for the Warehouse skill clients."""

from __future__ import annotations

import os
import stat
import ast
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # type: ignore
except ModuleNotFoundError:  # Python 3.10 and earlier
    tomllib = None
    try:
        import tomli  # type: ignore
    except ModuleNotFoundError:
        tomli = None


DEFAULT_CONFIG_PATH = Path.home() / ".yeying" / "skills" / "warehouse" / "config.toml"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    base_url: str
    token: str
    upload_directory: str
    config_path: Path
    source: str


def _fallback_toml(raw: bytes) -> dict:
    """Parse the small [warehouse] config subset without third-party packages."""
    section = None
    result: dict[str, dict[str, object]] = {}
    for line_number, raw_line in enumerate(raw.decode("utf-8").splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        header = re.fullmatch(r"\[([A-Za-z0-9_-]+)\]", line)
        if header:
            section = header.group(1)
            result.setdefault(section, {})
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+)\s*=\s*(.+)", line)
        if not match or section is None:
            raise ValueError(f"invalid TOML at line {line_number}")
        key, value = match.groups()
        if value in ("true", "false"):
            parsed: object = value == "true"
        elif re.fullmatch(r"[+-]?[0-9]+", value):
            parsed = int(value)
        else:
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f"invalid TOML value at line {line_number}") from exc
            if not isinstance(parsed, str):
                raise ValueError(f"unsupported TOML value at line {line_number}")
        result[section][key] = parsed
    return result


def _read_file(path: Path, required: bool) -> dict:
    if not path.exists():
        if required:
            raise ConfigError(f"Warehouse config file does not exist: {path}")
        return {}
    if not path.is_file():
        raise ConfigError(f"Warehouse config path is not a file: {path}")
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        raw = path.read_bytes()
        if tomllib is not None:
            data = tomllib.loads(raw.decode("utf-8"))
        elif tomli is not None:
            data = tomli.loads(raw.decode("utf-8"))
        else:
            data = _fallback_toml(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ConfigError(f"Cannot read Warehouse config file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Warehouse config must be a TOML table: {path}")
    section = data.get("warehouse", {})
    if not isinstance(section, dict):
        raise ConfigError("[warehouse] must be a TOML table")
    if section.get("tool_token") and mode & 0o077:
        raise ConfigError(f"Warehouse config containing tool_token must be mode 0600 or stricter: {path}")
    return section


def load(explicit_path: str | Path | None = None) -> Settings:
    explicit = Path(explicit_path).expanduser() if explicit_path else None
    env_path = os.environ.get("YEYING_WAREHOUSE_CONFIG")
    path = explicit or (Path(env_path).expanduser() if env_path else DEFAULT_CONFIG_PATH)
    section = _read_file(path, required=explicit is not None or bool(env_path))
    env_url = os.environ.get("YEYING_WAREHOUSE_URL", "").strip()
    env_token = os.environ.get("YEYING_WAREHOUSE_TOOL_TOKEN", "").strip()
    legacy_token = os.environ.get("YEYING_WAREHOUSE_TOKEN", "").strip()
    env_upload_directory = os.environ.get("YEYING_WAREHOUSE_UPLOAD_DIRECTORY", "").strip()
    file_url = str(section.get("url", "")).strip()
    file_token = str(section.get("tool_token", "")).strip()
    file_upload_directory = str(section.get("upload_directory", "")).strip()
    base_url = (env_url or file_url).rstrip("/")
    token = env_token or legacy_token or file_token
    upload_directory = env_upload_directory or file_upload_directory
    if not base_url:
        raise ConfigError("YEYING_WAREHOUSE_URL or [warehouse].url is required")
    if not token:
        raise ConfigError("YEYING_WAREHOUSE_TOOL_TOKEN or [warehouse].tool_token is required")
    if upload_directory:
        parts = upload_directory.split("/")
        if not upload_directory.startswith("/") or any(part in (".", "..") for part in parts):
            raise ConfigError(
                "[warehouse].upload_directory must be an absolute Warehouse path "
                "without '.' or '..' segments"
            )
    source = "env" if env_url or env_token or legacy_token else "file"
    if not env_url and not env_token and not legacy_token and not file_url and not file_token:
        source = "default"
    return Settings(base_url=base_url, token=token, upload_directory=upload_directory,
                    config_path=path, source=source)
