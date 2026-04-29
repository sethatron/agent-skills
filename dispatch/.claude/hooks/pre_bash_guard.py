#!/usr/bin/env python3
"""
Pre-Bash hook: Git guardrail for dispatch.

Blocks git add/commit/push unless the active task has git_permission=true
in dispatch.db. Logs all bash commands to bash_log regardless.

Hook contract:
    - Receives tool input JSON on stdin
    - Exit 0 to allow, exit 2 to block
    - Stdout JSON with "decision" and optional "reason"
"""

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~/.zsh/dispatch/dispatch.db"))

GIT_WRITE_PATTERNS = [
    r"\bgit\s+add\b",
    r"\bgit\s+commit\b",
    r"\bgit\s+push\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+checkout\s+--\b",
    r"\bgit\s+clean\b",
    r"\bgit\s+stash\s+drop\b",
]


def get_active_task_id(conn: sqlite3.Connection) -> str | None:
    """Find the currently active (IN_PROGRESS) task."""
    try:
        cursor = conn.execute(
            "SELECT task_id FROM tasks WHERE status = 'IN_PROGRESS' ORDER BY started_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def check_git_permission(conn: sqlite3.Connection, task_id: str) -> bool:
    """Check if a task has git_permission=true."""
    try:
        cursor = conn.execute(
            "SELECT git_permission FROM tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        return bool(row[0]) if row else False
    except Exception:
        return False


def is_git_write_command(command: str) -> bool:
    for pattern in GIT_WRITE_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


DISPATCH_DIR = Path(os.path.expanduser("~/.zsh/dispatch"))


def check_br_sync_warning(conn: sqlite3.Connection, command: str) -> str | None:
    if not re.search(r"\bgit\s+commit\b", command):
        return None

    try:
        cwd = Path(os.getcwd()).resolve()
        dispatch_resolved = DISPATCH_DIR.resolve()
        if not str(cwd).startswith(str(dispatch_resolved)):
            return None
    except Exception:
        return None

    try:
        today = time.strftime("%Y-%m-%d")
        cursor = conn.execute(
            "SELECT 1 FROM bash_log WHERE command LIKE '%br sync --flush-only%' "
            "AND timestamp >= ? LIMIT 1",
            (today,),
        )
        if cursor.fetchone():
            return None
    except Exception:
        return None

    return (
        "BLOCKED: git commit in dispatch directory without prior 'br sync --flush-only'. "
        "Run: cd ~/.zsh/dispatch && br sync --flush-only"
    )


ARCH_PATH = Path(os.path.expanduser("~/.zsh/dispatch/contracts/architecture.yaml"))
ARCH_VIOLATIONS_LOG = Path(os.path.expanduser("~/.zsh/dispatch/harness/arch-violations.log"))

SKILL_INVOKE_PATTERNS = [
    r"/(\w[\w-]+)",
    r"claude\s+-p\s+\S*?/agent-skills/(\w[\w-]+)",
]


def check_architecture_constraint(command: str) -> str | None:
    if not ARCH_PATH.exists():
        return None

    try:
        import yaml
        arch = yaml.safe_load(ARCH_PATH.read_text())
    except Exception:
        return None

    dep_order = arch.get("dependency_order", [])
    known_slugs = {entry["slug"] for entry in dep_order}
    calls_map = {entry["slug"]: set(entry.get("calls", [])) for entry in dep_order}

    called_slug = None
    for pattern in SKILL_INVOKE_PATTERNS:
        match = re.search(pattern, command)
        if match:
            candidate = match.group(1)
            if candidate in known_slugs:
                called_slug = candidate
                break

    if not called_slug:
        return None

    calling_slug = os.environ.get("DISPATCH_SKILL_CONTEXT", "unknown")

    if calling_slug == "unknown" or calling_slug == called_slug:
        return None

    declared_calls = calls_map.get(calling_slug, set())
    if called_slug not in declared_calls:
        warning = (
            f"ARCH WARN: {calling_slug} -> {called_slug} "
            f"not declared in architecture.yaml"
        )
        _log_arch_violation(calling_slug, called_slug, command[:80])
        return warning

    return None


def _log_arch_violation(calling: str, called: str, command_snippet: str) -> None:
    try:
        ARCH_VIOLATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ARCH_VIOLATIONS_LOG, "a") as f:
            f.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} "
                f"{calling} -> {called} "
                f"cmd: {command_snippet}\n"
            )
    except Exception:
        pass


def log_command(conn: sqlite3.Connection, command: str, blocked: bool = False,
                block_reason: str = "") -> None:
    """Log the bash command to bash_log table."""
    try:
        conn.execute(
            """INSERT INTO bash_log (command, cwd, timestamp, blocked, block_reason)
               VALUES (?, ?, ?, ?, ?)""",
            (command, os.getcwd(), time.strftime("%Y-%m-%dT%H:%M:%S%z"),
             1 if blocked else 0, block_reason),
        )
        conn.commit()
    except Exception:
        pass


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        json.dump({"decision": "allow"}, sys.stdout)
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        json.dump({"decision": "allow"}, sys.stdout)
        sys.exit(0)

    if not DB_PATH.exists():
        json.dump({"decision": "allow"}, sys.stdout)
        sys.exit(0)

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        json.dump({"decision": "allow"}, sys.stdout)
        sys.exit(0)

    if is_git_write_command(command):
        task_id = get_active_task_id(conn)

        sync_warning = check_br_sync_warning(conn, command)

        if sync_warning:
            log_command(conn, command, blocked=True, block_reason=sync_warning)
            conn.close()
            json.dump({"decision": "block", "reason": sync_warning}, sys.stdout)
            sys.exit(2)

        if task_id and check_git_permission(conn, task_id):
            log_command(conn, command, blocked=False, block_reason="")
            conn.close()
            json.dump({"decision": "allow"}, sys.stdout)
            sys.exit(0)

        reason = (
            f"BLOCKED: git add/commit/push requires explicit permission for task {task_id or 'none'}.\n"
            f"Grant with: /dispatch task git-allow <jira-id>"
        )
        if sync_warning:
            reason = f"{sync_warning}\n{reason}"
        log_command(conn, command, blocked=True, block_reason=reason)
        conn.close()
        json.dump({"decision": "block", "reason": reason}, sys.stdout)
        sys.exit(2)

    arch_warning = check_architecture_constraint(command)
    if arch_warning:
        log_command(conn, command, blocked=False, block_reason=arch_warning)
    else:
        log_command(conn, command, blocked=False)
    conn.close()
    json.dump({"decision": "allow"}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
