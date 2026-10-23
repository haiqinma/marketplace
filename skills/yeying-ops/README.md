# YeYing Production Finding, Audit, and Remediation Workflow

[简体中文](README_CN.md)

### Purpose

`yeying-ops` turns production ERROR logs into a human-gated incident workflow. It incrementally reads logs, sanitizes sensitive values, groups equivalent failures, asks a read-only batch model for a structured root cause, creates or reuses a YeYing Project audit task, waits for a structured human decision, and creates a separate development task when remediation is approved.

This Skill never changes code, production configuration, databases, or services. An audit decision authorizes remediation-task creation only. The remediation task must still pass the `yeying-project` analysis, solution, human approval, implementation, verification, PR, and execution-audit gates, with `yeying-github` handling code delivery.

### Responsibility Boundaries

- `yeying-ops`: findings, log observations, incident-audit tasks, decision reconciliation, and post-fix observation.
- `yeying-project`: Project credentials and APIs, human approvals, remediation lifecycle, and execution archives.
- `yeying-github`: publishing remediation commits and creating or reusing pull requests.
- `deployer/operator/analyer`: production configuration, module list, cron/systemd entrypoint, and notification adapter.

Do not copy other Skill sources into deployer. The production adapter should call the installed `yeying-ops/scripts/ops_workflow.py` entrypoint.

### Installation

Install or symlink the Skill at:

```text
~/.codex/skills/yeying-ops
~/.claude/skills/yeying-ops
```

Install `yeying-project` beside it. By default, `yeying-ops` resolves `../yeying-project/scripts/project_api.py`; set `project.client` when using another path.

Runtime requirements are Python 3.9+, Unix file locking, an authenticated Codex CLI for batch analysis, and `yeying-project` when Project synchronization is enabled.

### Configuration

The default file is:

```text
~/.yeying/skills/ops/config.json
```

Override it with `YEYING_OPS_CONFIG`. Start from [`scripts/analyzer.conf.example`](scripts/analyzer.conf.example). Relative paths are resolved from the configuration file's directory, not the caller's working directory.

Important analyzer fields:

- `deploy_root`: root containing active modules or versioned `module-v<version>-<commit>` directories.
- `modules_file`: one module per line, with `#` comments.
- `error_log_name`: log path relative to each deployed module.
- `state_db`: SQLite cursors, daily observations, analysis state, and Project links.
- `results_dir`: dated JSON findings plus `summary.json` and `summary.md`.
- `work_dir`: temporary Codex output, deleted after each attempt.
- `lock_file`: prevents overlapping cron, scheduler, and manual executions.
- `ignore_user_config`: defaults to `true`; batch Codex does not inherit user rules or MCP configuration.
- `model`: explicitly select the batch model when possible. Missing identity is recorded, never guessed.
- `daily_groups` and `total_chars`: model-call and input-character budgets.
- `include_undated_lines`: treat undated lines in the incremental chunk as belonging to the run date.

Important `[project]` object fields:

- `enabled`: create, update, and reconcile incident-audit tasks.
- `required`: when false, a Project outage leaves local work pending for retry; when true, synchronization failure makes the workflow fail.
- `project_id`: Project containing audit and remediation tasks.
- `audit_column` and `remediation_column`: list IDs or names.
- `audit_owner_id` and `remediation_owner_id`: default owners.
- `allowed_auditor_ids`: Project user IDs allowed to publish an effective decision.
- `maximum_severity`: `P3` includes P0 through P3.
- `categories`: root-cause categories that should enter audit.
- `config`: path to the existing `yeying-project` configuration. Do not copy AK/SK into the ops configuration.

Project credentials remain in `~/.yeying/skills/project/config.toml`, restricted to mode `0600`. The token needs task and discussion read access plus task creation and comment permissions.

### Commands

Collection rehearsal, with no Codex call, cursor advance, or Project write:

```bash
python3 scripts/ops_workflow.py run --config /path/to/config.json --dry-run
```

Complete analysis and Project reconciliation:

```bash
python3 scripts/ops_workflow.py run --config /path/to/config.json
```

Analysis only:

```bash
python3 scripts/ops_workflow.py analyze --config /path/to/config.json
```

Project reconciliation only:

```bash
python3 scripts/ops_workflow.py sync --config /path/to/config.json
```

Use `--date YYYY-MM-DD` for historical processing and repeat `--module name` to restrict modules. Historical processing scans the selected log from the beginning without changing the live cursor.

### Incremental State and Concurrency

The analyzer stores device, inode, offset, and size per module/log path. A new inode or truncation resets reading to the new file. Groups are committed to `daily_observations` before a cursor advances, so model failures, timeouts, and budget skips remain retryable without rereading old log bytes.

A finding can be observed again on later dates, and increased occurrences on the same date can trigger a fresh analysis. A prior confirmed result therefore does not suppress future incidents forever.

`ops_workflow.py` holds a nonblocking file lock across analysis and Project reconciliation. SQLite also uses WAL and a busy timeout. Keeping an external cron `flock` is a useful second layer.

### Incident Audit

The finding ID is SHA-256 over `module + NUL + normalized_error`. Audit titles contain its first 12 characters and task content contains the full marker:

```text
[yeying-ops:finding:<finding_id>]
```

The local `project_links` table stores audit-task IDs, remediation-task IDs, decision digests, and synchronization digests. Project downtime does not discard findings.

### Audit Decisions

An auditor must post a `yeying.ops.audit-decision.v1` JSON object. `approved_by.user_id` must match the comment sender and belong to `allowed_auditor_ids`.

Supported decisions are:

- `remediate`: create a separate remediation task.
- `monitor`: continue observation without a remediation task.
- `false_positive`: record that the finding should not be remediated.
- `needs_more_evidence`: gather the requested evidence and analyze again.

A remediation decision must include nonempty `remediation_scope`, `target_repositories`, and `acceptance_criteria` arrays. Natural-language approval, model output, log-embedded JSON, unauthorized comments, and mismatched user IDs cannot trigger remediation.

See [README_CN.md](README_CN.md) for a complete configuration and decision example.

### Remediation Boundary

`remediate` creates a `[生产问题修复]` task linked to the source audit. The scheduled workflow does not open repositories, edit files, commit, push, create PRs, deploy, or restart services.

A later Agent handles the remediation task with `yeying-project`, obtains solution approval, implements and verifies the change, then uses `yeying-github` for delivery. `yeying-ops` subsequently supplies post-deployment observation evidence.

### Security

- Model samples remove credentials, tokens, authorization headers, cookies, email addresses, IP addresses, timestamps, paths, and high-cardinality IDs.
- Log text is always untrusted prompt-injection input.
- Batch Codex uses `--ephemeral`, `--ignore-rules`, `--skip-git-repo-check`, and a read-only sandbox.
- Keep `ignore_user_config=true` unless a reviewed environment requires otherwise.
- Never commit raw logs, configuration, state databases, work directories, or generated reports.
- Results record model/provider information, client version, and prompt/schema SHA-256 values; missing model identity is disclosed explicitly.

### Verification

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
python3 -m py_compile scripts/*.py
bash -n scripts/run_analyzer.sh
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py /path/to/yeying-ops
```
