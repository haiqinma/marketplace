"""Resolve PAT or GitHub App user credentials for one visibility profile."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from github_config import AuthProfile, Settings, update_github_app_tokens


@dataclass(frozen=True)
class Credentials:
    provider: str
    origin_token: str
    upstream_token: str


def _oauth_post(values: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://github.com/login/oauth/access_token",
        data=urllib.parse.urlencode(values).encode("utf-8"),
        method="POST",
        headers={"Accept": "application/json", "User-Agent": "yeying-github"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GitHub App OAuth request failed with HTTP {exc.code}.") from exc
    except (TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"GitHub App OAuth request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("GitHub App OAuth returned an invalid response.")
    return payload


def _expires_soon(expires_at: str) -> bool:
    if not expires_at:
        return False
    try:
        return float(expires_at) <= time.time() + 300
    except ValueError as exc:
        raise SystemExit("GitHub App expires_at must be a Unix timestamp string.") from exc


def _app_user_token(settings: Settings, visibility: str, profile: AuthProfile) -> str:
    app = profile.github_app
    if not app.client_id:
        raise SystemExit(f"GitHub config missing github.{visibility}.github_app.client_id.")
    if app.user_token and not _expires_soon(app.expires_at):
        return app.user_token
    if not app.refresh_token:
        raise SystemExit(
            f"GitHub App login is required for the {visibility} profile. Run "
            f"github_app_login.py --visibility {visibility}."
        )
    payload = _oauth_post(
        {
            "client_id": app.client_id,
            "grant_type": "refresh_token",
            "refresh_token": app.refresh_token,
        }
    )
    if payload.get("error"):
        raise SystemExit(
            f"GitHub App token refresh failed: {payload['error']}. Run "
            f"github_app_login.py --visibility {visibility}."
        )
    token = str(payload.get("access_token", "")).strip()
    refresh_token = str(payload.get("refresh_token", "")).strip()
    if not token:
        raise SystemExit("GitHub App token refresh returned no access_token.")
    try:
        expires_in = int(payload.get("expires_in", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise SystemExit("GitHub App token refresh returned invalid expires_in.") from exc
    expires_at = str(int(time.time()) + expires_in) if expires_in else ""
    update_github_app_tokens(
        settings.config_path,
        visibility,
        user_token=token,
        refresh_token=refresh_token or app.refresh_token,
        expires_at=expires_at,
    )
    return token


def credentials_for(
    settings: Settings,
    visibility: str,
    *,
    require_origin: bool = True,
    require_upstream: bool = True,
) -> Credentials:
    profile = settings.profile(visibility)
    if profile.provider == "github_app":
        token = _app_user_token(settings, visibility, profile)
        return Credentials("github_app", token, token)
    missing = []
    if require_origin and not profile.origin_token:
        missing.append(f"github.{visibility}.origin_token")
    if require_upstream and not profile.upstream_token:
        missing.append(f"github.{visibility}.upstream_token")
    if missing:
        raise SystemExit(
            "GitHub config missing: "
            + ", ".join(missing)
            + f"; configure them in {settings.config_path}"
        )
    return Credentials("pat", profile.origin_token, profile.upstream_token)
