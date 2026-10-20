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
AUTH_KEYS = {"fork_token", "pull_request_token", "github_app"}
SECRET_KEYS = {
    "fork_token",
    "pull_request_token",
    "user_token",
    "refresh_token",
}
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
REPOSITORY_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
AUTH_TABLE_RE = re.compile(r"^github(?:\.projects\.[A-Za-z0-9_-]+)?$")


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
class ProjectOverride:
    name: str
    origin: str
    upstream: str
    mode: str
    sync_script: str
    pr_script: str
    auth: AuthProfile | None
    auth_table: str


@dataclass(frozen=True)
class Settings:
    mode: str
    sync_script: str
    pr_script: str
    auth: AuthProfile
    config_path: Path
    project: str
    auth_table: str


@dataclass(frozen=True)
class Config:
    mode: str
    sync_script: str
    pr_script: str
    auth: AuthProfile
    projects: tuple[ProjectOverride, ...]
    config_path: Path
    mode_override: str

    def _settings(self, project: ProjectOverride | None) -> Settings:
        return Settings(
            mode=self.mode_override or (project.mode if project else "") or self.mode,
            sync_script=(project.sync_script if project else "") or self.sync_script,
            pr_script=(project.pr_script if project else "") or self.pr_script,
            auth=(project.auth if project and project.auth is not None else self.auth),
            config_path=self.config_path,
            project=project.name if project else "default",
            auth_table=(
                project.auth_table
                if project and project.auth is not None
                else "github"
            ),
        )

    def resolve(self, origin: str, upstream: str) -> Settings:
        normalized_origin = _repository(origin, "origin")
        normalized_upstream = _repository(upstream, "upstream")
        exact = [
            project
            for project in self.projects
            if project.origin.lower() == normalized_origin.lower()
            and project.upstream.lower() == normalized_upstream.lower()
        ]
        if len(exact) > 1:
            names = ", ".join(project.name for project in exact)
            raise ConfigError(
                f"Multiple project configurations match {origin} -> {upstream}: {names}"
            )
        if exact:
            return self._settings(exact[0])

        partial = [
            project
            for project in self.projects
            if project.origin.lower() == normalized_origin.lower()
            or project.upstream.lower() == normalized_upstream.lower()
        ]
        if partial:
            names = ", ".join(project.name for project in partial)
            raise ConfigError(
                f"Project configuration {names} partially matches {origin} -> {upstream}; "
                "both origin and upstream must match exactly"
            )
        return self._settings(None)

    def resolve_project(self, name: str) -> Settings:
        if name == "default":
            return self._settings(None)
        for project in self.projects:
            if project.name == name:
                return self._settings(project)
        available = ", ".join(["default", *(project.name for project in self.projects)])
        raise ConfigError(f"Unknown GitHub project configuration {name!r}; available: {available}")


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


def _reject_unknown(
    table: dict[str, object], allowed: set[str], table_name: str
) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(
            f"Unsupported key(s) in [{table_name}]: {', '.join(unknown)}; "
            f"allowed keys: {', '.join(sorted(allowed))}"
        )


def _validated_choice(
    value: object, allowed: set[str], field: str, *, empty: bool = False
) -> str:
    result = str(value or "").strip().lower()
    if empty and not result:
        return ""
    if result not in allowed:
        raise ConfigError(f"{field} must be one of {sorted(allowed)}, got: {result!r}")
    return result


def _repository(value: object, field: str) -> str:
    result = str(value or "").strip()
    if result.endswith(".git"):
        result = result[:-4]
    if not REPOSITORY_RE.fullmatch(result):
        raise ConfigError(f"{field} must use owner/repository form, got: {result!r}")
    return result


def _auth_profile(table: dict[str, object], table_name: str) -> AuthProfile:
    fork_token = str(table.get("fork_token", "")).strip()
    pull_request_token = str(table.get("pull_request_token", "")).strip()
    app_configured = "github_app" in table
    if app_configured and (fork_token or pull_request_token):
        raise ConfigError(
            f"[{table_name}] configures both PAT and GitHub App authentication; "
            "keep either fork_token/pull_request_token or github_app"
        )
    app = table.get("github_app", {})
    if not isinstance(app, dict):
        raise ConfigError(f"[{table_name}.github_app] must be a TOML table")
    _reject_unknown(
        app,
        {"client_id", "user_token", "refresh_token", "expires_at"},
        f"{table_name}.github_app",
    )
    return AuthProfile(
        provider="github_app" if app_configured else "pat",
        fork_token=fork_token,
        pull_request_token=pull_request_token,
        github_app=GitHubAppSettings(
            client_id=str(app.get("client_id", "")).strip(),
            user_token=str(app.get("user_token", "")).strip(),
            refresh_token=str(app.get("refresh_token", "")).strip(),
            expires_at=str(app.get("expires_at", "")).strip(),
        ),
    )


