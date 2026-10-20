from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_delivery  # noqa: E402
from github_config import AuthProfile, GitHubAppSettings, Settings  # noqa: E402


class GitHubDeliveryTests(unittest.TestCase):
    def settings(self) -> Settings:
        app = GitHubAppSettings("", "", "", "")
        return Settings(
            mode="api",
            sync_script="scripts/sync.sh",
            pr_script="scripts/pr.sh",
            auth=AuthProfile("pat", "configured-fork", "configured-pr", app),
            config_path=Path("/secure/config.toml"),
            project="default",
            auth_table="github",
        )

    def test_parse_github_repo(self) -> None:
        self.assertEqual(
            github_delivery.parse_github_repo("git@github.com:liuppx/marketplace.git"),
            ("liuppx", "marketplace"),
        )
        self.assertEqual(
            github_delivery.parse_github_repo("https://github.com/yeying-community/books.git"),
            ("yeying-community", "books"),
        )

    def test_rejects_generic_title(self) -> None:
        with self.assertRaises(SystemExit):
            github_delivery.validate_title("update")

    def test_default_body_lists_complete_commit_range(self) -> None:
        with mock.patch.object(github_delivery, "commit_subjects", return_value=["first", "second"]):
            body = github_delivery.default_body("feat: useful delivery")
        self.assertIn("- feat: useful delivery", body)
        self.assertIn("- first", body)
        self.assertIn("- second", body)

    def test_api_command_carries_explicit_title(self) -> None:
        args = argparse.Namespace(dry_run=True, allow_dirty=True)
        command = github_delivery.api_command(
            args, self.settings(), "docs: accurate title", "body"
        )
        self.assertIn("--pr-title", command)
        self.assertEqual(command[command.index("--pr-title") + 1], "docs: accurate title")
        self.assertEqual(command[command.index("--config") + 1], "/secure/config.toml")
        self.assertNotIn("--visibility", command)
        self.assertIn("--dry-run", command)
        self.assertIn("--allow-dirty", command)

    def test_subprocess_env_replaces_ambient_tokens(self) -> None:
        with mock.patch.dict(
            github_delivery.os.environ,
            {
                "GH_TOKEN": "ambient-gh",
                "GITHUB_TOKEN": "ambient-github",
                "UPSTREAM_TOKEN": "ambient-upstream",
                "KEEP": "yes",
            },
            clear=True,
        ):
            clean = github_delivery.subprocess_env()
            pr = github_delivery.subprocess_env("configured-upstream")
        self.assertEqual(clean, {"KEEP": "yes"})
        self.assertEqual(pr, {"KEEP": "yes", "GH_TOKEN": "configured-upstream"})

    def test_existing_git_pr_title_is_corrected(self) -> None:
        existing = {"number": 12, "url": "https://github.com/yeying-community/repo/pull/12", "title": "old"}
        with mock.patch.object(
            github_delivery, "find_open_pr", return_value=existing
        ), mock.patch.object(github_delivery, "run") as run:
            env = {"GH_TOKEN": "configured-upstream"}
            github_delivery.sync_git_pr_title(
                "yeying-community/repo", "liuppx", "feat: accurate title", env
            )
        run.assert_called_once_with(
            [
                "gh",
                "pr",
                "edit",
                "12",
                "--repo",
                "yeying-community/repo",
                "--title",
                "feat: accurate title",
            ],
            env=env,
        )

if __name__ == "__main__":
    unittest.main()
