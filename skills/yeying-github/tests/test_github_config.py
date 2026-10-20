from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_config  # noqa: E402
from github_config import ConfigError, load, update_github_app_tokens  # noqa: E402


class GitHubConfigTests(unittest.TestCase):
    def write_config(self, directory: str, content: str, *, secure: bool = False) -> Path:
        config = Path(directory) / "config.toml"
        config.write_text(content, encoding="utf-8")
        if secure:
            config.chmod(0o600)
        return config

    def test_defaults_resolve_for_any_repository_pair(self) -> None:
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {}, clear=True
        ), mock.patch.object(
            github_config, "DEFAULT_CONFIG_PATH", Path(home) / ".yeying/skills/github/config.toml"
        ):
            settings = load().resolve("liuppx/repo", "yeying-community/repo")
        self.assertEqual(settings.mode, "api")
        self.assertEqual(settings.visibility, "auto")
        self.assertEqual(settings.sync_script, "scripts/sync.sh")
        self.assertEqual(settings.pr_script, "scripts/pr.sh")
        self.assertEqual(settings.project, "default")
        self.assertEqual(settings.auth_table, "github")
        self.assertEqual(settings.auth.provider, "pat")

    def test_project_overrides_defaults_and_cli_has_highest_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github]\nmode = "api"\nvisibility = "auto"\n'
                '[github.projects.marketplace]\n'
                'origin = "liuppx/marketplace"\n'
                'upstream = "yeying-community/marketplace"\n'
                'mode = "git"\nvisibility = "public"\n',
            )
            loaded = load(config, mode_override="api")
            settings = loaded.resolve(
                "liuppx/marketplace", "yeying-community/marketplace"
            )
        self.assertEqual(settings.mode, "api")
        self.assertEqual(settings.visibility, "public")
        self.assertEqual(settings.project, "marketplace")

    def test_environment_override_has_precedence_over_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.repo]\norigin = "me/repo"\nupstream = "org/repo"\n'
                'visibility = "private"\n',
            )
            with mock.patch.dict(
                os.environ, {"YEYING_GITHUB_VISIBILITY": "public"}, clear=True
            ):
                settings = load(config).resolve("me/repo", "org/repo")
        self.assertEqual(settings.visibility, "public")

    def test_default_pat_is_used_when_no_project_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github]\nfork_token = "default-fork"\n'
                'pull_request_token = "default-pr"\n'
                '[github.projects.special]\norigin = "me/special"\n'
                'upstream = "org/special"\n',
                secure=True,
            )
            with mock.patch.dict(
                os.environ,
                {"GH_TOKEN": "ambient", "GITHUB_TOKEN": "ambient"},
                clear=True,
            ):
                settings = load(config).resolve("me/ordinary", "org/ordinary")
        self.assertEqual(settings.auth.fork_token, "default-fork")
        self.assertEqual(settings.auth.pull_request_token, "default-pr")
        self.assertEqual(settings.project, "default")

    def test_project_without_auth_inherits_default_auth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github]\nfork_token = "default-fork"\n'
                'pull_request_token = "default-pr"\n'
                '[github.projects.marketplace]\n'
                'origin = "liuppx/marketplace"\n'
                'upstream = "yeying-community/marketplace"\n'
                'visibility = "public"\n',
                secure=True,
            )
            settings = load(config).resolve(
                "liuppx/marketplace", "yeying-community/marketplace"
            )
        self.assertEqual(settings.project, "marketplace")
        self.assertEqual(settings.auth_table, "github")
        self.assertEqual(settings.auth.fork_token, "default-fork")

    def test_project_auth_replaces_default_auth_as_a_unit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github]\nfork_token = "default-fork"\n'
                'pull_request_token = "default-pr"\n'
                '[github.projects.private_repo]\norigin = "me/private"\n'
                'upstream = "org/private"\nfork_token = "project-fork"\n',
                secure=True,
            )
            settings = load(config).resolve("me/private", "org/private")
        self.assertEqual(settings.auth.fork_token, "project-fork")
        self.assertEqual(settings.auth.pull_request_token, "")
        self.assertEqual(settings.auth_table, "github.projects.private_repo")

    def test_repository_pair_matching_is_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.repo]\norigin = "Liuppx/Repo"\n'
                'upstream = "YeYing-Community/Repo"\nvisibility = "public"\n',
            )
            settings = load(config).resolve("liuppx/repo", "yeying-community/repo")
        self.assertEqual(settings.project, "repo")

    def test_partial_project_match_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.repo]\norigin = "me/repo"\n'
                'upstream = "org/repo"\n',
            )
            with self.assertRaisesRegex(ConfigError, "partially matches"):
                load(config).resolve("me/repo", "another/repo")

    def test_duplicate_repository_pair_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.first]\norigin = "me/repo"\nupstream = "org/repo"\n'
                '[github.projects.second]\norigin = "ME/REPO"\nupstream = "ORG/REPO"\n',
            )
            with self.assertRaisesRegex(ConfigError, "duplicates repository pair"):
                load(config)

    def test_project_requires_origin_and_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.repo]\norigin = "me/repo"\n',
            )
            with self.assertRaisesRegex(ConfigError, "upstream.*owner/repository"):
                load(config)

    def test_named_project_resolution_supports_github_app_login(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.private_repo]\norigin = "me/private"\n'
                'upstream = "org/private"\n'
                '[github.projects.private_repo.github_app]\nclient_id = "Iv1.test"\n',
            )
            settings = load(config).resolve_project("private_repo")
        self.assertEqual(settings.auth.provider, "github_app")
        self.assertEqual(settings.auth.github_app.client_id, "Iv1.test")
        self.assertEqual(settings.auth_table, "github.projects.private_repo")

    def test_unknown_named_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(directory, "[github]\n")
            with self.assertRaisesRegex(ConfigError, "Unknown GitHub project"):
                load(config).resolve_project("missing")

    def test_rejects_old_visibility_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.public]\nfork_token = "old"\n',
                secure=True,
            )
            with self.assertRaisesRegex(ConfigError, "Unsupported key.*public"):
                load(config)

    def test_rejects_shared_and_removed_token_fields(self) -> None:
        for field in ("token", "origin_token", "upstream_token", "provider"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                config = self.write_config(
                    directory,
                    f'[github]\n{field} = "unsupported"\n',
                    secure=True,
                )
                with self.assertRaisesRegex(ConfigError, f"Unsupported key.*{field}"):
                    load(config)

    def test_rejects_pat_and_github_app_in_same_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github]\nfork_token = "fork"\n'
                '[github.github_app]\nclient_id = "Iv1.test"\n',
                secure=True,
            )
            with self.assertRaisesRegex(ConfigError, "both PAT and GitHub App"):
                load(config)

    def test_rejects_unused_github_app_client_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.github_app]\nclient_id = "Iv1.test"\n'
                'client_secret = "unused"\n',
            )
            with self.assertRaisesRegex(ConfigError, "Unsupported key.*client_secret"):
                load(config)

    def test_empty_pat_placeholders_do_not_conflict_with_github_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github]\nfork_token = ""\npull_request_token = ""\n'
                '[github.github_app]\nclient_id = "Iv1.test"\n',
            )
            settings = load(config).resolve_project("default")
        self.assertEqual(settings.auth.provider, "github_app")

    def test_fallback_parser_supports_nested_project_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.private_repo]\norigin = "me/private"\n'
                'upstream = "org/private"\n'
                '[github.projects.private_repo.github_app]\nclient_id = "Iv1.test"\n',
            )
            with mock.patch.object(github_config, "tomllib", None), mock.patch.object(
                github_config, "tomli", None
            ):
                settings = load(config).resolve("me/private", "org/private")
        self.assertEqual(settings.auth.provider, "github_app")

    def test_updates_project_github_app_tokens_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github.projects.private_repo]\norigin = "me/private"\n'
                'upstream = "org/private"\n'
                '[github.projects.private_repo.github_app]\nclient_id = "Iv1.test"\n',
            )
            update_github_app_tokens(
                config,
                "github.projects.private_repo",
                user_token="new-user-token",
                refresh_token="new-refresh-token",
                expires_at="12345",
            )
            settings = load(config).resolve_project("private_repo")
            mode = config.stat().st_mode & 0o777
        self.assertEqual(settings.auth.github_app.user_token, "new-user-token")
        self.assertEqual(settings.auth.github_app.refresh_token, "new-refresh-token")
        self.assertEqual(mode, 0o600)

    def test_rejects_token_config_readable_by_group_or_others(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.write_config(
                directory,
                '[github]\npull_request_token = "secret"\n',
            )
            config.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "0600"):
                load(config)


if __name__ == "__main__":
    unittest.main()
