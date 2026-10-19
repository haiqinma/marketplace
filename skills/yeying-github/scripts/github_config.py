"""Configuration loader for the YeYing GitHub delivery skill."""

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


DEFAULT_CONFIG_PATH = Path.home() / ".yeying" / "skills" / "github" / "config.toml"
VALID_MODES = {"api", "git"}
VALID_VISIBILITIES = {"auto", "public", "private"}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    mode: str
    visibility: str
    sync_script: str
    pr_script: str
    origin_token: str
    upstream_token: str
    config_path: Path


def _fallback_toml(raw: bytes) -> dict[str, object]:
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
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"invalid TOML value at line {line_number}") from exc
        if not isinstance(parsed, str):
            raise ValueError(f"unsupported TOML value at line {line_number}")
        result[section][key] = parsed
    return result


def _read_config(path: Path, required: bool) -> dict[str, object]:
    if not path.exists():
        if required:
            raise ConfigError(f"GitHub config file does not exist: {path}")
        return {}
    if not path.is_file():
        raise ConfigError(f"GitHub config path is not a file: {path}")
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
        raise ConfigError(f"Cannot read GitHub config file {path}: {exc}") from exc
    section = data.get("github", {}) if isinstance(data, dict) else {}
    if not isinstance(section, dict):
        raise ConfigError("[github] must be a TOML table")
    if (section.get("origin_token") or section.get("upstream_token")) and mode & 0o077:
        raise ConfigError(f"GitHub config containing tokens must be mode 0600 or stricter: {path}")
    return section


def load(
    explicit_path: str | Path | None = None,
    mode_override: str | None = None,
    visibility_override: str | None = None,
) -> Settings:
    explicit = Path(explicit_path).expanduser() if explicit_path else None
    env_path = os.environ.get("YEYING_GITHUB_CONFIG")
    path = explicit or (Path(env_path).expanduser() if env_path else DEFAULT_CONFIG_PATH)
    section = _read_config(path, required=explicit is not None or bool(env_path))

    mode = (
        (mode_override or "").strip()
        or os.environ.get("YEYING_GITHUB_MODE", "").strip()
        or str(section.get("mode", "api")).strip()
    ).lower()
    if mode not in VALID_MODES:
        raise ConfigError(f"GitHub mode must be one of {sorted(VALID_MODES)}, got: {mode!r}")

    visibility = (
        (visibility_override or "").strip()
        or os.environ.get("YEYING_GITHUB_VISIBILITY", "").strip()
        or str(section.get("visibility", "auto")).strip()
    ).lower()
    if visibility not in VALID_VISIBILITIES:
        raise ConfigError(
            "GitHub visibility must be one of "
            f"{sorted(VALID_VISIBILITIES)}, got: {visibility!r}"
        )

    sync_script = str(section.get("sync_script", "scripts/sync.sh")).strip()
    pr_script = str(section.get("pr_script", "scripts/pr.sh")).strip()
    origin_token = str(section.get("origin_token", "")).strip()
    upstream_token = str(section.get("upstream_token", "")).strip()
    if not sync_script or not pr_script:
        raise ConfigError("sync_script and pr_script must be non-empty paths")
    return Settings(
        mode=mode,
        visibility=visibility,
        sync_script=sync_script,
        pr_script=pr_script,
        origin_token=origin_token,
        upstream_token=upstream_token,
        config_path=path,
    )
