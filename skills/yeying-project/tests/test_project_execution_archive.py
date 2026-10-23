import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_execution_archive as archive  # noqa: E402
import project_api  # noqa: E402


class ExecutionArchiveTest(unittest.TestCase):
    def test_task_dialog_id_creates_or_reuses_dialog(self):
        with mock.patch.object(project_api, "request_api", return_value={"dialog_id": 456}) as request:
            self.assertEqual(archive.task_dialog_id({}, 123), 456)

        request.assert_called_once_with(
            {}, "GET", "/api/project/task/dialog", {"task_id": 123}
        )

    def test_default_paths_are_scoped_by_task_id(self):
        root = Path("/tmp/workspace")
        self.assertEqual(
            archive.default_execution_state_path(root, 214),
            root / ".project-execution-214.json",
        )
        self.assertEqual(
            archive.default_execution_output_dir(root, 214),
            root / ".project-execution-214",
        )

    def test_redaction_keeps_normal_field_names(self):
        value = archive.redact({
            "risks": ["保留这段风险"],
            "tasks": ["保留这段任务"],
            "secret_key": "hidden",
            "accessToken": "hidden-too",
        })
        self.assertEqual(value["risks"], ["保留这段风险"])
        self.assertEqual(value["tasks"], ["保留这段任务"])
        self.assertEqual(value["secret_key"], archive.REDACTED)
        self.assertEqual(value["accessToken"], archive.REDACTED)

    def test_finalize_redacts_and_records_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            archive_dir = root / "archive"
            state = {
                "schema": archive.SCHEMA,
                "project_id": 8,
                "task_id": 123,
                "execution_id": "exec-test-001",
                "source_tool": "test",
                "model": "test-model",
                "started_at": archive.now(),
                "status": "running",
                "complete": False,
                "missing": ["hidden context"],
                "records": [{"role": "tool", "content": {"token": "secret", "stdout": "ok"}}],
                "attachments": [],
                "lifecycle": {"stage": "verification", "task_id": 123},
                "repository": {"name": "project"},
                "verification": [{"passed": True}],
                "output_dir": str(archive_dir),
            }
            state = archive.finalize_state(state, archive_dir)
            archive.write_json(state_path, state)
            transcript_md = (archive_dir / "transcript.md").read_text(encoding="utf-8")
            self.assertIn("原始记录默认折叠", transcript_md)
            self.assertIn("<details>", transcript_md)
            self.assertNotIn('details open', transcript_md)
            transcript = (archive_dir / "transcript.json").read_text(encoding="utf-8")
            self.assertNotIn("secret", transcript)
            self.assertIn("[REDACTED]", transcript)
            manifest = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["complete"])
            self.assertEqual(manifest["taskId"], 123)
            self.assertEqual(manifest["lifecycleStage"], "verification")
            self.assertEqual(manifest["agent"]["models"][0]["id"], "test-model")
            transcript_data = json.loads((archive_dir / "transcript.json").read_text(encoding="utf-8"))
            self.assertEqual(transcript_data["lifecycle"]["stage"], "verification")
            for item in manifest["files"]:
                self.assertEqual(item["sha256"], hashlib.sha256((archive_dir / item["name"]).read_bytes()).hexdigest())

    def test_finalize_records_reason_when_model_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir = Path(tmp) / "archive"
            state = {
                "schema": archive.SCHEMA,
                "project_id": 8,
                "task_id": 123,
                "execution_id": "exec-no-model",
                "source_tool": "codex",
                "model": None,
                "started_at": archive.now(),
                "status": "running",
                "complete": False,
                "missing": ["hidden context"],
                "records": [],
                "attachments": [],
            }

            with mock.patch.dict("os.environ", {"YEYING_AGENT_MODEL": "ambient-model"}):
                archive.finalize_state(state, archive_dir)

            manifest = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["agent"]["models"], [])
            self.assertEqual(
                manifest["agent"]["model_missing_reason"],
                "host did not expose the active model",
            )

    def test_finalized_archive_rejects_a_new_model(self):
        state = {
            "schema": archive.SCHEMA,
            "source_tool": "codex",
            "model": "gpt-primary",
            "agent": {
                "source_tool": "codex",
                "client_version": None,
                "models": [{"id": "gpt-primary", "role": "primary", "source": "argument"}],
                "model_missing_reason": None,
            },
            "finalized_at": archive.now(),
        }
        candidate = {
            "source_tool": "codex",
            "client_version": None,
            "models": [{"id": "gpt-other", "role": "participant", "source": "event"}],
            "model_missing_reason": None,
        }

        with self.assertRaisesRegex(ValueError, "执行归档已冻结"):
            archive.merge_state_agent_context(state, candidate, locked=True)

    def test_publish_reuses_files_and_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            archive_dir = root / "archive"
            state = {
                "schema": archive.SCHEMA,
                "project_id": 8,
                "task_id": 123,
                "execution_id": "exec-test-002",
                "source_tool": "test",
                "model": "test-model",
                "started_at": archive.now(),
                "status": "succeeded",
                "complete": True,
                "missing": [],
                "records": [],
                "attachments": [],
                "output_dir": str(archive_dir),
            }
            archive.finalize_state(state, archive_dir)
            archive.write_json(state_path, state)
            remote: dict[str, dict] = {}
            bodies: dict[int, bytes] = {}
            comments: list[str] = []
            sent_params: list[dict] = []
            next_id = [10]

            def fake_upload(_api, _path, params, _field, file_path):
                self.assertEqual(params["dialog_id"], 456)
                file_id = next_id[0]
                next_id[0] += 1
                remote[file_path.name] = {"id": file_id, "name": file_path.name}
                bodies[file_id] = file_path.read_bytes()
                return {"id": file_id}

            def fake_request(_api, method, path, params, *, raw=False):
                if path == "/api/dialog/msg/list":
                    return comments
                if path == "/api/dialog/msg/sendtext":
                    sent_params.append(dict(params))
                    comments.append(params["text"])
                    return {"id": 99}
                if path == "/api/project/task/filedown" and raw:
                    return bodies[int(params["file_id"])]
                raise AssertionError((method, path, params))

            with mock.patch.object(archive, "load_config", return_value={"url": "https://example.invalid"}), \
                 mock.patch.object(archive, "existing_task_files", side_effect=lambda _api, _task: remote), \
                 mock.patch.object(archive, "task_dialog_id", return_value=456), \
                 mock.patch.object(archive, "request_upload", side_effect=fake_upload), \
                 mock.patch.object(archive, "request_api", side_effect=fake_request):
                first = archive.publish(state_path, archive.load_state(state_path))
                second = archive.publish(state_path, archive.load_state(state_path))

            self.assertEqual(len(first["files"]), 3)
            self.assertTrue(all(item["reused"] is False for item in first["files"]))
            self.assertTrue(all(item["reused"] is True for item in second["files"]))
            self.assertEqual(len(comments), 1)
            self.assertIn("主模型：`test-model`", comments[0])
            self.assertEqual(sent_params[0]["model_name"], "test-model")


if __name__ == "__main__":
    unittest.main()
