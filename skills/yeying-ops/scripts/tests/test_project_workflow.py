import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
import analyze_errors
import project_workflow


class FakeProjectClient:
    def __init__(self):
        self.created = []
        self.comments = []
        self.reopened = []
        self.task_list = []
        self.task_value = None

    def tasks(self, project_id, keyword):
        return self.task_list

    def create_task(self, project_id, name, content, column=None, owner=None):
        task = {"id": 100 + len(self.created), "name": name}
        self.created.append((project_id, name, content, column, owner))
        return task

    def comment(self, task_id, content):
        self.comments.append((task_id, content))
        return {"id": len(self.comments)}

    def task(self, task_id):
        return self.task_value

    def reopen(self, task_id):
        self.reopened.append(task_id)
        return {"id": task_id}


def finding_result():
    return {
        "summary": "router failed", "severity": "P1",
        "root_cause": {"category": "likely", "explanation": "bad configuration"},
        "confidence": 0.8, "evidence": ["sanitized evidence"], "impact": ["requests failed"],
        "recommended_actions": ["review config"], "missing_information": [],
        "dedup_fingerprint": "a" * 64, "occurrences": 3, "first_seen": "a", "last_seen": "b",
        "execution": {"model": {"provider": "openai", "model": "gpt-test"}},
    }


