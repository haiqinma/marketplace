from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_api_push  # noqa: E402
from github_config import Settings  # noqa: E402


class GitHubApiPushTests(unittest.TestCase):
    def test_credentials_are_loaded_from_settings(self) -> None:
        settings = Settings(
            mode="api",
            visibility="auto",
            sync_script="scripts/sync.sh",
            pr_script="scripts/pr.sh",
            origin_token="configured-origin",
            upstream_token="configured-upstream",
            config_path=Path("/secure/config.toml"),
        )
        github_api_push.configure_credentials(settings, require_upstream=True)
        self.assertEqual(github_api_push.token(), "configured-origin")
        self.assertEqual(github_api_push.upstream_token(), "configured-upstream")

    def test_upstream_token_is_required_only_for_pr_operations(self) -> None:
        settings = Settings(
            mode="api",
            visibility="auto",
            sync_script="scripts/sync.sh",
            pr_script="scripts/pr.sh",
            origin_token="configured-origin",
            upstream_token="",
            config_path=Path("/secure/config.toml"),
        )
        github_api_push.configure_credentials(settings, require_upstream=False)
        self.assertEqual(github_api_push.token(), "configured-origin")
        with self.assertRaisesRegex(SystemExit, "upstream_token"):
            github_api_push.configure_credentials(settings, require_upstream=True)

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
            github_api_push, "upstream_token", return_value="token"
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


if __name__ == "__main__":
    unittest.main()
