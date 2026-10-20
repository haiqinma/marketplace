#!/usr/bin/env python3
"""Deliver personal main to origin/main and ensure an upstream/main PR."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from github_auth import Credentials, credentials_for
from github_config import ConfigError, Settings, load


GENERIC_TITLES = {"change", "changes", "misc", "pull request", "sync", "update", "updates"}
TOKEN_ENV_KEYS = ("GH_TOKEN", "GITHUB_TOKEN", "UPSTREAM_TOKEN")
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


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=env)


def subprocess_env(gh_token: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for name in TOKEN_ENV_KEYS:
        env.pop(name, None)
    if gh_token:
        env["GH_TOKEN"] = gh_token
    return env


def parse_github_repo(remote_url: str) -> tuple[str, str]:
    patterns = (
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
        r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, remote_url)
        if match:
            return match.group("owner"), match.group("repo")
    raise SystemExit(f"Unsupported GitHub remote URL: {remote_url}")


def github_repo_metadata(
    repo: str,
    auth_token: str = "",
    *,
    allow_not_found: bool = False,
) -> dict[str, Any] | None:
    owner, name = repo.split("/", 1)
    encoded_owner = urllib.parse.quote(owner, safe="")
    encoded_name = urllib.parse.quote(name, safe="")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "yeying-github",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{encoded_owner}/{encoded_name}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and allow_not_found:
            return None
        if exc.code in {401, 403, 404}:
            raise SystemExit(
                f"Cannot read GitHub repository {repo} with the selected project "
                f"credential (HTTP {exc.code}). The pull_request_token or GitHub App "
                "user token must read both origin and upstream."
            ) from exc
        raise SystemExit(f"Cannot inspect GitHub repository {repo} (HTTP {exc.code}).") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise SystemExit(f"Cannot inspect GitHub repository {repo}: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"GitHub returned invalid repository metadata for {repo}.") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"GitHub returned invalid repository metadata for {repo}.")
    return payload


def metadata_visibility(repo: str, metadata: dict[str, Any] | None) -> str:
    if metadata is None:
        raise SystemExit(f"GitHub repository is not publicly visible: {repo}")
    visibility = metadata.get("visibility")
    if visibility is None and isinstance(metadata.get("private"), bool):
        visibility = "private" if metadata["private"] else "public"
    if visibility not in {"public", "private"}:
        raise SystemExit(
            f"GitHub repository {repo} has unsupported visibility {visibility!r}; "
            "yeying-github currently supports public and private fork workflows."
        )
    return str(visibility)


def validate_repository_pair(
    expected: str,
    origin_repo: str,
    upstream_repo: str,
    pull_request_token: str,
) -> str:
    origin_visibility = metadata_visibility(
        origin_repo, github_repo_metadata(origin_repo, pull_request_token)
    )
    upstream_visibility = metadata_visibility(
        upstream_repo, github_repo_metadata(upstream_repo, pull_request_token)
    )
    if origin_visibility != upstream_visibility:
        raise SystemExit(
            "origin and upstream have different GitHub visibility "
            f"({origin_repo}: {origin_visibility}, {upstream_repo}: {upstream_visibility}). "
            "The supported workflow requires repositories in the same GitHub fork network."
        )
    if expected != "auto" and expected != origin_visibility:
        raise SystemExit(
            f"Configured visibility is {expected}, but both GitHub repositories are "
            f"{origin_visibility}. Set visibility = \"{origin_visibility}\" or \"auto\"."
        )
    return origin_visibility


def resolve_repository_access(
    settings: Settings,
    origin_repo: str,
    upstream_repo: str,
) -> tuple[str, Credentials]:
    require_fork = settings.mode == "api"
    credentials = credentials_for(
        settings,
        require_fork=require_fork,
    )
    if settings.visibility in {"public", "private"}:
        return settings.visibility, credentials
    visibility = validate_repository_pair(
        "auto", origin_repo, upstream_repo, credentials.pull_request_token
    )
    return visibility, credentials


def validate_title(title: str) -> str:
    value = " ".join(title.split())
    if len(value) < 8:
        raise SystemExit("PR title is too short to describe the delivered change accurately.")
    if len(value) > 256:
        raise SystemExit("PR title must be 256 characters or fewer.")
    if value.lower() in GENERIC_TITLES:
        raise SystemExit(f"PR title is too generic: {value!r}")
    return value


def ensure_fork_main() -> tuple[Path, str, str]:
    root = Path(git_output("rev-parse", "--show-toplevel"))
    branch = git_output("branch", "--show-current")
    if branch != "main":
        raise SystemExit(f"YeYing delivery requires the personal main branch, found: {branch or 'detached HEAD'}")
    origin_url = git_output("remote", "get-url", "origin")
    upstream_url = git_output("remote", "get-url", "upstream")
    origin_repo = parse_github_repo(origin_url)
    upstream_repo = parse_github_repo(upstream_url)
    if origin_repo == upstream_repo:
        raise SystemExit("origin and upstream must be different repositories for the fork PR workflow.")
    return root, f"{origin_repo[0]}/{origin_repo[1]}", f"{upstream_repo[0]}/{upstream_repo[1]}"


def resolve_script(root: Path, configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else root / path


def commit_subjects() -> list[str]:
    for revision in ("upstream/main..HEAD", "origin/main..HEAD"):
        try:
            output = git_output("log", "--reverse", "--format=%s", revision)
        except subprocess.CalledProcessError:
            continue
        subjects = [line.strip() for line in output.splitlines() if line.strip()]
        if subjects:
            return subjects
    return []


def default_body(title: str) -> str:
    subjects = commit_subjects()
    lines = ["## Summary", f"- {title}"]
    if subjects:
        lines.extend(["", "## Commits"])
        lines.extend(f"- {subject}" for subject in subjects[:20])
        if len(subjects) > 20:
            lines.append(f"- ... and {len(subjects) - 20} more commits")
    return "\n".join(lines) + "\n"


def read_body(args: argparse.Namespace, title: str) -> str:
    if args.body_file:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    if args.body:
        return args.body.replace("\\n", "\n")
    return default_body(title)


def api_command(
    args: argparse.Namespace,
    settings: Settings,
    title: str,
    body: str,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).with_name("github_api_push.py")),
        "--config",
        str(settings.config_path.expanduser().resolve()),
        "--remote",
        "origin",
        "--branch",
        "main",
        "--pr",
        "--upstream-remote",
        "upstream",
        "--base-branch",
        "main",
        "--pr-title",
        title,
        "--pr-body",
        body,
    ]
    if args.dry_run:
        command.append("--dry-run")
    if args.allow_dirty:
        command.append("--allow-dirty")
    return command


def print_git_plan(sync_script: Path, pr_script: Path, skip_sync: bool, title: str) -> None:
    if not skip_sync:
        print(f"dry run: AUTO_PUSH=true bash {shlex.quote(str(sync_script))}")
    if pr_script.is_file():
        print(
            "dry run: INTERACTIVE=false AUTO_PUSH="
            + ("true" if skip_sync else "false")
            + f" PR_TITLE={shlex.quote(title)} bash {shlex.quote(str(pr_script))} main"
        )
    else:
        print("dry run: repository pr.sh is missing; would use gh pr list/create/edit fallback")


def find_open_pr(
    upstream_repo: str, origin_owner: str, env: dict[str, str]
) -> dict[str, object] | None:
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            upstream_repo,
            "--state",
            "open",
            "--base",
            "main",
            "--head",
            f"{origin_owner}:main",
            "--limit",
            "1",
            "--json",
            "number,url,title",
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    prs = json.loads(result.stdout)
    return prs[0] if prs else None


def sync_git_pr_title(
    upstream_repo: str, origin_owner: str, title: str, env: dict[str, str]
) -> None:
    pr = find_open_pr(upstream_repo, origin_owner, env)
    if not pr:
        raise SystemExit("PR command completed but no open origin/main -> upstream/main PR was found.")
    if pr.get("title") != title:
        run(
            ["gh", "pr", "edit", str(pr["number"]), "--repo", upstream_repo, "--title", title],
            env=env,
        )
        print(f"updated PR title: {pr['url']}")
    else:
        print(f"existing PR title is accurate: {pr['url']}")


def ensure_pr_with_gh(
    upstream_repo: str, origin_owner: str, title: str, body: str, env: dict[str, str]
) -> None:
    if shutil.which("gh") is None:
        raise SystemExit("scripts/pr.sh is missing and gh is unavailable for the PR fallback.")
    existing = find_open_pr(upstream_repo, origin_owner, env)
    if existing:
        sync_git_pr_title(upstream_repo, origin_owner, title, env)
        return
    run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            upstream_repo,
            "--base",
            "main",
            "--head",
            f"{origin_owner}:main",
            "--title",
            title,
            "--body",
            body,
        ],
        env=env,
    )
    sync_git_pr_title(upstream_repo, origin_owner, title, env)


def deliver_git(
    args: argparse.Namespace,
    settings: Settings,
    credentials: Credentials,
    root: Path,
    origin_repo: str,
    upstream_repo: str,
    title: str,
) -> None:
    if args.allow_dirty:
        raise SystemExit("--allow-dirty is available only in api mode; repository sync/pr scripts require a clean worktree.")
    sync_script = resolve_script(root, settings.sync_script)
    pr_script = resolve_script(root, settings.pr_script)
    if not args.skip_sync and not sync_script.is_file():
        raise SystemExit(f"Missing repository sync script: {sync_script}")
    if args.dry_run:
        if sync_script.is_file():
            run(["bash", "-n", str(sync_script)])
        if pr_script.is_file():
            run(["bash", "-n", str(pr_script)])
        print_git_plan(sync_script, pr_script, args.skip_sync, title)
        return

    if not args.skip_sync:
        sync_env = subprocess_env()
        sync_env["AUTO_PUSH"] = "true"
        run(["bash", str(sync_script)], env=sync_env)

    body = read_body(args, title)
    origin_owner = origin_repo.split("/", 1)[0]
    pr_env = subprocess_env(credentials.pull_request_token)
    if pr_script.is_file():
        pr_env.update(
            {
                "INTERACTIVE": "false",
                "AUTO_PUSH": "true" if args.skip_sync else "false",
                "AUTO_FILL_PR": "false",
                "PR_TITLE": title,
                "PR_BODY": body,
            }
        )
        run(["bash", str(pr_script), "main"], env=pr_env)
        sync_git_pr_title(upstream_repo, origin_owner, title, pr_env)
    else:
        if args.skip_sync:
            run(["git", "push", "origin", "main"], env=subprocess_env())
        ensure_pr_with_gh(upstream_repo, origin_owner, title, body, pr_env)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument(
        "--mode",
        choices=("api", "git"),
        help="Transport: GitHub API, or repository Git/gh scripts.",
    )
    parser.add_argument(
        "--visibility",
        choices=("auto", "public", "private"),
        help="Detect visibility with the selected credential, or use an explicit configured value.",
    )
    parser.add_argument("--title", required=True, help="Specific title for the complete upstream PR delta.")
    body_group = parser.add_mutually_exclusive_group()
    body_group.add_argument("--body")
    body_group.add_argument("--body-file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--skip-sync", action="store_true", help="Git mode only: skip sync.sh and let pr.sh push main.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    title = validate_title(args.title)
    root, origin_repo, upstream_repo = ensure_fork_main()
    try:
        settings = load(args.config, args.mode, args.visibility).resolve(
            origin_repo, upstream_repo
        )
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    if args.skip_sync and settings.mode != "git":
        raise SystemExit("--skip-sync is available only in git mode.")
    visibility, credentials = resolve_repository_access(
        settings, origin_repo, upstream_repo
    )
    print(f"mode: {settings.mode}")
    print(f"visibility: {visibility}")
    print(f"configuration: {settings.project}")
    print(f"authentication: {credentials.provider}")
    print(f"head: {origin_repo}:main")
    print(f"base: {upstream_repo}:main")
    print(f"title: {title}")
    sys.stdout.flush()

    if settings.mode == "api":
        body = read_body(args, title)
        run(
            api_command(args, settings, title, body),
            env=subprocess_env(),
        )
    else:
        deliver_git(
            args,
            settings,
            credentials,
            root,
            origin_repo,
            upstream_repo,
            title,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