class ProjectWorkflowTests(unittest.TestCase):
    def test_valid_decision_requires_matching_human_identity(self):
        value = {"schema": project_workflow.DECISION_SCHEMA, "finding_id": "abc", "decision": "monitor", "approved_by": {"user_id": 7, "name": "auditor"}, "approved_at": "2026-10-22T10:00:00+08:00"}
        self.assertIsNotNone(project_workflow.validate_decision(value, "abc", 7, {7}))
        self.assertIsNone(project_workflow.validate_decision(value, "abc", 8, {7}))
        self.assertIsNone(project_workflow.validate_decision(value, "other", 7, {7}))

    def test_latest_decision_ignores_unapproved_sender(self):
        decision = {"schema": project_workflow.DECISION_SCHEMA, "finding_id": "abc", "decision": "monitor", "approved_by": {"user_id": 9}, "approved_at": "2026-10-22T10:00:00+08:00"}
        task = {"task": {"owner": 7}, "messages": {"list": [{"id": 1, "userid": 9, "type": "text", "msg": {"text": f"```json\n{json.dumps(decision)}\n```"}}]}}
        self.assertIsNone(project_workflow.latest_decision(task, "abc", {"allowed_auditor_ids": [7]}))

    def test_latest_decision_ignores_malformed_identity_and_uses_newest_comment(self):
        malformed = {"schema": project_workflow.DECISION_SCHEMA, "finding_id": "abc", "decision": "monitor", "approved_by": {"user_id": "invalid"}, "approved_at": "2026-10-22T09:00:00+08:00"}
        older = {"schema": project_workflow.DECISION_SCHEMA, "finding_id": "abc", "decision": "monitor", "approved_by": {"user_id": 7}, "approved_at": "2026-10-22T10:00:00+08:00"}
        newer = {"schema": project_workflow.DECISION_SCHEMA, "finding_id": "abc", "decision": "false_positive", "approved_by": {"user_id": 7}, "approved_at": "2026-10-22T11:00:00+08:00"}
        task = {"task": {"owner": 7}, "messages": {"list": [
            {"id": 3, "userid": 7, "type": "text", "msg": {"text": json.dumps(malformed)}},
            {"id": 1, "userid": 7, "type": "text", "msg": {"text": json.dumps(older)}},
            {"id": 2, "userid": 7, "type": "text", "msg": {"text": json.dumps(newer)}},
        ]}}
        selected = project_workflow.latest_decision(task, "abc", {"allowed_auditor_ids": [7]})
        self.assertEqual(selected[0]["decision"], "false_positive")
        self.assertEqual(selected[1], 2)

    def test_existing_audit_task_reuses_completed_audit_not_remediation(self):
        client = FakeProjectClient()
        client.task_list = [
            {"id": 10, "name": "[生产问题修复] fix [aaaaaaaaaaaa]", "complete_at": None},
            {"id": 11, "name": "[生产问题审计][P1][router] failure [aaaaaaaaaaaa]", "complete_at": "2026-10-22"},
        ]
        self.assertEqual(project_workflow.existing_audit_task(client, 8, "a" * 64), 11)

    def test_ensure_audit_task_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            client = FakeProjectClient()
            settings = {"project_id": 8, "audit_column": 13, "audit_owner_id": 1}
            result = finding_result()
            item = {"finding_id": "a" * 64, "module": "router"}
            first, _ = project_workflow.ensure_audit_task(connection, client, settings, dt.date(2026, 10, 22), item, result, False)
            connection.commit()
            second, _ = project_workflow.ensure_audit_task(connection, client, settings, dt.date(2026, 10, 22), item, result, False)
            self.assertEqual(first, second)
            self.assertEqual(len(client.created), 1)

    def test_recurring_finding_reopens_completed_audit_task(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            client = FakeProjectClient()
            client.task_value = {"task": {"complete_at": "2026-10-21"}}
            settings = {"project_id": 8, "audit_column": 13, "audit_owner_id": 1}
            result = finding_result()
            item = {"finding_id": "a" * 64, "module": "router"}
            project_workflow.save_link(connection, "a" * 64, "router", 44, [], "monitor", None, "", "old")
            connection.commit()
            task_id, status = project_workflow.ensure_audit_task(connection, client, settings, dt.date(2026, 10, 22), item, result, False)
            self.assertEqual((task_id, status), (44, "audit_task_ready"))
            self.assertEqual(client.reopened, [44])
            self.assertEqual(len(client.comments), 1)

    def test_reconcile_remediate_creates_task_once(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            finding_id = "a" * 64
            project_workflow.save_link(connection, finding_id, "router", 44, [], "awaiting_audit", None, "", "digest")
            connection.commit()
            decision = {
                "schema": project_workflow.DECISION_SCHEMA, "finding_id": finding_id, "decision": "remediate",
                "approved_by": {"user_id": 7, "name": "auditor"}, "approved_at": "2026-10-22T10:00:00+08:00",
                "summary": "fix router", "remediation_scope": ["fix config"],
                "target_repositories": ["yeying-community/router"], "acceptance_criteria": ["tests pass"], "constraints": [],
            }
            client = FakeProjectClient()
            client.task_value = {"task": {"owner": 7}, "messages": {"list": [{"id": 55, "userid": 7, "type": "text", "msg": {"text": f"```json\n{json.dumps(decision)}\n```"}}]}}
            settings = {"project_id": 8, "allowed_auditor_ids": [7], "remediation_column": 13}
            row = connection.execute("SELECT * FROM project_links WHERE finding_id = ?", (finding_id,)).fetchone()
            result = project_workflow.reconcile_link(connection, client, settings, row, False)
            connection.commit()
            self.assertEqual(result["status"], "remediation_task_created")
            self.assertEqual(len(client.created), 1)
            row = connection.execute("SELECT * FROM project_links WHERE finding_id = ?", (finding_id,)).fetchone()
            project_workflow.reconcile_link(connection, client, settings, row, False)
            self.assertEqual(len(client.created), 1)

    def test_reconcile_remediate_reuses_remote_task_after_interrupted_save(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = analyze_errors.open_database(Path(directory) / "state.db")
            finding_id = "a" * 64
            project_workflow.save_link(connection, finding_id, "router", 44, [], "awaiting_audit", None, "", "digest")
            connection.commit()
            decision = {
                "schema": project_workflow.DECISION_SCHEMA, "finding_id": finding_id, "decision": "remediate",
                "approved_by": {"user_id": 7, "name": "auditor"}, "approved_at": "2026-10-22T10:00:00+08:00",
                "summary": "fix router", "remediation_scope": ["fix config"],
                "target_repositories": ["yeying-community/router"], "acceptance_criteria": ["tests pass"], "constraints": [],
            }
            client = FakeProjectClient()
            client.task_value = {"task": {"owner": 7}, "messages": {"list": [{"id": 55, "userid": 7, "type": "text", "msg": {"text": json.dumps(decision)}}]}}
            client.task_list = [{"id": 88, "name": "[生产问题修复] fix router [aaaaaaaaaaaa]"}]
            settings = {"project_id": 8, "allowed_auditor_ids": [7], "remediation_column": 13}
            row = connection.execute("SELECT * FROM project_links WHERE finding_id = ?", (finding_id,)).fetchone()
            result = project_workflow.reconcile_link(connection, client, settings, row, False)
            self.assertEqual(result["status"], "remediation_task_created")
            self.assertEqual(result["remediation_task_ids"], [88])
            self.assertEqual(client.created, [])


if __name__ == "__main__":
    unittest.main()