def _projects(section: dict[str, object]) -> tuple[ProjectOverride, ...]:
    raw_projects = section.get("projects", {})
    if not isinstance(raw_projects, dict):
        raise ConfigError("[github.projects] must be a TOML table")
    result: list[ProjectOverride] = []
    pairs: dict[tuple[str, str], str] = {}
    for name, raw_project in raw_projects.items():
        if not PROJECT_NAME_RE.fullmatch(name):
            raise ConfigError(
                f"GitHub project configuration name must match {PROJECT_NAME_RE.pattern}: {name!r}"
            )
        if not isinstance(raw_project, dict):
            raise ConfigError(f"[github.projects.{name}] must be a TOML table")
        table_name = f"github.projects.{name}"
        _reject_unknown(
            raw_project,
            {
                "origin",
                "upstream",
                "mode",
                "sync_script",
                "pr_script",
                *AUTH_KEYS,
            },
            table_name,
        )
        origin = _repository(raw_project.get("origin", ""), f"{table_name}.origin")
        upstream = _repository(raw_project.get("upstream", ""), f"{table_name}.upstream")
        pair = (origin.lower(), upstream.lower())
        if pair in pairs:
            raise ConfigError(
                f"[{table_name}] duplicates repository pair configured by "
                f"[github.projects.{pairs[pair]}]"
            )
        pairs[pair] = name
        mode = _validated_choice(
            raw_project.get("mode", ""), VALID_MODES, f"{table_name}.mode", empty=True
        )
        auth = (
            _auth_profile(raw_project, table_name)
            if AUTH_KEYS.intersection(raw_project)
            else None
        )
        result.append(
            ProjectOverride(
                name=name,
                origin=origin,
                upstream=upstream,
                mode=mode,
                sync_script=str(raw_project.get("sync_script", "")).strip(),
                pr_script=str(raw_project.get("pr_script", "")).strip(),
                auth=auth,
                auth_table=table_name,
            )
        )
    return tuple(result)


def load(
    explicit_path: str | Path | None = None,
    mode_override: str | None = None,
) -> Config:
    explicit = Path(explicit_path).expanduser() if explicit_path else None
    env_path = os.environ.get("YEYING_GITHUB_CONFIG")
    path = explicit or (Path(env_path).expanduser() if env_path else DEFAULT_CONFIG_PATH)
    section = _read_config(path, required=explicit is not None or bool(env_path))
    _reject_unknown(
        section,
        {
            "mode",
            "sync_script",
            "pr_script",
            "projects",
            *AUTH_KEYS,
        },
        "github",
    )

    mode = _validated_choice(section.get("mode", "api"), VALID_MODES, "github.mode")
    forced_mode = _validated_choice(
        (mode_override or "").strip() or os.environ.get("YEYING_GITHUB_MODE", "").strip(),
        VALID_MODES,
        "GitHub mode override",
        empty=True,
    )
    sync_script = str(section.get("sync_script", "scripts/sync.sh")).strip()
    pr_script = str(section.get("pr_script", "scripts/pr.sh")).strip()
    if not sync_script or not pr_script:
        raise ConfigError("sync_script and pr_script must be non-empty paths")

    return Config(
        mode=mode,
        sync_script=sync_script,
        pr_script=pr_script,
        auth=_auth_profile(section, "github"),
        projects=_projects(section),
        config_path=path,
        mode_override=forced_mode,
    )


def update_github_app_tokens(
    path: Path,
    auth_table: str,
    *,
    user_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    if not AUTH_TABLE_RE.fullmatch(auth_table):
        raise ConfigError(f"Cannot update GitHub App tokens for table: {auth_table!r}")
    table = f"{auth_table}.github_app"
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
