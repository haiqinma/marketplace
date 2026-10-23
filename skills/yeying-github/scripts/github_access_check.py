#!/usr/bin/env python3
"""Verify GitHub access required to publish a fork and create its pull request."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from github_auth import credentials_for
from github_config import ConfigError, load


API_VERSION = "2022-11-28"


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def parse_github_repo(remote_url: str) -> str:
    patterns = (
        r"^git@github\.com:(?P<repo>[^/]+/.+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<repo>[^/]+/.+?)(?:\.git)?$",
        r"^https://github\.com/(?P<repo>[^/]+/.+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, remote_url)
        if match:
            return match.group("repo")
    raise SystemExit(f"Unsupported GitHub remote URL: {remote_url}")


def github_json(repo: str, endpoint: str, token: str, credential: str) -> Any:
    encoded_repo = urllib.parse.quote(repo, safe="/")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{encoded_repo}{endpoint}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "yeying-github-access-check",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"{credential} cannot access {repo}{endpoint or ''} (HTTP {exc.code})."
        ) from exc
    except (TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot check GitHub access for {repo}: {exc}") from exc


def verify_fork_relationship(origin: str, upstream: str, metadata: Any) -> None:
    if not isinstance(metadata, dict) or metadata.get("fork") is not True:
        raise SystemExit(f"{origin} is not a GitHub fork.")
    parent = metadata.get("parent")
    parent_name = parent.get("full_name", "") if isinstance(parent, dict) else ""
    if parent_name.lower() != upstream.lower():
        raise SystemExit(
            f"{origin} belongs to a different fork network; expected parent {upstream}, "
            f"found {parent_name or '<none>'}."
        )


def check_access(
    *,
    config: str | None,
    remote: str,
    upstream_remote: str,
    head_branch: str,
    base_branch: str,
) -> None:
    origin = parse_github_repo(git_output("remote", "get-url", remote))
    upstream = parse_github_repo(git_output("remote", "get-url", upstream_remote))
    if origin.lower() == upstream.lower():
        raise SystemExit("origin and upstream must be different repositories.")

    try:
        settings = load(config).resolve(upstream)
        credentials = credentials_for(
            settings,
            require_fork=settings.mode == "api",
            require_pull_request=True,
        )
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"mode: {settings.mode}")
    print(f"configuration: {settings.project}")
    print(f"authentication: {credentials.provider}")
    print(f"origin: {origin}:{head_branch}")
    print(f"upstream: {upstream}:{base_branch}")

    if settings.mode == "api":
        fork_metadata = github_json(origin, "", credentials.fork_token, "fork_token")
        verify_fork_relationship(origin, upstream, fork_metadata)
        permissions = fork_metadata.get("permissions", {})
        if isinstance(permissions, dict) and permissions.get("push") is False:
            raise SystemExit(f"fork_token cannot write {origin}.")
        print("fork publish access: verified")

    origin_for_pr = github_json(
        origin, "", credentials.pull_request_token, "pull_request_token"
    )
    verify_fork_relationship(origin, upstream, origin_for_pr)
    github_json(upstream, "", credentials.pull_request_token, "pull_request_token")
    print("pull request repository access: verified")

    origin_owner = origin.split("/", 1)[0]
    comparison = urllib.parse.quote(
        f"{base_branch}...{origin_owner}:{head_branch}", safe=".:"
    )
    comparison_data = github_json(
        upstream,
        f"/compare/{comparison}",
        credentials.pull_request_token,
        "pull_request_token",
    )
    if not isinstance(comparison_data, dict):
        raise SystemExit("GitHub returned an invalid comparison response.")
    print(
        "private head comparison: verified "
        f"(ahead={comparison_data.get('ahead_by', '?')}, "
        f"behind={comparison_data.get('behind_by', '?')})"
    )
    print("access check: ready")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--upstream-remote", default="upstream")
    parser.add_argument("--head-branch", default="main")
    parser.add_argument("--base-branch", default="main")
    args = parser.parse_args()
    check_access(
        config=args.config,
        remote=args.remote,
        upstream_remote=args.upstream_remote,
        head_branch=args.head_branch,
        base_branch=args.base_branch,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
