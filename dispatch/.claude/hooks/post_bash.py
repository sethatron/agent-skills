#!/usr/bin/env python3
"""
Post-Bash hook: Log every bash command execution to dispatch.db.

Records command, cwd, exit_code, duration_ms, and timestamp.

Hook contract:
    - Receives tool result JSON on stdin
    - Always exits 0 (logging hook, never blocks)
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~/.zsh/dispatch/dispatch.db"))


def main():
    if not DB_PATH.exists():
        sys.exit(0)

    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", {})

    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    exit_code = tool_result.get("exit_code")
    duration_ms = tool_result.get("duration_ms")

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO bash_log (command, cwd, exit_code, duration_ms, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (command, os.getcwd(), exit_code, duration_ms,
             time.strftime("%Y-%m-%dT%H:%M:%S%z")),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    try:
        from event_processor import process_pending_events
        process_pending_events()
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
