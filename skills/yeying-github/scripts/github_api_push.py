#!/usr/bin/env python3
"""Publish local Git commits and optionally ensure a GitHub PR using the API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


API_VERSION = "2022-11-28"


@dataclass
class Repo:
    owner: str
    name: str


def run_git(args: list[str], binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if binary:
        return result.stdout
    return result.stdout.decode().strip()


def parse_repo(remote_url: str) -> Repo:
    patterns = [
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
        r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, remote_url)
        if match:
            return Repo(match.group("owner"), match.group("repo"))
    raise SystemExit(f"Unsupported GitHub remote URL: {remote_url}")


def token() -> str:
    value = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not value:
        raise SystemExit("Set GH_TOKEN or GITHUB_TOKEN with repo write access.")
    return value


def upstream_token() -> str:
    return os.environ.get("UPSTREAM_TOKEN") or token()


def gh(
    repo: Repo,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    auth_token: str | None = None,
) -> Any:
    url = f"https://api.github.com/repos/{repo.owner}/{repo.name}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {auth_token or token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "Content-Type": "application/json",
    }
    retryable_statuses = {429, 500, 502, 503, 504}
    for attempt in range(6):
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode()
            return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode()
            if error.code not in retryable_statuses or attempt == 5:
                raise SystemExit(f"{method} {path} failed with {error.code}: {detail}") from error
        except (TimeoutError, urllib.error.URLError) as error:
            if attempt == 5:
                raise SystemExit(f"{method} {path} failed after retries: {error}") from error
        time.sleep(1)
    raise AssertionError("unreachable")


def repo_full_name(repo: Repo) -> str:
    return f"{repo.owner}/{repo.name}"


def current_branch() -> str:
    branch = run_git(["branch", "--show-current"])
    if not isinstance(branch, str) or not branch:
        raise SystemExit("Not on a named branch. Pass --branch explicitly after checking state.")
    return branch


def ensure_clean_worktree(allow_dirty: bool) -> None:
    status = run_git(["status", "--short"])
    if status and not allow_dirty:
        raise SystemExit(
            "Worktree is dirty. Commit/stash changes first or pass --allow-dirty after inspection.\n"
            + str(status)
        )


def commit_meta(sha: str) -> dict[str, Any]:
    raw = run_git(["show", "-s", "--format=%B%x00%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI", sha])
    parts = str(raw).split("\0")
    if len(parts) != 7:
        raise SystemExit(f"Unexpected commit metadata for {sha}")
    message, author_name, author_email, author_date, committer_name, committer_email, committer_date = parts
    return {
        "message": message.rstrip(),
        "author": {"name": author_name, "email": author_email, "date": author_date},
        "committer": {"name": committer_name, "email": committer_email, "date": committer_date},
    }


def changed_paths(sha: str) -> list[dict[str, str]]:
    raw = run_git(["diff-tree", "--no-commit-id", "--name-status", "-r", sha])
    if not raw:
        return []
    changes = []
    for line in str(raw).splitlines():
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")):
            changes.append({"status": status[0], "old_path": parts[1], "path": parts[2]})
        else:
            changes.append({"status": status[0], "path": parts[1]})
    return changes


def file_mode_at(sha: str, path: str) -> str:
    raw = run_git(["ls-tree", sha, "--", path])
    if not raw:
        return "100644"
    return str(raw).split()[0]


def file_b64_at(sha: str, path: str) -> str:
    data = run_git(["show", f"{sha}:{path}"], binary=True)
    assert isinstance(data, bytes)
    return base64.b64encode(data).decode()


def is_ancestor(base: str, head: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", base, head]).returncode == 0


def refresh_remote_tracking(remote: str, branch: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "fetch",
            remote,
            f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        print(f"warning: remote was updated, but local tracking ref was not refreshed: {detail}")
        return False
    return True


def align_checked_out_branch(branch: str, old_head: str, new_head: str, expected_tree: str) -> bool:
    """Move the checked-out branch to the API-created commit after tree verification."""
    current = current_branch()
    if current != branch:
        print(f"warning: pushed {branch}, but checked-out branch is {current}; local branch was not aligned")
        return False

    actual_head = str(run_git(["rev-parse", "HEAD"]))
    if actual_head != old_head:
        print(
            "warning: HEAD moved during publish; local branch was not aligned "
            f"(expected {old_head}, found {actual_head})"
        )
        return False

    local_tree = str(run_git(["rev-parse", "HEAD^{tree}"]))
    if local_tree != expected_tree:
        print(
            "warning: local tree changed during publish; local branch was not aligned "
            f"(local {local_tree}, remote {expected_tree})"
        )
        return False

    run_git(["update-ref", f"refs/heads/{branch}", new_head, old_head])
    print(f"aligned local {branch} -> {new_head}")
    return True


def first_commit_subject(base: str, head: str) -> str:
    raw = run_git(["log", "--reverse", "--format=%s", f"{base}..{head}"])
    subjects = [line for line in str(raw).splitlines() if line.strip()]
    return subjects[0] if subjects else f"Update {head[:7]}"


def pr_body(source_repo: Repo, source_branch: str, base_repo: Repo, base_branch: str) -> str:
    return (
        "Created by Codex using the GitHub API push workflow.\n\n"
        f"- Head: `{repo_full_name(source_repo)}:{source_branch}`\n"
        f"- Base: `{repo_full_name(base_repo)}:{base_branch}`\n"
    )


def normalize_pr_body(body: str) -> str:
    """Accept shell-style escaped newlines for --pr-body and store real Markdown."""
    return body.replace("\\r\\n", "\n").replace("\\n", "\n")


def ensure_pull_request(
    *,
    source_repo: Repo,
    source_branch: str,
    base_repo: Repo,
    base_branch: str,
    title: str,
    body: str,
    dry_run: bool,
) -> None:
    pr_token = upstream_token()
    body = normalize_pr_body(body)
    head = f"{source_repo.owner}:{source_branch}"
    query = urllib.parse.urlencode(
        {
            "state": "open",
            "head": head,
            "base": base_branch,
        }
    )
    existing = gh(base_repo, "GET", f"/pulls?{query}", auth_token=pr_token)
    if existing:
        pr = existing[0]
        updates: dict[str, str] = {}
        if pr.get("title") != title:
            updates["title"] = title
        current_body = pr.get("body") or ""
        normalized_current_body = normalize_pr_body(current_body)
        if normalized_current_body != current_body:
            updates["body"] = normalized_current_body
        if updates:
            if dry_run:
                fields = ", ".join(sorted(updates))
                print(f"existing PR metadata differs; dry run: would update {fields}: {pr['html_url']}")
            else:
                gh(base_repo, "PATCH", f"/pulls/{pr['number']}", updates, auth_token=pr_token)
                print(f"updated existing PR metadata: {pr['html_url']}")
        print(f"existing PR: {pr['html_url']}")
        return

    print(f"no open PR found for {head} -> {repo_full_name(base_repo)}:{base_branch}")
    if dry_run:
        print(f"dry run: would create PR title={title!r}")
        return

    pr = gh(
        base_repo,
        "POST",
        "/pulls",
        {
            "title": title,
            "head": head,
            "base": base_branch,
            "body": body,
            "maintainer_can_modify": True,
        },
        auth_token=pr_token,
    )
    print(f"created PR: {pr['html_url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default=None)
    parser.add_argument("--pr", action="store_true", help="Ensure an open PR after pushing.")
    parser.add_argument("--upstream-remote", default="upstream")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--pr-title", default=None)
    parser.add_argument("--pr-body", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--no-update-tracking-ref", action="store_true")
    parser.add_argument("--no-align-local-ref", action="store_true")
    args = parser.parse_args()

    if args.pr and not (args.pr_title or "").strip():
        raise SystemExit("--pr-title is required with --pr so the complete delivery has an accurate title.")

    branch = args.branch or current_branch()
    ensure_clean_worktree(args.allow_dirty)

    remote_url = run_git(["remote", "get-url", args.remote])
    repo = parse_repo(str(remote_url))
    local_head = str(run_git(["rev-parse", "HEAD"]))
    tracking_ref = f"{args.remote}/{branch}"
    tracking_sha = str(run_git(["rev-parse", tracking_ref]))
    remote_ref = gh(repo, "GET", f"/git/ref/heads/{branch}")
    remote_sha = remote_ref["object"]["sha"]

    print(f"repo: {repo.owner}/{repo.name}")
    print(f"branch: {branch}")
    print(f"remote ref: {remote_sha}")
    print(f"tracking:   {tracking_sha}")
    print(f"local HEAD: {local_head}")

    if remote_sha != tracking_sha:
        raise SystemExit(
            f"Remote branch moved from local {tracking_ref}. Run git fetch or inspect before publishing."
        )
    if not is_ancestor(tracking_sha, local_head):
        local_tree = str(run_git(["rev-parse", "HEAD^{tree}"]))
        tracking_tree = str(run_git(["rev-parse", f"{tracking_ref}^{{tree}}"]))
        if local_tree != tracking_tree:
            raise SystemExit(f"{tracking_ref} is not an ancestor of HEAD; refusing non-fast-forward API push.")
        if args.no_align_local_ref:
            raise SystemExit(
                f"{tracking_ref} and HEAD have identical trees but different commits; "
                "rerun without --no-align-local-ref to align the checked-out branch."
            )
        if args.dry_run:
            print(f"{tracking_ref} and HEAD have identical trees; dry run: would align local {branch} -> {tracking_sha}")
        else:
            align_checked_out_branch(branch, local_head, tracking_sha, tracking_tree)
        local_head = tracking_sha

    commits_raw = run_git(["rev-list", "--reverse", f"{tracking_sha}..{local_head}"])
    commits = [line for line in str(commits_raw).splitlines() if line]
    if not commits:
        print("nothing to publish")
        if args.pr:
            upstream_url = run_git(["remote", "get-url", args.upstream_remote])
            upstream_repo = parse_repo(str(upstream_url))
            title = args.pr_title or first_commit_subject(
                str(run_git(["rev-parse", f"{args.upstream_remote}/{args.base_branch}"])),
                local_head,
            )
            body = args.pr_body or pr_body(repo, branch, upstream_repo, args.base_branch)
            ensure_pull_request(
                source_repo=repo,
                source_branch=branch,
                base_repo=upstream_repo,
                base_branch=args.base_branch,
                title=title,
                body=body,
                dry_run=args.dry_run,
            )
        return 0

    upstream_repo: Repo | None = None
    pr_title: str | None = None
    pr_description: str | None = None
    if args.pr:
        upstream_url = run_git(["remote", "get-url", args.upstream_remote])
        upstream_repo = parse_repo(str(upstream_url))
        try:
            upstream_base_sha = str(run_git(["rev-parse", f"{args.upstream_remote}/{args.base_branch}"]))
        except subprocess.CalledProcessError:
            subprocess.run(
                [
                    "git",
                    "fetch",
                    args.upstream_remote,
                    f"+refs/heads/{args.base_branch}:refs/remotes/{args.upstream_remote}/{args.base_branch}",
                ],
                check=True,
            )
            upstream_base_sha = str(run_git(["rev-parse", f"{args.upstream_remote}/{args.base_branch}"]))
        pr_title = args.pr_title or first_commit_subject(upstream_base_sha, local_head)
        pr_description = args.pr_body or pr_body(repo, branch, upstream_repo, args.base_branch)

    print("commits to recreate:")
    for sha in commits:
        subject = str(run_git(["show", "-s", "--format=%s", sha]))
        print(f"  {sha[:7]} {subject}")
    if args.dry_run:
        print("dry run: no remote changes made")
        if args.pr and upstream_repo and pr_title and pr_description:
            ensure_pull_request(
                source_repo=repo,
                source_branch=branch,
                base_repo=upstream_repo,
                base_branch=args.base_branch,
                title=pr_title,
                body=pr_description,
                dry_run=True,
            )
        return 0

    parent_sha = remote_sha
    for local_sha in commits:
        entries: list[dict[str, Any]] = []
        for change in changed_paths(local_sha):
            if change["status"] in {"D", "R"}:
                entries.append(
                    {
                        "path": change.get("old_path", change["path"]),
                        "mode": "100644",
                        "type": "blob",
                        "sha": None,
                    }
                )
            if change["status"] == "D":
                continue
            path = change["path"]
            blob = gh(
                repo,
                "POST",
                "/git/blobs",
                {"content": file_b64_at(local_sha, path), "encoding": "base64"},
            )
            entries.append(
                {
                    "path": path,
                    "mode": file_mode_at(local_sha, path),
                    "type": "blob",
                    "sha": blob["sha"],
                }
            )

        parent_commit = gh(repo, "GET", f"/git/commits/{parent_sha}")
        tree = gh(repo, "POST", "/git/trees", {"base_tree": parent_commit["tree"]["sha"], "tree": entries})
        meta = commit_meta(local_sha)
        commit = gh(
            repo,
            "POST",
            "/git/commits",
            {
                "message": meta["message"],
                "tree": tree["sha"],
                "parents": [parent_sha],
                "author": meta["author"],
                "committer": meta["committer"],
            },
        )
        print(f"created {commit['sha']} for local {local_sha[:7]} {meta['message'].splitlines()[0]}")
        parent_sha = commit["sha"]

    gh(repo, "PATCH", f"/git/refs/heads/{branch}", {"sha": parent_sha, "force": False})
    remote_commit = gh(repo, "GET", f"/git/commits/{parent_sha}")
    local_tree = str(run_git(["rev-parse", "HEAD^{tree}"]))
    remote_tree = remote_commit["tree"]["sha"]
    if local_tree != remote_tree:
        raise SystemExit(f"Remote tree mismatch: local {local_tree}, remote {remote_tree}")
    print(f"updated {branch} -> {parent_sha}")
    print(f"verified tree {remote_tree}")

    tracking_refreshed = False
    if not args.no_update_tracking_ref:
        tracking_refreshed = refresh_remote_tracking(args.remote, branch)
        if tracking_refreshed:
            print(f"refreshed refs/remotes/{args.remote}/{branch}")
    if not args.no_align_local_ref and tracking_refreshed:
        align_checked_out_branch(branch, local_head, parent_sha, remote_tree)
    elif not args.no_align_local_ref:
        print("warning: local branch was not aligned because the remote-tracking ref was not refreshed")
    if args.pr and upstream_repo and pr_title and pr_description:
        ensure_pull_request(
            source_repo=repo,
            source_branch=branch,
            base_repo=upstream_repo,
            base_branch=args.base_branch,
            title=pr_title,
            body=pr_description,
            dry_run=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
