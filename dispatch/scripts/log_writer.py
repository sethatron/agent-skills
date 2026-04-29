#!/usr/bin/env python3
"""
Structured log and artifact writer for dispatch.

All writes are atomic (temp file -> rename). task.yaml and session.yaml
are DERIVED from dispatch.db, never source of truth.

Usage (CLI):
    python scripts/log_writer.py session --session-id <id>
    python scripts/log_writer.py tasks --date 2026-04-01
    python scripts/log_writer.py carry-forward --session-id <id>
    python scripts/log_writer.py task-log --task PLAT-1234

Usage (module):
    from log_writer import LogWriter
    writer = LogWriter(store)
    writer.write_task_yaml()
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATE_ROOT = Path(os.path.expanduser("~/.zsh/dispatch"))

try:
    import yaml
except ImportError:
    yaml = None

TASK_LOG_MAX_LINES = 500


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp, str(path))
    except Exception:
        os.unlink(tmp)
        raise


def _dump_yaml(data):
    if yaml:
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return json.dumps(data, indent=2, default=str) + "\n"


class LogWriter:
    """Writes structured dispatch artifacts to the filesystem."""

    def __init__(self, store=None, date=None):
        self.store = store
        self._date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def day_dir(self, date=None):
        d = date or self._date
        parts = d.split("-")
        return STATE_ROOT / parts[0] / parts[1] / parts[2]

    def task_dir(self, task_id, date=None):
        return self.day_dir(date) / "tasks" / task_id

    # --- Session artifacts ---

    def write_task_yaml(self, date=None):
        d = date or self._date
        tasks = self.store.list_tasks(date=d)
        data = {
            "date": d,
            "generated_at": _now(),
            "tasks": [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "status": t["status"],
                    "priority": t["priority"],
                    "git_permission": bool(t.get("git_permission")),
                    "blocker": t.get("blocker"),
                    "tags": t.get("tags", []),
                }
                for t in tasks
            ],
        }
        path = self.day_dir(d) / "task.yaml"
        _atomic_write(path, _dump_yaml(data))
        return path

    def write_session_yaml(self, session_id):
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        summary = self.store.export_session_summary(session["date"])
        data = {
            "session_id": session["session_id"],
            "date": session["date"],
            "mode": session.get("mode", ""),
            "started_at": session["started_at"],
            "ended_at": session.get("ended_at"),
            "step_count": session.get("step_count", 0),
            "task_count": session.get("task_count", 0),
            "context_compaction_count": session.get("context_compaction_count", 0),
            "steps": summary.get("steps", []),
        }
        path = self.day_dir(session["date"]) / "session.yaml"
        _atomic_write(path, _dump_yaml(data))
        return path

    def write_carry_forward(self, session_id):
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        tasks = self.store.generate_carry_forward()
        data = {
            "generated_at": _now(),
            "source_session": session_id,
            "tasks": tasks,
        }
        path = self.day_dir(session["date"]) / "carry_forward.yaml"
        _atomic_write(path, _dump_yaml(data))
        return path

    def write_slack_queue_fallback(self, notifications):
        data = {
            "generated_at": _now(),
            "pending_count": len(notifications),
            "messages": [
                {
                    "id": n.get("id"),
                    "channel": n["channel"],
                    "message": n["message"],
                    "template_id": n.get("template_id", ""),
                }
                for n in notifications
            ],
        }
        path = self.day_dir() / "slack_queue.yaml"
        _atomic_write(path, _dump_yaml(data))
        return path

    # --- Task artifacts ---

    def append_task_log(self, task_id, entry, timestamp=None):
        ts = timestamp or _now()
        tdir = self.task_dir(task_id)
        tdir.mkdir(parents=True, exist_ok=True)
        log_path = tdir / "task_log.md"

        line = f"[{ts}] {entry}\n"
        if log_path.exists():
            existing = log_path.read_text()
            lines = existing.splitlines(keepends=True)
            lines.append(line)
            if len(lines) > TASK_LOG_MAX_LINES:
                lines = lines[-TASK_LOG_MAX_LINES:]
                lines.insert(0, f"<!-- trimmed to {TASK_LOG_MAX_LINES} lines -->\n")
            log_path.write_text("".join(lines))
        else:
            log_path.write_text(f"# Task Log: {task_id}\n\n{line}")

    def write_bash_commands_log(self, task_id):
        rows = self.store.conn.execute(
            """SELECT timestamp, command, blocked, block_reason
               FROM bash_log WHERE task_id = ?
               ORDER BY timestamp""",
            (task_id,),
        ).fetchall()
        lines = [f"# Bash Commands: {task_id}\n\n"]
        for r in rows:
            prefix = "[BLOCKED] " if r["blocked"] else ""
            lines.append(f"{r['timestamp']} | {prefix}{r['command']}\n")
            if r["blocked"] and r["block_reason"]:
                lines.append(f"  reason: {r['block_reason']}\n")
        content = "".join(lines)
        path = self.task_dir(task_id) / "bash_commands.log"
        _atomic_write(path, content)
        return path

    def symlink_artifact(self, task_id, source, link_name):
        source = Path(source)
        tdir = self.task_dir(task_id)
        tdir.mkdir(parents=True, exist_ok=True)
        link_path = tdir / link_name
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(source.resolve())
        return link_path

    # --- Step artifacts ---

    def write_handoff(self, step_id, content):
        path = self.day_dir() / f"handoff_{step_id}.md"
        _atomic_write(path, content)
        return path

    def write_step_output(self, step_id, content, filename):
        path = self.day_dir() / f"{step_id}_{filename}"
        _atomic_write(path, content)
        return path

    # --- Reports ---

    def write_weekly_report(self, content):
        path = self.day_dir() / "weekly_report.md"
        _atomic_write(path, content)
        return path

    def write_monthly_report(self, content):
        path = self.day_dir() / "monthly_report.md"
        _atomic_write(path, content)
        return path


def main():
    parser = argparse.ArgumentParser(description="Dispatch log writer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_session = sub.add_parser("session", help="Write session.yaml")
    p_session.add_argument("--session-id", required=True)

    p_tasks = sub.add_parser("tasks", help="Write task.yaml")
    p_tasks.add_argument("--date", required=True)

    p_carry = sub.add_parser("carry-forward", help="Write carry_forward.yaml")
    p_carry.add_argument("--session-id", required=True)

    p_task_log = sub.add_parser("task-log", help="Write bash_commands.log")
    p_task_log.add_argument("--task", required=True)

    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore

    with StateStore() as store:
        store.schema_init()
        writer = LogWriter(store)

        if args.command == "session":
            path = writer.write_session_yaml(args.session_id)
            print(f"Written: {path}")
        elif args.command == "tasks":
            writer._date = args.date
            path = writer.write_task_yaml(args.date)
            print(f"Written: {path}")
        elif args.command == "carry-forward":
            path = writer.write_carry_forward(args.session_id)
            print(f"Written: {path}")
        elif args.command == "task-log":
            path = writer.write_bash_commands_log(args.task)
            print(f"Written: {path}")


if __name__ == "__main__":
    main()
