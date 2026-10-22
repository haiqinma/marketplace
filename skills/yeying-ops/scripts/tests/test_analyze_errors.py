import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
import analyze_errors


def valid_result():
    return {
        "summary": "summary",
        "severity": "P2",
        "root_cause": {"category": "unknown", "explanation": "not enough evidence"},
        "confidence": 0.1,
        "evidence": [],
        "impact": [],
        "recommended_actions": [],
        "missing_information": ["more logs"],
        "dedup_fingerprint": "model-value",
        "occurrences": 1,
        "first_seen": "model-value",
        "last_seen": "model-value",
    }


class AnalyzerTests(unittest.TestCase):
    def test_sanitize_for_model_removes_sensitive_values(self):
        value = (
            "2026-10-21 10:11:12 ERROR /opt/deploy/router/config.yaml "
            "email=user@example.com ip=10.0.0.8 token=sk-secret123 "
            "request id: abc123 url=https://user:pass@example.com/a?access_token=secret"
        )
        sanitized = analyze_errors.sanitize_for_model(value)
        for secret in ("2026-10-21", "/opt/deploy", "user@example.com", "10.0.0.8", "sk-secret123", "abc123", "pass", "access_token=secret"):
            self.assertNotIn(secret, sanitized)
        self.assertIn("[PATH]", sanitized)
        self.assertIn("[EMAIL_REDACTED]", sanitized)

    def test_normalize_redacts_ids_and_numbers(self):
        normalized = analyze_errors.normalize_error("ERROR request_id=abc123 user=42")
        self.assertNotIn("abc123", normalized)
        self.assertIn("[id_redacted]", normalized)
        self.assertIn("[n]", normalized)

    def test_read_groups_filters_date_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "error.log"
            log.write_text(
                "2026-10-20 23:59:59 ERROR old failure 1\n"
                "2026-10-21 23:01:00 ERROR failure 42\n"
                "2026-10-21 23:02:00 ERROR failure 43\n",
                encoding="utf-8",
            )
            groups = analyze_errors.read_error_groups("router", log, dt.date(2026, 10, 21), ZoneInfo("Asia/Shanghai"), 3, 4000)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].occurrences, 2)

    def test_read_log_chunk_keeps_incomplete_line_for_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "error.log"
            log.write_bytes(b"ERROR complete\nERROR incomplete")
            lines, offset, _ = analyze_errors.read_log_chunk(log, 0)
            self.assertEqual(lines, ["ERROR complete"])
            self.assertEqual(offset, len(b"ERROR complete\n"))
            with log.open("ab") as stream:
                stream.write(b" now\n")
            lines, next_offset, _ = analyze_errors.read_log_chunk(log, offset)
            self.assertEqual(lines, ["ERROR incomplete now"])
            self.assertGreater(next_offset, offset)

    def test_discover_active_or_highest_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "router-v0.0.9-aaaaaaa").mkdir()
            (root / "router-v0.0.10-bbbbbbb").mkdir()
            self.assertEqual(analyze_errors.discover_deploy_dir(root, "router").name, "router-v0.0.10-bbbbbbb")
            (root / "router").symlink_to(root / "router-v0.0.9-aaaaaaa", target_is_directory=True)
            self.assertEqual(analyze_errors.discover_deploy_dir(root, "router").name, "router-v0.0.9-aaaaaaa")

    def test_config_paths_are_relative_to_config_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_file = root / "config.json"
            config_file.write_text('{"modules_file":"conf/modules.conf"}', encoding="utf-8")
            config = analyze_errors.load_config(config_file)
            self.assertEqual(analyze_errors.config_path(config, "modules_file", Path("x")), (root / "conf/modules.conf").resolve())

    def test_observations_survive_cursor_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            date = dt.date(2026, 10, 21)
            group = analyze_errors.ErrorGroup("router", "abc", "error", ("error",), 2, "a", "b")
            analyze_errors.store_observations(connection, date, [group], 3)
            connection.commit()
            self.assertEqual(analyze_errors.observation_groups(connection, date, "router"), [group])

    def test_success_is_reanalyzed_on_new_date(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            group = analyze_errors.ErrorGroup("router", "abc", "error", ("error",), 1, "a", "b")
            analyze_errors.upsert_group(connection, group, "success", target_date=dt.date(2026, 10, 20), category="confirmed")
            connection.commit()
            self.assertFalse(analyze_errors.should_analyze(connection, group, 0, dt.date(2026, 10, 20)))
            self.assertTrue(analyze_errors.should_analyze(connection, group, 0, dt.date(2026, 10, 21)))

    def test_new_occurrence_same_day_is_reanalyzed(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            old = analyze_errors.ErrorGroup("router", "abc", "error", ("error",), 1, "a", "b")
            new = analyze_errors.ErrorGroup("router", "abc", "error", ("error",), 2, "a", "c")
            date = dt.date(2026, 10, 21)
            analyze_errors.upsert_group(connection, old, "success", target_date=date, category="confirmed")
            connection.commit()
            self.assertTrue(analyze_errors.should_analyze(connection, new, 0, date))

    def test_already_analyzed_state_keeps_result_for_project_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            group = analyze_errors.ErrorGroup("router", "abc", "error", ("error",), 1, "a", "b")
            analyze_errors.upsert_group(connection, group, "success", result_path="/tmp/result.json", target_date=dt.date(2026, 10, 21), category="likely")
            connection.commit()
            state = analyze_errors.finding_state(connection, "abc")
            self.assertEqual(state["result_path"], "/tmp/result.json")
            self.assertEqual(state["root_cause_category"], "likely")

    def test_validate_result_adds_trusted_group_metadata(self):
        group = analyze_errors.ErrorGroup("router", "abc", "error", ("error",), 2, "a", "b")
        result = analyze_errors.validate_result(valid_result(), group)
        self.assertEqual(result["dedup_fingerprint"], "abc")
        self.assertEqual(result["occurrences"], 2)

    def test_validate_result_rejects_invalid_nested_type(self):
        group = analyze_errors.ErrorGroup("router", "abc", "error", ("error",), 1, "a", "b")
        value = valid_result()
        value["root_cause"] = "unknown"
        with self.assertRaises(ValueError):
            analyze_errors.validate_result(value, group)

    def test_write_summary_handles_missing_module(self):
        with tempfile.TemporaryDirectory() as directory:
            analyze_errors.write_summary(Path(directory), dt.date(2026, 10, 21), [{"module": "missing", "status": "missing_deploy_dir", "occurrences": 0}])
            self.assertTrue((Path(directory) / "2026-10-21" / "summary.md").is_file())

    def test_nonblocking_lock_rejects_second_holder(self):
        if analyze_errors.fcntl is None:
            self.skipTest("fcntl unavailable")
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "ops.lock"
            with analyze_errors.exclusive_lock(lock):
                with self.assertRaises(RuntimeError):
                    with analyze_errors.exclusive_lock(lock):
                        pass


if __name__ == "__main__":
    unittest.main()
