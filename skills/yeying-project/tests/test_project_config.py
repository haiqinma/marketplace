import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from project_config import ConfigError, load  # noqa: E402


class ProjectConfigTest(unittest.TestCase):
    def test_toml_config_uses_standard_project_path_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                '[project]\nurl = "http://localhost:8080"\naccess_key = "ak"\nsecret_key = "sk"\n',
                encoding="utf-8",
            )
            path.chmod(0o600)
            settings = load(path)
            self.assertEqual(settings.base_url, "http://localhost:8080")
            self.assertEqual(settings.access_key, "ak")
            self.assertEqual(settings.source, "file")

    def test_environment_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                '[project]\nurl = "http://file"\naccess_key = "file-ak"\nsecret_key = "file-sk"\n',
                encoding="utf-8",
            )
            path.chmod(0o600)
            with mock.patch.dict(os.environ, {
                "YEYING_PROJECT_URL": "http://env",
                "YEYING_PROJECT_AK": "env-ak",
                "YEYING_PROJECT_SK": "env-sk",
            }, clear=False):
                settings = load(path)
            self.assertEqual(settings.base_url, "http://env")
            self.assertEqual(settings.access_key, "env-ak")
            self.assertEqual(settings.secret_key, "env-sk")
            self.assertEqual(settings.source, "env")

    def test_secret_config_requires_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('[project]\nsecret_key = "sk"\n', encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(ConfigError):
                load(path)


if __name__ == "__main__":
    unittest.main()
