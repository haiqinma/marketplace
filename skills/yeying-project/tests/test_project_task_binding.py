import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from project_task_binding import TaskBindingError, resolve_binding  # noqa: E402


class TaskBindingTest(unittest.TestCase):
    def test_nearest_marker_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "repo" / "src"
            work.mkdir(parents=True)
            (root / "repo" / ".project-task-123.json").write_text(
                json.dumps({"project_id": 8, "task_id": 123}), encoding="utf-8"
            )
            binding = resolve_binding(start_dir=work)
            self.assertEqual(binding["project_id"], 8)
            self.assertEqual(binding["task_id"], 123)

    def test_explicit_values_override_environment(self):
        with mock.patch.dict(os.environ, {"YEYING_PROJECT_ID": "9", "YEYING_PROJECT_TASK_ID": "999"}):
            binding = resolve_binding(8, 123)
        self.assertEqual(binding["source"], "arguments")
        self.assertEqual(binding["task_id"], 123)

    def test_missing_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"YEYING_PROJECT_ID": "", "YEYING_PROJECT_TASK_ID": ""}, clear=False
        ):
            with self.assertRaises(TaskBindingError):
                resolve_binding(start_dir=Path(tmp))

    def test_multiple_markers_require_explicit_task(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"YEYING_PROJECT_ID": "", "YEYING_PROJECT_TASK_ID": ""}, clear=False
        ):
            root = Path(tmp)
            for task_id in (123, 214):
                (root / f".project-task-{task_id}.json").write_text(
                    json.dumps({"project_id": 8, "task_id": task_id}), encoding="utf-8"
                )
            with self.assertRaisesRegex(TaskBindingError, "多个 Project 任务绑定"):
                resolve_binding(start_dir=root)

    def test_explicit_task_selects_matching_marker(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"YEYING_PROJECT_ID": "", "YEYING_PROJECT_TASK_ID": ""}, clear=False
        ):
            root = Path(tmp)
            for project_id, task_id in ((8, 123), (9, 214)):
                (root / f".project-task-{task_id}.json").write_text(
                    json.dumps({"project_id": project_id, "task_id": task_id}), encoding="utf-8"
                )
            binding = resolve_binding(task_id=214, start_dir=root)
            self.assertEqual(binding["project_id"], 9)
            self.assertEqual(binding["task_id"], 214)

    def test_marker_filename_must_match_task_id(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"YEYING_PROJECT_ID": "", "YEYING_PROJECT_TASK_ID": ""}, clear=False
        ):
            root = Path(tmp)
            (root / ".project-task-214.json").write_text(
                json.dumps({"project_id": 8, "task_id": 123}), encoding="utf-8"
            )
            with self.assertRaisesRegex(TaskBindingError, "文件名与 task_id 不一致"):
                resolve_binding(start_dir=root)


if __name__ == "__main__":
    unittest.main()
