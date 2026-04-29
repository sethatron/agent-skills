#!/usr/bin/env python3
"""
Post-Edit hook: Log every file edit to dispatch.db.

Records path, diff line count, and timestamp.

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
    file_path = tool_input.get("file_path", "")
    old_string = tool_input.get("old_string", "")
    new_string = tool_input.get("new_string", "")

    if not file_path:
        sys.exit(0)

    diff_lines = abs(new_string.count("\n") - old_string.count("\n"))

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO bash_log (command, cwd, timestamp, blocked, block_reason)
               VALUES (?, ?, ?, 0, '')""",
            (f"[Edit] {file_path} ({diff_lines} line delta)", os.getcwd(),
             time.strftime("%Y-%m-%dT%H:%M:%S%z")),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
