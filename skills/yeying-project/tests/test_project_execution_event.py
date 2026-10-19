import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_execution_event as event  # noqa: E402


class ExecutionEventTest(unittest.TestCase):
    def test_append_is_restart_safe_and_finalize_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = event.parser().parse_args([
                "--project-id", "8", "--task-id", "123", "--source-tool", "claude",
                "--state", str(root / "state.json"), "--output-dir", str(root / "archive"),
            ])
            payload = {"event_id": "evt-1", "type": "user_message", "content": "hello"}
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                self.assertTrue(event.append_event(args)["appended"])
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                self.assertFalse(event.append_event(args)["appended"])
            args.finalize = True
            args.missing = ["hidden context"]
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"event_id": "evt-2", "type": "session_end"}))):
                result = event.append_event(args)
            self.assertTrue(result["finalized"])
            self.assertTrue((root / "archive" / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
