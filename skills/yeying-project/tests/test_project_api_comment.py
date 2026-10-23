import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_api  # noqa: E402


class ProjectApiCommentTest(unittest.TestCase):
    def test_ensure_task_dialog_creates_or_reuses_project_dialog(self):
        calls = []

        def request(_config, method, path, params, **_kwargs):
            calls.append((method, path, params))
            return {"dialog_id": 456}

        with mock.patch.object(project_api, "request_api", side_effect=request):
            self.assertEqual(project_api.ensure_task_dialog_id({}, 123), 456)

        self.assertEqual(calls, [("GET", "/api/project/task/dialog", {"task_id": 123})])

    def test_ensure_task_dialog_rejects_empty_dialog_id(self):
        with mock.patch.object(project_api, "request_api", return_value={"dialog_id": 0}):
            with self.assertRaisesRegex(project_api.ProjectApiError, "对话创建失败"):
                project_api.ensure_task_dialog_id({}, 123)

    def test_comment_sends_model_name(self):
        calls = []

        def request(_config, method, path, params, **_kwargs):
            calls.append((method, path, params))
            if path == "/api/project/task/dialog":
                return {"dialog_id": 456}
            if path == "/api/dialog/msg/sendtext":
                return {"id": 99}
            raise AssertionError(path)

        argv = [
            "project_api.py", "comment", "--task-id", "123",
            "--content", "done", "--model", "gpt-test",
        ]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(project_api, "load_config", return_value={"url": "https://example.invalid"}), \
             mock.patch.object(project_api, "request_api", side_effect=request), \
             mock.patch("builtins.print"):
            self.assertEqual(project_api.main(), 0)

        self.assertEqual(calls[-1][2]["model_name"], "gpt-test")

    def test_comment_uses_model_from_environment(self):
        calls = []

        def request(_config, method, path, params, **_kwargs):
            calls.append((method, path, params))
            if path == "/api/project/task/dialog":
                return {"dialog_id": 456}
            if path == "/api/dialog/msg/sendtext":
                return {"id": 99}
            raise AssertionError(path)

        argv = ["project_api.py", "comment", "--task-id", "123", "--content", "done"]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict("os.environ", {"YEYING_AGENT_MODEL": "gpt-env"}), \
             mock.patch.object(project_api, "load_config", return_value={"url": "https://example.invalid"}), \
             mock.patch.object(project_api, "request_api", side_effect=request), \
             mock.patch("builtins.print"):
            self.assertEqual(project_api.main(), 0)

        self.assertEqual(calls[-1][2]["model_name"], "gpt-env")


if __name__ == "__main__":
    unittest.main()
