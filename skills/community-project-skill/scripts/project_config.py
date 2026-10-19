"""Standard TOML configuration loader for the Project skill client."""

from __future__ import annotations

import ast
import os
import re
import stat
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


DEFAULT_CONFIG_PATH = Path.home() / ".yeying" / "skills" / "project" / "config.toml"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    base_url: str
    access_key: str
    secret_key: str
    config_path: Path
    source: str


def _fallback_toml(raw: bytes) -> dict:
    """Parse the small [project] subset without requiring an extra package."""
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
        try:
            parsed: object = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"invalid TOML value at line {line_number}") from exc
        if not isinstance(parsed, str):
            raise ValueError(f"unsupported TOML value at line {line_number}")
        result[section][key] = parsed
    return result


def _read_file(path: Path, required: bool) -> dict[str, object]:
    if not path.exists():
        if required:
            raise ConfigError(f"Project config file does not exist: {path}")
        return {}
    if not path.is_file():
        raise ConfigError(f"Project config path is not a file: {path}")
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
        raise ConfigError(f"Cannot read Project config file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Project config must be a TOML table: {path}")
    section = data.get("project", {})
    if not isinstance(section, dict):
        raise ConfigError("[project] must be a TOML table")
    if section.get("secret_key") and mode & 0o077:
        raise ConfigError(f"Project config containing secret_key must be mode 0600 or stricter: {path}")
    return section


def load(explicit_path: str | Path | None = None) -> Settings:
    explicit = Path(explicit_path).expanduser() if explicit_path else None
    env_path = os.environ.get("YEYING_PROJECT_CONFIG")
    path = explicit or (Path(env_path).expanduser() if env_path else DEFAULT_CONFIG_PATH)
    section = _read_file(path, required=explicit is not None or bool(env_path))
    env_url = os.environ.get("YEYING_PROJECT_URL", "").strip()
    env_access_key = os.environ.get("YEYING_PROJECT_AK", "").strip()
    env_secret_key = os.environ.get("YEYING_PROJECT_SK", "").strip()
    file_url = str(section.get("url", "")).strip()
    file_access_key = str(section.get("access_key", "")).strip()
    file_secret_key = str(section.get("secret_key", "")).strip()
    base_url = (env_url or file_url).rstrip("/")
    access_key = env_access_key or file_access_key
    secret_key = env_secret_key or file_secret_key
    missing = [name for name, value in (("url", base_url), ("access_key", access_key), ("secret_key", secret_key)) if not value]
    if missing:
        raise ConfigError(
            "Project config missing: " + ", ".join(missing)
            + "; use --config, YEYING_PROJECT_CONFIG, or ~/.yeying/skills/project/config.toml"
        )
    source = "env" if env_url or env_access_key or env_secret_key else "file"
    return Settings(base_url, access_key, secret_key, path, source)
