from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_delivery  # noqa: E402
from github_config import Settings  # noqa: E402


class GitHubDeliveryTests(unittest.TestCase):
    def settings(self) -> Settings:
        return Settings(
            mode="api",
            visibility="auto",
            sync_script="scripts/sync.sh",
            pr_script="scripts/pr.sh",
            origin_token="origin-secret",
            upstream_token="upstream-secret",
            config_path=Path("/secure/config.toml"),
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
        command = github_delivery.api_command(args, self.settings(), "docs: accurate title", "body")
        self.assertIn("--pr-title", command)
        self.assertEqual(command[command.index("--pr-title") + 1], "docs: accurate title")
        self.assertEqual(command[command.index("--config") + 1], "/secure/config.toml")
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

    def test_detects_public_repository_pair(self) -> None:
        with mock.patch.object(
            github_delivery,
            "github_repo_metadata",
            side_effect=[{"visibility": "public"}, {"private": False}],
        ) as metadata:
            visibility = github_delivery.resolve_repository_visibility(
                "auto", "liuppx/repo", "yeying-community/repo", "configured-token"
            )
        self.assertEqual(visibility, "public")
        self.assertEqual(metadata.call_count, 2)

    def test_detects_private_repository_pair(self) -> None:
        with mock.patch.object(
            github_delivery,
            "github_repo_metadata",
            side_effect=[{"visibility": "private"}, {"private": True}],
        ):
            visibility = github_delivery.resolve_repository_visibility(
                "private", "liuppx/repo", "yeying-community/repo", "configured-token"
            )
        self.assertEqual(visibility, "private")

    def test_rejects_mixed_repository_visibility(self) -> None:
        with mock.patch.object(
            github_delivery,
            "github_repo_metadata",
            side_effect=[{"visibility": "public"}, {"visibility": "private"}],
        ), self.assertRaisesRegex(SystemExit, "different GitHub visibility"):
            github_delivery.resolve_repository_visibility(
                "auto", "liuppx/repo", "yeying-community/repo", "configured-token"
            )

    def test_rejects_explicit_visibility_mismatch(self) -> None:
        with mock.patch.object(
            github_delivery,
            "github_repo_metadata",
            side_effect=[{"visibility": "private"}, {"visibility": "private"}],
        ), self.assertRaisesRegex(SystemExit, "Configured visibility is public"):
            github_delivery.resolve_repository_visibility(
                "public", "liuppx/repo", "yeying-community/repo", "configured-token"
            )

    def test_requires_pr_credential_for_visibility_preflight(self) -> None:
        with self.assertRaisesRegex(SystemExit, "missing upstream_token"):
            github_delivery.resolve_repository_visibility(
                "auto", "liuppx/repo", "yeying-community/repo", ""
            )

    def test_private_access_error_does_not_expose_token(self) -> None:
        error = github_delivery.urllib.error.HTTPError(
            "https://api.github.com/repos/private/repo", 404, "Not Found", {}, None
        )
        with mock.patch.object(
            github_delivery.urllib.request, "urlopen", side_effect=error
        ), self.assertRaises(SystemExit) as raised:
            github_delivery.github_repo_metadata("private/repo", "super-secret")
        self.assertIn("must read both", str(raised.exception))
        self.assertNotIn("super-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
