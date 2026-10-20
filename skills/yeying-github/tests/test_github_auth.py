from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_auth  # noqa: E402
from github_config import AuthProfile, GitHubAppSettings, Settings  # noqa: E402


def settings(auth: AuthProfile, *, project: str = "default") -> Settings:
    table = "github" if project == "default" else f"github.projects.{project}"
    return Settings(
        mode="api",
        visibility="auto",
        sync_script="scripts/sync.sh",
        pr_script="scripts/pr.sh",
        auth=auth,
        config_path=Path("/secure/config.toml"),
        project=project,
        auth_table=table,
    )


class GitHubAuthTests(unittest.TestCase):
    def test_pat_uses_resolved_default_credentials(self) -> None:
        empty_app = GitHubAppSettings("", "", "", "")
        configured = settings(
            AuthProfile("pat", "default-fork", "default-pr", empty_app)
        )
        credentials = github_auth.credentials_for(configured)
        self.assertEqual(credentials.fork_token, "default-fork")
        self.assertEqual(credentials.pull_request_token, "default-pr")

    def test_project_missing_token_error_names_project_table(self) -> None:
        empty_app = GitHubAppSettings("", "", "", "")
        configured = settings(
            AuthProfile("pat", "project-fork", "", empty_app),
            project="private_repo",
        )
        with self.assertRaisesRegex(
            SystemExit, "github.projects.private_repo.pull_request_token"
        ):
            github_auth.credentials_for(configured)

    def test_git_mode_can_omit_fork_pat(self) -> None:
        empty_app = GitHubAppSettings("", "", "", "")
        configured = settings(AuthProfile("pat", "", "default-pr", empty_app))
        credentials = github_auth.credentials_for(configured, require_fork=False)
        self.assertEqual(credentials.pull_request_token, "default-pr")

    def test_github_app_uses_current_user_token_for_both_repositories(self) -> None:
        app = GitHubAppSettings("Iv1.test", "app-user-token", "", "9999999999")
        configured = settings(
            AuthProfile("github_app", "", "", app), project="private_repo"
        )
        credentials = github_auth.credentials_for(configured)
        self.assertEqual(credentials.provider, "github_app")
        self.assertEqual(credentials.fork_token, "app-user-token")
        self.assertEqual(credentials.pull_request_token, "app-user-token")

    def test_expired_github_app_token_is_refreshed_in_selected_table(self) -> None:
        app = GitHubAppSettings("Iv1.test", "expired", "refresh-secret", "1")
        configured = settings(
            AuthProfile("github_app", "", "", app), project="private_repo"
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
            credentials = github_auth.credentials_for(configured)
        self.assertEqual(credentials.fork_token, "new-user-token")
        self.assertEqual(
            update.call_args.args[:2],
            (Path("/secure/config.toml"), "github.projects.private_repo"),
        )


if __name__ == "__main__":
    unittest.main()
