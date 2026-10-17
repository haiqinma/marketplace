import json
import hashlib
import sys
import tempfile
import unittest
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
        record = {
            "kind": "solution",
            "recorded_at": "2026-01-01T00:00:00Z",
            "sha256": "a" * 64,
            "data": {"recommendation": "A"},
        }
        with mock.patch.object(lifecycle, "load_config", return_value={"url": "https://example.invalid"}), \
             mock.patch.object(lifecycle, "request_api", side_effect=[
                 {"dialog_id": 456},
                 [],
                 {"id": 1},
             ]) as request:
            self.assertTrue(lifecycle.publish_record(state, record))
            request.side_effect = [{"dialog_id": 456}, [lifecycle.render_record_comment(state, record)]]
            self.assertFalse(lifecycle.publish_record(state, record))

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
                "missing": ["hidden context"],
                "files": [{"name": "transcript.json", "sha256": hashlib.sha256(transcript.read_bytes()).hexdigest()}],
            }
            manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
            payload = lifecycle.link_archive(state, manifest)
            self.assertEqual(payload["execution_id"], "exec-1")
            self.assertFalse(payload["complete"])
            record = lifecycle.add_record(state, "execution_archive", payload, manifest)
            self.assertEqual(record["kind"], "execution_archive")

    def test_initialize_rejects_conflicting_workspace_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".project-task.json").write_text(json.dumps({"project_id": 8, "task_id": 999}), encoding="utf-8")
            with mock.patch.object(lifecycle, "load_config", return_value={"url": "https://example.invalid"}), \
                 mock.patch.object(lifecycle, "request_api", return_value={"id": 123, "project_id": 8, "name": "task"}):
                with self.assertRaises(lifecycle.ProjectApiError):
                    lifecycle.initialize(8, 123, root, root / ".project-lifecycle.json")


if __name__ == "__main__":
    unittest.main()
