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
    def test_defaults_to_api(self) -> None:
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(
            os.environ, {}, clear=True
        ), mock.patch.object(
            github_config, "DEFAULT_CONFIG_PATH", Path(home) / ".yeying/skills/github/config.toml"
        ):
            settings = load()
        self.assertEqual(settings.mode, "api")
        self.assertEqual(settings.visibility, "auto")
        self.assertEqual(settings.sync_script, "scripts/sync.sh")
        self.assertEqual(settings.pr_script, "scripts/pr.sh")
        self.assertEqual(settings.public.fork_token, "")
        self.assertEqual(settings.private.fork_token, "")
        self.assertEqual(settings.public.provider, "pat")

    def test_cli_mode_overrides_env_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[github]\nmode = "git"\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"YEYING_GITHUB_MODE": "git"}, clear=True):
                settings = load(config, "api")
        self.assertEqual(settings.mode, "api")

    def test_rejects_invalid_mode(self) -> None:
        with mock.patch.dict(os.environ, {"YEYING_GITHUB_MODE": "ssh"}, clear=True):
            with self.assertRaises(ConfigError):
                load()

    def test_visibility_override_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github]\nvisibility = "public"\n', encoding="utf-8"
            )
            with mock.patch.dict(
                os.environ, {"YEYING_GITHUB_VISIBILITY": "private"}, clear=True
            ):
                settings = load(config, visibility_override="auto")
        self.assertEqual(settings.visibility, "auto")

    def test_accepts_public_and_private_visibility(self) -> None:
        for visibility in ("public", "private"):
            with self.subTest(visibility=visibility), tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / "config.toml"
                config.write_text(
                    f'[github]\nvisibility = "{visibility}"\n', encoding="utf-8"
                )
                settings = load(config)
            self.assertEqual(settings.visibility, visibility)

    def test_rejects_invalid_visibility(self) -> None:
        with mock.patch.dict(
            os.environ, {"YEYING_GITHUB_VISIBILITY": "internal"}, clear=True
        ):
            with self.assertRaisesRegex(ConfigError, "visibility"):
                load()

    def test_loads_visibility_profiles_only_from_secure_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\nfork_token = "public-fork"\n'
                'pull_request_token = "public-pr"\n'
                '[github.private]\nfork_token = "private-fork"\n'
                'pull_request_token = "private-pr"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with mock.patch.dict(
                os.environ,
                {"GH_TOKEN": "ambient-origin", "UPSTREAM_TOKEN": "ambient-upstream"},
                clear=True,
            ):
                settings = load(config)
        self.assertEqual(settings.public.fork_token, "public-fork")
        self.assertEqual(settings.public.pull_request_token, "public-pr")
        self.assertEqual(settings.private.fork_token, "private-fork")
        self.assertEqual(settings.private.pull_request_token, "private-pr")

    def test_rejects_shared_token_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\ntoken = "unsupported"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with self.assertRaisesRegex(ConfigError, "Unsupported key.*token"):
                load(config)

    def test_rejects_removed_role_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\norigin_token = "old-fork"\n'
                'upstream_token = "old-pr"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with self.assertRaisesRegex(ConfigError, "Unsupported key"):
                load(config)

    def test_rejects_credentials_at_github_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github]\nfork_token = "misplaced"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with self.assertRaisesRegex(ConfigError, "Unsupported key.*fork_token"):
                load(config)

    def test_rejects_provider_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\nprovider = "pat"\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(ConfigError, "Unsupported key.*provider"):
                load(config)

    def test_rejects_pat_and_github_app_in_same_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private]\nfork_token = "private-fork"\n'
                '[github.private.github_app]\nclient_id = "Iv1.test"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with self.assertRaisesRegex(ConfigError, "both PAT and GitHub App"):
                load(config)

    def test_loads_github_app_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private.github_app]\nclient_id = "Iv1.test"\n'
                'user_token = "app-user-token"\nexpires_at = "9999999999"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            settings = load(config)
        self.assertEqual(settings.private.provider, "github_app")
        self.assertEqual(settings.private.github_app.client_id, "Iv1.test")
        self.assertEqual(settings.private.github_app.user_token, "app-user-token")

    def test_empty_pat_placeholders_do_not_conflict_with_github_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private]\nfork_token = ""\npull_request_token = ""\n'
                '[github.private.github_app]\nclient_id = "Iv1.test"\n',
                encoding="utf-8",
            )
            settings = load(config)
        self.assertEqual(settings.private.provider, "github_app")
        self.assertEqual(settings.private.github_app.client_id, "Iv1.test")

    def test_fallback_parser_supports_nested_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\nfork_token = "public-fork"\n'
                '[github.private.github_app]\nclient_id = "Iv1.test"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with mock.patch.object(github_config, "tomllib", None), mock.patch.object(
                github_config, "tomli", None
            ):
                settings = load(config)
        self.assertEqual(settings.public.fork_token, "public-fork")
        self.assertEqual(settings.private.provider, "github_app")
        self.assertEqual(settings.private.github_app.client_id, "Iv1.test")

    def test_updates_github_app_tokens_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private.github_app]\nclient_id = "Iv1.test"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            update_github_app_tokens(
                config,
                "private",
                user_token="new-user-token",
                refresh_token="new-refresh-token",
                expires_at="12345",
            )
            settings = load(config)
            mode = config.stat().st_mode & 0o777
        self.assertEqual(settings.private.github_app.user_token, "new-user-token")
        self.assertEqual(settings.private.github_app.refresh_token, "new-refresh-token")
        self.assertEqual(mode, 0o600)

    def test_rejects_token_config_readable_by_group_or_others(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private]\nfork_token = "secret"\n', encoding="utf-8"
            )
            config.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "0600"):
                load(config)

    def test_rejects_pull_request_token_readable_by_group_or_others(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private]\npull_request_token = "secret"\n', encoding="utf-8"
            )
            config.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "0600"):
                load(config)


if __name__ == "__main__":
    unittest.main()
