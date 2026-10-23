#!/usr/bin/env python3
"""Run the YeYing Ops analysis and Project audit reconciliation workflow."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import analyze_errors
import project_workflow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("run", "analyze", "sync"), default="run")
    parser.add_argument("--config", type=Path, default=analyze_errors.default_config_path())
    parser.add_argument("--date")
    parser.add_argument("--module", action="append")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def analyzer_arguments(args: argparse.Namespace) -> list[str]:
    values = ["--config", str(args.config), "--no-lock"]
    if args.date:
        values.extend(["--date", args.date])
    for module in args.module or []:
        values.extend(["--module", module])
    if args.dry_run:
        values.append("--dry-run")
    return values


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = analyze_errors.load_config(args.config)
        target_date = analyze_errors.local_date(config, args.date)
        state_db = analyze_errors.config_path(
            config, "state_db", Path("~/.yeying/skills/ops/runtime/state.db").expanduser()
        )
        lock_file = analyze_errors.config_path(config, "lock_file", state_db.with_suffix(".lock"))
        output: dict[str, object] = {"command": args.command, "date": target_date.isoformat()}
        analysis_status = 0
        sync_error = ""
        with analyze_errors.exclusive_lock(lock_file):
            if args.command in {"run", "analyze"}:
                analysis_status, analysis_output = analyze_errors.analyze(config, analyze_errors.parse_args(analyzer_arguments(args)))
                output["analysis"] = analysis_output
            if args.command in {"run", "sync"} and not args.dry_run:
                try:
                    output["project"] = project_workflow.sync(config, target_date, False)
                except (OSError, ValueError, sqlite3.Error, subprocess.TimeoutExpired, project_workflow.ProjectWorkflowError) as exc:
                    sync_error = str(exc)
                    output["project"] = {"enabled": True, "error": sync_error, "pending_retry": True}
            elif args.command in {"run", "sync"}:
                output["project"] = project_workflow.sync(config, target_date, True)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        project_required = bool(project_workflow.project_settings(config).get("required", False))
        if sync_error and project_required:
            return 2
        return analysis_status
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
