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
        self.assertEqual(settings.public.origin_token, "")
        self.assertEqual(settings.private.origin_token, "")
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
                '[github.public]\norigin_token = "public-origin"\n'
                'upstream_token = "public-upstream"\n'
                '[github.private]\norigin_token = "private-origin"\n'
                'upstream_token = "private-upstream"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with mock.patch.dict(
                os.environ,
                {"GH_TOKEN": "ambient-origin", "UPSTREAM_TOKEN": "ambient-upstream"},
                clear=True,
            ):
                settings = load(config)
        self.assertEqual(settings.public.origin_token, "public-origin")
        self.assertEqual(settings.public.upstream_token, "public-upstream")
        self.assertEqual(settings.private.origin_token, "private-origin")
        self.assertEqual(settings.private.upstream_token, "private-upstream")

    def test_shared_token_populates_both_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\ntoken = "public-shared"\n'
                '[github.private]\ntoken = "private-shared"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            settings = load(config)
        self.assertEqual(settings.public.origin_token, "public-shared")
        self.assertEqual(settings.public.upstream_token, "public-shared")
        self.assertEqual(settings.private.origin_token, "private-shared")
        self.assertEqual(settings.private.upstream_token, "private-shared")

    def test_shared_token_does_not_cross_visibility_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\ntoken = "public-shared"\n', encoding="utf-8"
            )
            config.chmod(0o600)
            settings = load(config)
        self.assertEqual(settings.public.origin_token, "public-shared")
        self.assertEqual(settings.private.origin_token, "")
        self.assertEqual(settings.private.upstream_token, "")

    def test_role_tokens_override_shared_token_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\ntoken = "shared"\n'
                'origin_token = "origin-only"\n'
                '[github.private]\ntoken = "private-shared"\n'
                'upstream_token = "upstream-only"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            settings = load(config)
        self.assertEqual(settings.public.origin_token, "origin-only")
        self.assertEqual(settings.public.upstream_token, "shared")
        self.assertEqual(settings.private.origin_token, "private-shared")
        self.assertEqual(settings.private.upstream_token, "upstream-only")

    def test_legacy_tokens_are_public_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github]\norigin_token = "legacy-origin"\n'
                'upstream_token = "legacy-upstream"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            settings = load(config)
        self.assertEqual(settings.public.origin_token, "legacy-origin")
        self.assertEqual(settings.private.origin_token, "")

    def test_loads_github_app_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private]\nprovider = "github_app"\n'
                '[github.private.github_app]\nclient_id = "Iv1.test"\n'
                'user_token = "app-user-token"\nexpires_at = "9999999999"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            settings = load(config)
        self.assertEqual(settings.private.provider, "github_app")
        self.assertEqual(settings.private.github_app.client_id, "Iv1.test")
        self.assertEqual(settings.private.github_app.user_token, "app-user-token")

    def test_fallback_parser_supports_nested_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.public]\nprovider = "pat"\n'
                'origin_token = "public-origin"\n'
                '[github.private]\nprovider = "github_app"\n'
                '[github.private.github_app]\nclient_id = "Iv1.test"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with mock.patch.object(github_config, "tomllib", None), mock.patch.object(
                github_config, "tomli", None
            ):
                settings = load(config)
        self.assertEqual(settings.public.origin_token, "public-origin")
        self.assertEqual(settings.private.provider, "github_app")
        self.assertEqual(settings.private.github_app.client_id, "Iv1.test")

    def test_updates_github_app_tokens_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private]\nprovider = "github_app"\n'
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
                '[github.private]\norigin_token = "secret"\n', encoding="utf-8"
            )
            config.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "0600"):
                load(config)

    def test_rejects_shared_token_readable_by_group_or_others(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github.private]\ntoken = "secret"\n', encoding="utf-8"
            )
            config.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "0600"):
                load(config)


if __name__ == "__main__":
    unittest.main()
