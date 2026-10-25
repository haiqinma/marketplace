import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_api  # noqa: E402


class ProjectApiTaskCreateTest(unittest.TestCase):
    def test_task_create_omits_owner_for_server_side_token_default(self):
        calls = []

        def request(_config, method, path, params, **_kwargs):
            calls.append((method, path, params))
            return {"id": 123}

        argv = ["project_api.py", "task-create", "--project-id", "8", "--name", "task"]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(project_api, "load_config", return_value={"url": "https://example.invalid"}), \
             mock.patch.object(project_api, "request_api", side_effect=request), \
             mock.patch("builtins.print"):
            self.assertEqual(project_api.main(), 0)

        self.assertNotIn("owner", calls[0][2])

    def test_task_create_can_explicitly_remain_unassigned(self):
        calls = []

        def request(_config, method, path, params, **_kwargs):
            calls.append((method, path, params))
            return {"id": 123}

        argv = ["project_api.py", "task-create", "--project-id", "8", "--name", "task", "--unassigned"]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(project_api, "load_config", return_value={"url": "https://example.invalid"}), \
             mock.patch.object(project_api, "request_api", side_effect=request), \
             mock.patch("builtins.print"):
            self.assertEqual(project_api.main(), 0)

        self.assertEqual(calls[0][2]["owner"], [])

    def test_task_create_preserves_explicit_owner(self):
        calls = []

        def request(_config, method, path, params, **_kwargs):
            calls.append((method, path, params))
            return {"id": 123}

        argv = ["project_api.py", "task-create", "--project-id", "8", "--name", "task", "--owner", "9"]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(project_api, "load_config", return_value={"url": "https://example.invalid"}), \
             mock.patch.object(project_api, "request_api", side_effect=request), \
             mock.patch("builtins.print"):
            self.assertEqual(project_api.main(), 0)

        self.assertEqual(calls[0][2]["owner"], 9)


if __name__ == "__main__":
    unittest.main()
