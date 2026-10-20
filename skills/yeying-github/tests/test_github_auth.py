from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_auth  # noqa: E402
from github_config import AuthProfile, GitHubAppSettings, Settings  # noqa: E402


def settings(public: AuthProfile, private: AuthProfile) -> Settings:
    return Settings(
        mode="api",
        visibility="auto",
        sync_script="scripts/sync.sh",
        pr_script="scripts/pr.sh",
        public=public,
        private=private,
        config_path=Path("/secure/config.toml"),
    )


class GitHubAuthTests(unittest.TestCase):
    def test_pat_profiles_do_not_fall_back_to_each_other(self) -> None:
        empty_app = GitHubAppSettings("", "", "", "")
        configured = settings(
            AuthProfile("pat", "public-fork", "public-pr", empty_app),
            AuthProfile("pat", "", "", empty_app),
        )
        public = github_auth.credentials_for(configured, "public")
        self.assertEqual(public.fork_token, "public-fork")
        with self.assertRaisesRegex(SystemExit, "github.private.fork_token"):
            github_auth.credentials_for(configured, "private")

    def test_git_mode_can_omit_fork_pat(self) -> None:
        empty_app = GitHubAppSettings("", "", "", "")
        configured = settings(
            AuthProfile("pat", "", "public-pr", empty_app),
            AuthProfile("pat", "", "", empty_app),
        )
        credentials = github_auth.credentials_for(
            configured, "public", require_fork=False
        )
        self.assertEqual(credentials.pull_request_token, "public-pr")

    def test_github_app_uses_current_user_token_for_both_repositories(self) -> None:
        empty_app = GitHubAppSettings("", "", "", "")
        app = GitHubAppSettings("Iv1.test", "app-user-token", "", "9999999999")
        configured = settings(
            AuthProfile("pat", "", "", empty_app),
            AuthProfile("github_app", "", "", app),
        )
        credentials = github_auth.credentials_for(configured, "private")
        self.assertEqual(credentials.provider, "github_app")
        self.assertEqual(credentials.fork_token, "app-user-token")
        self.assertEqual(credentials.pull_request_token, "app-user-token")

    def test_expired_github_app_token_is_refreshed_and_stored(self) -> None:
        empty_app = GitHubAppSettings("", "", "", "")
        app = GitHubAppSettings("Iv1.test", "expired", "refresh-secret", "1")
        configured = settings(
            AuthProfile("pat", "", "", empty_app),
            AuthProfile("github_app", "", "", app),
        )
        with mock.patch.object(
            github_auth,
            "_oauth_post",
            return_value={
                "access_token": "new-user-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 28800,
            },
        ), mock.patch.object(github_auth, "update_github_app_tokens") as update:
            credentials = github_auth.credentials_for(configured, "private")
        self.assertEqual(credentials.fork_token, "new-user-token")
        update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
