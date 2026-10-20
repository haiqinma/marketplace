"""Configuration loader for the YeYing GitHub delivery skill."""

from __future__ import annotations

import ast
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

tomli = None

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
VALID_PROVIDERS = {"pat", "github_app"}
SECRET_KEYS = {
    "fork_token",
    "pull_request_token",
    "user_token",
    "refresh_token",
    "client_secret",
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubAppSettings:
    client_id: str
    user_token: str
    refresh_token: str
    expires_at: str


@dataclass(frozen=True)
class AuthProfile:
    provider: str
    fork_token: str
    pull_request_token: str
    github_app: GitHubAppSettings


@dataclass(frozen=True)
class Settings:
    mode: str
    visibility: str
    sync_script: str
    pr_script: str
    public: AuthProfile
    private: AuthProfile
    config_path: Path

    def profile(self, visibility: str) -> AuthProfile:
        if visibility == "public":
            return self.public
        if visibility == "private":
            return self.private
        raise ConfigError(f"Resolved visibility must be public or private, got: {visibility!r}")


def _assign_nested(result: dict[str, object], path: list[str]) -> dict[str, object]:
    current = result
    for name in path:
        value = current.setdefault(name, {})
        if not isinstance(value, dict):
            raise ValueError(f"TOML table conflicts with value: {'.'.join(path)}")
        current = value
    return current


def _fallback_toml(raw: bytes) -> dict[str, object]:
    section: dict[str, object] | None = None
    result: dict[str, object] = {}
    for line_number, raw_line in enumerate(raw.decode("utf-8").splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        header = re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]", line)
        if header:
            section = _assign_nested(result, header.group(1).split("."))
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
        section[key] = parsed
    return result


def _contains_secret(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for key, child in value.items():
        is_secret_key = key in SECRET_KEYS or key == "token" or key.endswith("_token")
        if is_secret_key and isinstance(child, str) and child.strip():
            return True
        if _contains_secret(child):
            return True
    return False


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
    if _contains_secret(section) and mode & 0o077:
        raise ConfigError(f"GitHub config containing tokens must be mode 0600 or stricter: {path}")
    return section


def _table(section: dict[str, object], name: str) -> dict[str, object]:
    value = section.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[github.{name}] must be a TOML table")
    return value


def _reject_unknown(
    table: dict[str, object], allowed: set[str], table_name: str
) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(
            f"Unsupported key(s) in [{table_name}]: {', '.join(unknown)}; "
            f"allowed keys: {', '.join(sorted(allowed))}"
        )


def _profile(
    section: dict[str, object],
    visibility: str,
) -> AuthProfile:
    profile = _table(section, visibility)
    _reject_unknown(
        profile,
        {"provider", "fork_token", "pull_request_token", "github_app"},
        f"github.{visibility}",
    )
    provider = str(profile.get("provider", "pat")).strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ConfigError(
            f"github.{visibility}.provider must be one of {sorted(VALID_PROVIDERS)}, "
            f"got: {provider!r}"
        )
    app = profile.get("github_app", {})
    if not isinstance(app, dict):
        raise ConfigError(f"[github.{visibility}.github_app] must be a TOML table")
    _reject_unknown(
        app,
        {"client_id", "client_secret", "user_token", "refresh_token", "expires_at"},
        f"github.{visibility}.github_app",
    )
    return AuthProfile(
        provider=provider,
        fork_token=str(profile.get("fork_token", "")).strip(),
        pull_request_token=str(profile.get("pull_request_token", "")).strip(),
        github_app=GitHubAppSettings(
            client_id=str(app.get("client_id", "")).strip(),
            user_token=str(app.get("user_token", "")).strip(),
            refresh_token=str(app.get("refresh_token", "")).strip(),
            expires_at=str(app.get("expires_at", "")).strip(),
        ),
    )


def load(
    explicit_path: str | Path | None = None,
    mode_override: str | None = None,
    visibility_override: str | None = None,
) -> Settings:
    explicit = Path(explicit_path).expanduser() if explicit_path else None
    env_path = os.environ.get("YEYING_GITHUB_CONFIG")
    path = explicit or (Path(env_path).expanduser() if env_path else DEFAULT_CONFIG_PATH)
    section = _read_config(path, required=explicit is not None or bool(env_path))
    _reject_unknown(
        section,
        {"mode", "visibility", "sync_script", "pr_script", "public", "private"},
        "github",
    )

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
    if not sync_script or not pr_script:
        raise ConfigError("sync_script and pr_script must be non-empty paths")

    return Settings(
        mode=mode,
        visibility=visibility,
        sync_script=sync_script,
        pr_script=pr_script,
        public=_profile(section, "public"),
        private=_profile(section, "private"),
        config_path=path,
    )


def update_github_app_tokens(
    path: Path,
    visibility: str,
    *,
    user_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    if visibility not in {"public", "private"}:
        raise ConfigError(f"Cannot update GitHub App tokens for visibility: {visibility!r}")
    table = f"github.{visibility}.github_app"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read GitHub config file {path}: {exc}") from exc
    header = re.search(rf"(?m)^\[{re.escape(table)}\]\s*$", raw)
    if not header:
        if not raw or raw.endswith("\n\n"):
            separator = ""
        elif raw.endswith("\n"):
            separator = "\n"
        else:
            separator = "\n\n"
        raw += f"{separator}[{table}]\n"
        header = re.search(rf"(?m)^\[{re.escape(table)}\]\s*$", raw)
        assert header is not None
    next_header = re.search(r"(?m)^\[[^]]+\]\s*$", raw[header.end() :])
    table_end = header.end() + (
        next_header.start() if next_header else len(raw) - header.end()
    )
    before, body, after = raw[: header.end()], raw[header.end() : table_end], raw[table_end:]
    values = {
        "user_token": user_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    }
    for key, value in values.items():
        rendered = f"{key} = {json.dumps(value)}"
        pattern = rf"(?m)^\s*{re.escape(key)}\s*=.*$"
        if re.search(pattern, body):
            body = re.sub(pattern, rendered, body)
        else:
            body = body.rstrip("\n") + "\n" + rendered + "\n"
    updated = before + body + after
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
