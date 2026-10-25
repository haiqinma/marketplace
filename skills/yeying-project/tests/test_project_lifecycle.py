import json
import hashlib
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_lifecycle as lifecycle  # noqa: E402


class LifecycleTest(unittest.TestCase):
    def state(self) -> dict:
        return {
            "schema": lifecycle.SCHEMA,
            "project_id": 8,
            "task_id": 123,
            "stage": "intake",
            "records": [],
            "history": [],
        }

    def record(self, state: dict, kind: str, payload: dict, root: Path) -> dict:
        source = root / f"{kind}.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        return lifecycle.add_record(state, kind, lifecycle.load_record(source), source)

    def test_stage_gates_require_analysis_approval_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.state()
            lifecycle.advance(state, "analysis")

            self.record(state, "analysis", {
                "understanding": "需求",
                "in_scope": ["功能"],
                "out_of_scope": ["重构"],
                "evidence": ["代码"],
                "constraints": ["兼容"],
                "risks": ["风险"],
            }, root)
            lifecycle.advance(state, "analysis")
            self.record(state, "solution", {
                "options": ["A", "B"],
                "comparison": {"A": "优"},
                "recommendation": "A",
                "acceptance_criteria": ["通过测试"],
                "test_plan": ["单测"],
            }, root)
            lifecycle.advance(state, "solution")
            lifecycle.advance(state, "approval")
            with self.assertRaises(lifecycle.ProjectApiError):
                lifecycle.advance(state, "implementation")
            state["approval"] = {"by": "owner", "reference": "comment:1"}
            lifecycle.advance(state, "implementation")
            self.record(state, "implementation", {
                "files": ["skill"], "decisions": ["保留 JSON 原始记录"], "status": "done",
            }, root)
            self.record(state, "verification", {
                "commands": ["test"],
                "environment": "local",
                "passed": False,
                "results": "failed",
            }, root)
            with self.assertRaises(lifecycle.ProjectApiError):
                lifecycle.advance(state, "verification")
            state["stage"] = "verification"
            lifecycle.advance(state, "implementation")
            self.assertTrue(state["history"][-1]["rollback"])

    def test_verification_requires_documentation_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.state()
            state["stage"] = "implementation"
            self.record(state, "implementation", {
                "files": ["skill"], "decisions": [], "status": "done",
            }, root)
            self.record(state, "verification", {
                "commands": ["test"], "environment": "local", "passed": True, "results": "ok",
            }, root)
            with self.assertRaisesRegex(lifecycle.ProjectApiError, "documentation"):
                lifecycle.advance(state, "verification")

            self.record(state, "documentation", {
                "paths": ["docs/README.md", "books/yeying"],
                "status": "checked",
                "updated": False,
                "no_update_reason": "本次实现不改变用户可见流程",
                "cross_project_impact": "无",
            }, root)
            lifecycle.advance(state, "verification")
            self.assertEqual(state["stage"], "verification")

    def test_record_comment_summarizes_and_collapses_raw_data(self):
        state = self.state()
        record = {
            "kind": "documentation",
            "recorded_at": "2026-01-01T00:00:00Z",
            "sha256": "a" * 64,
            "data": {
                "paths": ["docs"], "status": "checked", "updated": True,
                "no_update_reason": "", "cross_project_impact": "无",
            },
        }
        rendered = lifecycle.render_record_comment(state, record)
        self.assertIn("文档收口", rendered)
        self.assertIn("<details>", rendered)
        self.assertIn("查看结构化原始记录", rendered)

    def test_record_requires_contract_fields_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.state()
            source = root / "verification.json"
            source.write_text(json.dumps({"passed": True}), encoding="utf-8")
            with self.assertRaises(lifecycle.ProjectApiError):
                lifecycle.add_record(state, "verification", lifecycle.load_record(source), source)
            source.write_text(json.dumps({
                "commands": ["test"], "environment": "local", "passed": True, "results": "ok",
            }), encoding="utf-8")
            first = lifecycle.add_record(state, "verification", lifecycle.load_record(source), source)
            second = lifecycle.add_record(state, "verification", lifecycle.load_record(source), source)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(len(state["records"]), 1)

    def test_publish_record_is_idempotent(self):
        state = self.state()
        state["stage"] = "solution"
        state["agent"] = {
            "source_tool": "codex",
            "client_version": "1.0",
            "models": [{"id": "gpt-test", "role": "primary", "source": "host"}],
            "model_missing_reason": None,
        }
        record = {
            "kind": "solution",
            "recorded_at": "2026-01-01T00:00:00Z",
            "sha256": "a" * 64,
            "data": {"recommendation": "A"},
        }
        with mock.patch.object(lifecycle, "load_config", return_value={"url": "https://example.invalid"}), \
             mock.patch.object(lifecycle, "ensure_task_dialog_id", return_value=456) as ensure_dialog, \
             mock.patch.object(lifecycle, "request_api", side_effect=[
                 [],
                 {"id": 1},
             ]) as request:
            self.assertTrue(lifecycle.publish_record(state, record))
            ensure_dialog.assert_called_once_with({"url": "https://example.invalid"}, 123)
            sent = request.call_args_list[1].args[3]
            self.assertEqual(sent["model_name"], "gpt-test")
            request.side_effect = [[lifecycle.render_record_comment(state, record)]]
            self.assertFalse(lifecycle.publish_record(state, record))
            self.assertEqual(ensure_dialog.call_count, 2)

    def test_archive_link_validates_manifest_files_and_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.state()
            transcript = root / "transcript.json"
            transcript.write_text("{}\n", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest_payload = {
                "executionId": "exec-1",
                "projectId": 8,
                "taskId": 123,
                "complete": False,
                "sourceTool": "codex",
                "model": "gpt-test",
                "agent": {
                    "source_tool": "codex",
                    "client_version": "1.0",
                    "models": [{"id": "gpt-test", "role": "primary", "source": "host"}],
                    "model_missing_reason": None,
                },
                "missing": ["hidden context"],
                "files": [{"name": "transcript.json", "sha256": hashlib.sha256(transcript.read_bytes()).hexdigest()}],
            }
            manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
            payload = lifecycle.link_archive(state, manifest)
            self.assertEqual(payload["execution_id"], "exec-1")
            self.assertFalse(payload["complete"])
            self.assertEqual(payload["source_tool"], "codex")
            self.assertEqual(payload["model"], "gpt-test")
            self.assertEqual(payload["agent"]["models"][0]["id"], "gpt-test")
            record = lifecycle.add_record(state, "execution_archive", payload, manifest)
            self.assertEqual(record["kind"], "execution_archive")

    def test_initialize_allows_parallel_task_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".project-task-999.json").write_text(json.dumps({"project_id": 8, "task_id": 999}), encoding="utf-8")
            with mock.patch.object(lifecycle, "load_config", return_value={"url": "https://example.invalid"}), \
                 mock.patch.object(lifecycle, "request_api", return_value={"id": 123, "project_id": 8, "name": "task"}):
                state_path = lifecycle.default_state_path(root, 123)
                state = lifecycle.initialize(8, 123, root, state_path)
            self.assertEqual(state["task_id"], 123)
            self.assertTrue((root / ".project-task-123.json").is_file())
            self.assertTrue((root / ".project-task-999.json").is_file())
            self.assertEqual(state_path.name, ".project-lifecycle-123.json")

    def test_initialize_rejects_conflicting_task_specific_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / ".project-task-123.json"
            marker.write_text(json.dumps({"project_id": 8, "task_id": 999}), encoding="utf-8")
            with mock.patch.object(lifecycle, "load_config", return_value={"url": "https://example.invalid"}), \
                 mock.patch.object(lifecycle, "request_api", return_value={"id": 123, "project_id": 8, "name": "task"}):
                with self.assertRaises(lifecycle.ProjectApiError):
                    lifecycle.initialize(8, 123, root, lifecycle.default_state_path(root, 123))

    def test_create_task_params_use_config_owner_and_explicit_times(self):
        args = Namespace(
            project_id=8,
            name="task",
            column_id=None,
            content_file=None,
            owner=None,
            times='["2026-10-24 09:00", "2026-10-25 18:00"]',
            allow_unassigned=False,
            allow_unscheduled=False,
        )
        params = lifecycle.build_create_task_params(args, {"default_owner_id": 7})
        self.assertEqual(params["owner"], 7)
        self.assertEqual(params["times"], ["2026-10-24 09:00", "2026-10-25 18:00"])

    def test_create_task_params_fail_closed_without_owner_or_times(self):
        args = Namespace(
            project_id=8,
            name="task",
            column_id=None,
            content_file=None,
            owner=None,
            times=None,
            allow_unassigned=False,
            allow_unscheduled=False,
        )
        with self.assertRaisesRegex(lifecycle.ProjectApiError, "必须指定负责人"):
            lifecycle.build_create_task_params(args, {})
        args.allow_unassigned = True
        with self.assertRaisesRegex(lifecycle.ProjectApiError, "必须指定计划时间"):
            lifecycle.build_create_task_params(args, {})

    def test_create_task_params_allow_unassigned_overrides_config_owner(self):
        args = Namespace(
            project_id=8,
            name="task",
            column_id=None,
            content_file=None,
            owner=None,
            times='["2026-10-24 09:00", "2026-10-25 18:00"]',
            allow_unassigned=True,
            allow_unscheduled=False,
        )
        params = lifecycle.build_create_task_params(args, {"default_owner_id": 7})
        self.assertNotIn("owner", params)

    def test_parse_task_times_rejects_invalid_range(self):
        with self.assertRaisesRegex(lifecycle.ProjectApiError, "结束时间必须晚于开始时间"):
            lifecycle.parse_task_times('["2026-10-25 18:00", "2026-10-24 09:00"]')


if __name__ == "__main__":
    unittest.main()
