#!/usr/bin/env python3
"""Authorize a GitHub App with Device Flow and store its user token securely."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from github_config import ConfigError, load, update_github_app_tokens


def post(url: str, values: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode("utf-8"),
        method="POST",
        headers={"Accept": "application/json", "User-Agent": "yeying-github"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GitHub App Device Flow failed with HTTP {exc.code}.") from exc
    except (TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"GitHub App Device Flow failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("GitHub App Device Flow returned an invalid response.")
    return payload


def login(client_id: str) -> dict[str, Any]:
    device = post(
        "https://github.com/login/device/code",
        {"client_id": client_id, "scope": "offline_access"},
    )
    device_code = str(device.get("device_code", ""))
    user_code = str(device.get("user_code", ""))
    verification_uri = str(device.get("verification_uri", ""))
    if not device_code or not user_code or not verification_uri:
        error = device.get("error", "invalid_device_response")
        raise SystemExit(f"Cannot start GitHub App Device Flow: {error}")
    interval = int(device.get("interval", 5))
    deadline = time.monotonic() + int(device.get("expires_in", 900))
    print(f"Open: {verification_uri}")
    print(f"Enter code: {user_code}")
    print("Waiting for GitHub authorization...")
    while time.monotonic() < deadline:
        time.sleep(interval)
        result = post(
            "https://github.com/login/oauth/access_token",
            {
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        error = result.get("error")
        if not error:
            return result
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise SystemExit(f"GitHub App Device Flow failed: {error}")
    raise SystemExit("GitHub App Device Flow expired before authorization completed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--visibility", required=True, choices=("public", "private"))
    args = parser.parse_args()
    try:
        settings = load(args.config)
        profile = settings.profile(args.visibility)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    if profile.provider != "github_app":
        raise SystemExit(
            f"Configure [github.{args.visibility}.github_app] before login."
        )
    client_id = profile.github_app.client_id
    if not client_id:
        raise SystemExit(
            f"GitHub config missing github.{args.visibility}.github_app.client_id."
        )
    result = login(client_id)
    token = str(result.get("access_token", "")).strip()
    if not token:
        raise SystemExit("GitHub App Device Flow returned no access_token.")
    try:
        expires_in = int(result.get("expires_in", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise SystemExit("GitHub App Device Flow returned invalid expires_in.") from exc
    expires_at = str(int(time.time()) + expires_in) if expires_in else ""
    update_github_app_tokens(
        settings.config_path,
        args.visibility,
        user_token=token,
        refresh_token=str(result.get("refresh_token", "")).strip(),
        expires_at=expires_at,
    )
    print(f"GitHub App login stored for the {args.visibility} profile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
