from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from github_config import ConfigError, load  # noqa: E402


class GitHubConfigTests(unittest.TestCase):
    def test_defaults_to_api(self) -> None:
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}, clear=True):
            settings = load()
        self.assertEqual(settings.mode, "api")
        self.assertEqual(settings.sync_script, "scripts/sync.sh")
        self.assertEqual(settings.pr_script, "scripts/pr.sh")

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


if __name__ == "__main__":
    unittest.main()
