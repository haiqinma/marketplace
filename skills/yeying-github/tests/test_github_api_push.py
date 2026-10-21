from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_api_push  # noqa: E402
from github_auth import Credentials  # noqa: E402


class GitHubApiPushTests(unittest.TestCase):
    def test_credentials_are_loaded_from_settings(self) -> None:
        credentials = Credentials(
            provider="pat",
            fork_token="configured-fork",
            pull_request_token="configured-pr",
        )
        github_api_push.configure_credentials(
            credentials, "/secure/config.toml", require_pull_request=True
        )
        self.assertEqual(github_api_push.fork_token(), "configured-fork")
        self.assertEqual(github_api_push.pull_request_token(), "configured-pr")

    def test_pull_request_token_is_required_only_for_pr_operations(self) -> None:
        credentials = Credentials(
            provider="pat",
            fork_token="configured-fork",
            pull_request_token="",
        )
        github_api_push.configure_credentials(
            credentials, "/secure/config.toml", require_pull_request=False
        )
        self.assertEqual(github_api_push.fork_token(), "configured-fork")
        with self.assertRaisesRegex(SystemExit, "pull_request_token"):
            github_api_push.configure_credentials(
                credentials, "/secure/config.toml", require_pull_request=True
            )

    def test_existing_pr_title_is_updated_without_replacing_body(self) -> None:
        source = github_api_push.Repo("liuppx", "repo")
        base = github_api_push.Repo("yeying-community", "repo")
        existing = {
            "number": 7,
            "html_url": "https://github.com/yeying-community/repo/pull/7",
            "title": "old title",
            "body": "Human-maintained body",
        }
        with mock.patch.object(
            github_api_push, "pull_request_token", return_value="token"
        ), mock.patch.object(github_api_push, "gh", side_effect=[[existing], {}]) as gh:
            github_api_push.ensure_pull_request(
                source_repo=source,
                source_branch="main",
                base_repo=base,
                base_branch="main",
                title="feat: accurate title",
                body="Generated body",
                dry_run=False,
            )
        patch_call = gh.call_args_list[1]
        self.assertEqual(patch_call.args[1], "PATCH")
        self.assertEqual(patch_call.args[3], {"title": "feat: accurate title"})

    def test_empty_commit_reuses_parent_tree_without_creating_empty_tree(self) -> None:
        repo = github_api_push.Repo("liuppx", "repo")
        with mock.patch.object(
            github_api_push,
            "gh",
            return_value={"tree": {"sha": "parent-tree"}},
        ) as gh:
            tree_sha = github_api_push.tree_for_changes(repo, "parent-commit", [])
        self.assertEqual(tree_sha, "parent-tree")
        gh.assert_called_once_with(repo, "GET", "/git/commits/parent-commit")


if __name__ == "__main__":
    unittest.main()
