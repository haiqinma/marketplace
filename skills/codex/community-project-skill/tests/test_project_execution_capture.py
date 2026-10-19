import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_execution_capture as capture  # noqa: E402


class ExecutionCaptureTest(unittest.TestCase):
    def test_capture_deduplicates_events_and_redacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.jsonl"
            events.write_text(
                "\n".join([
                    json.dumps({"event_id": "1", "type": "user_message", "content": "开始"}),
                    json.dumps({"event_id": "1", "type": "user_message", "content": "重复"}),
                    json.dumps({"event_id": "2", "type": "tool_result", "content": {"token": "secret"}}),
                ]) + "\n",
                encoding="utf-8",
            )
            state_path = root / "state.json"
            lifecycle_path = root / "lifecycle.json"
            lifecycle_path.write_text(json.dumps({"project_id": 8, "task_id": 123, "stage": "implementation"}), encoding="utf-8")
            result = capture.capture(capture.parser().parse_args([
                "--project-id", "8", "--task-id", "123", "--source-tool", "claude",
                "--state", str(state_path), "--output-dir", str(root / "archive"),
                "--lifecycle-file", str(lifecycle_path),
                "--input-file", str(events), "--incomplete", "--missing", "hidden context",
            ]))
            self.assertEqual(result["records"], 2)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["event_ids"], ["1", "2"])
            transcript = (root / "archive" / "transcript.json").read_text(encoding="utf-8")
            self.assertIn("[REDACTED]", transcript)
            self.assertIn('"stage": "implementation"', transcript)

    def test_default_paths_are_scoped_by_task_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".project-task-214.json").write_text(
                json.dumps({"project_id": 8, "task_id": 214}), encoding="utf-8"
            )
            events = root / "events.jsonl"
            events.write_text(json.dumps({"event_id": "1", "type": "session_start"}) + "\n", encoding="utf-8")
            args = capture.parser().parse_args([
                "--binding-root", str(root), "--source-tool", "codex",
                "--input-file", str(events), "--incomplete",
            ])
            capture.capture(args)
            self.assertEqual(args.state, root.resolve() / ".project-execution-214.json")
            self.assertEqual(args.output_dir, root.resolve() / ".project-execution-214")
            self.assertTrue(args.state.is_file())
            self.assertTrue((args.output_dir / "manifest.json").is_file())

    def test_event_metadata_populates_agent_context_without_overriding_explicit_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.jsonl"
            events.write_text(
                json.dumps({
                    "event_id": "1",
                    "type": "session_start",
                    "metadata": {
                        "model": "event-model",
                        "model_provider": "provider-b",
                        "client_version": "2.0.0",
                    },
                }) + "\n",
                encoding="utf-8",
            )
            state_path = root / "state.json"
            capture.capture(capture.parser().parse_args([
                "--project-id", "8", "--task-id", "123", "--source-tool", "codex",
                "--model", "explicit-model", "--model-provider", "provider-a",
                "--state", str(state_path), "--output-dir", str(root / "archive"),
                "--input-file", str(events), "--incomplete",
            ]))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["model"], "explicit-model")
            self.assertEqual(state["agent"]["client_version"], "2.0.0")
            self.assertEqual(
                [(item["id"], item["role"]) for item in state["agent"]["models"]],
                [("explicit-model", "primary"), ("event-model", "participant")],
            )


if __name__ == "__main__":
    unittest.main()
