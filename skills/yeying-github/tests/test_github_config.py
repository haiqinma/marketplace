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
from github_config import ConfigError, load  # noqa: E402


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
        self.assertEqual(settings.origin_token, "")
        self.assertEqual(settings.upstream_token, "")

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

    def test_loads_tokens_only_from_secure_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[github]\norigin_token = "origin-secret"\nupstream_token = "upstream-secret"\n',
                encoding="utf-8",
            )
            config.chmod(0o600)
            with mock.patch.dict(
                os.environ,
                {"GH_TOKEN": "ambient-origin", "UPSTREAM_TOKEN": "ambient-upstream"},
                clear=True,
            ):
                settings = load(config)
        self.assertEqual(settings.origin_token, "origin-secret")
        self.assertEqual(settings.upstream_token, "upstream-secret")

    def test_rejects_token_config_readable_by_group_or_others(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[github]\norigin_token = "secret"\n', encoding="utf-8")
            config.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "0600"):
                load(config)


if __name__ == "__main__":
    unittest.main()
