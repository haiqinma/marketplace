import json
import hashlib
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import warehouse_tool  # noqa: E402
import warehouse_config  # noqa: E402


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class WarehouseToolClientTest(unittest.TestCase):
    def test_put_forwards_checksum_if_match_and_trace(self):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["headers"] = dict(req.headers)
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse({"name": "warehouse.object.put", "result": {}})

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                '[warehouse]\n'
                'url = "http://warehouse.test"\n'
                'tool_token = "wts_test-secret"\n',
                encoding="utf-8",
            )
            config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch("urllib.request.urlopen", fake_urlopen):
                with mock.patch("sys.argv", ["warehouse_tool.py", "--config", str(config_path), "put",
                                              "/personal/a.txt", "hello", "--checksum-sha256", "abc",
                                              "--if-match", "etag-1", "--overwrite", "--trace-id", "trace-1"]):
                    self.assertEqual(warehouse_tool.main(), 0)

        self.assertEqual(captured["body"]["traceId"], "trace-1")
        args = captured["body"]["arguments"]
        self.assertEqual(args["checksumSha256"], "abc")
        self.assertEqual(args["ifMatch"], "etag-1")
        self.assertTrue(args["overwrite"])
        self.assertEqual(captured["headers"]["X-trace-id"], "trace-1")
        self.assertEqual(captured["timeout"], 30)

    def test_put_file_uses_configured_directory_and_binary_encoding(self):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse({"name": "warehouse.object.put", "result": {}})

        with tempfile.TemporaryDirectory() as tmp:
            local_file = Path(tmp) / "sample.bin"
            local_file.write_bytes(b"\x00\xffwarehouse")
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                '[warehouse]\n'
                'url = "http://file.test"\n'
                'tool_token = "file-token"\n'
                'upload_directory = "/personal/backups"\n',
                encoding="utf-8",
            )
            config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch("urllib.request.urlopen", fake_urlopen):
                with mock.patch("sys.argv", ["warehouse_tool.py", "--config", str(config_path),
                                              "put-file", str(local_file)]):
                    self.assertEqual(warehouse_tool.main(), 0)

        arguments = captured["body"]["arguments"]
        self.assertEqual(arguments["path"], "/personal/backups/sample.bin")
        self.assertEqual(arguments["encoding"], "base64")
        self.assertEqual(arguments["content"], "AP93YXJlaG91c2U=")
        self.assertEqual(arguments["checksumSha256"], hashlib.sha256(b"\x00\xffwarehouse").hexdigest())

    def test_put_file_requires_destination_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_file = Path(tmp) / "sample.txt"
            local_file.write_text("hello", encoding="utf-8")
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                '[warehouse]\nurl = "http://file.test"\ntool_token = "file-token"\n',
                encoding="utf-8",
            )
            config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("sys.argv", ["warehouse_tool.py", "--config", str(config_path),
                                              "put-file", str(local_file)]):
                    with self.assertRaises(SystemExit) as raised:
                        warehouse_tool.main()
                    self.assertEqual(raised.exception.code, 2)

    def test_config_requires_explicit_url_and_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            default_path = Path(tmp) / "missing-config.toml"
            with mock.patch.object(warehouse_config, "DEFAULT_CONFIG_PATH", default_path):
                with mock.patch.dict(os.environ, {}, clear=True):
                    with self.assertRaises(SystemExit) as raised:
                        warehouse_tool.config()
                    self.assertEqual(raised.exception.code, 2)

    def test_toml_config_and_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('[warehouse]\nurl = "http://file.test"\ntool_token = "file-token"\n', encoding="utf-8")
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with mock.patch.dict(os.environ, {}, clear=True):
                settings = __import__("warehouse_config").load(path)
                self.assertEqual(settings.base_url, "http://file.test")
                self.assertEqual(settings.token, "file-token")
            path.write_text(
                '[warehouse]\n'
                'url = "http://file.test"\n'
                'tool_token = "file-token"\n'
                'upload_directory = "/file/backups"\n',
                encoding="utf-8",
            )
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with mock.patch.dict(os.environ, {}, clear=True):
                settings = __import__("warehouse_config").load(path)
                self.assertEqual(settings.upload_directory, "/file/backups")
            with mock.patch.dict(os.environ, {
                "YEYING_WAREHOUSE_URL": "http://env.test",
                "YEYING_WAREHOUSE_TOOL_TOKEN": "env-token",
                "YEYING_WAREHOUSE_UPLOAD_DIRECTORY": "/env/backups",
            }, clear=True):
                settings = __import__("warehouse_config").load(path)
                self.assertEqual(settings.base_url, "http://env.test")
                self.assertEqual(settings.token, "env-token")
                self.assertEqual(settings.upload_directory, "/env/backups")

    def test_toml_token_requires_private_file_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('[warehouse]\nurl = "http://file.test"\ntool_token = "file-token"\n', encoding="utf-8")
            path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
            with self.assertRaises(__import__("warehouse_config").ConfigError):
                __import__("warehouse_config").load(path)


if __name__ == "__main__":
    unittest.main()
