#!/usr/bin/env python3
"""
NotebookLM authentication guard — check, recover, and notify.

Usage as module:
    from auth_guard import ensure_auth, notify_auth_failure
    if not ensure_auth():
        notify_auth_failure()

Usage as CLI:
    python scripts/auth_guard.py check
    python scripts/auth_guard.py ensure [--retries 2]
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

SKILL_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path.home() / ".zsh" / "dispatch" / "dispatch.db"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from nlm_runner import NLMRunner, NLMError


def ensure_auth(nlm: Optional[NLMRunner] = None, max_retries: int = 1) -> bool:
    nlm = nlm or NLMRunner()
    if nlm.login_check():
        return True

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["nlm", "login"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and nlm.login_check():
                return True
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

        if attempt < max_retries - 1:
            time.sleep(5)

    return False


def notify_auth_failure(channel: str = "#dispatch-alerts") -> None:
    if not DB_PATH.exists():
        print("[AUTH] NotebookLM auth expired. Manual re-auth required: nlm login",
              file=sys.stderr)
        return

    try:
        import hashlib
        message = "NotebookLM authentication expired. Manual re-auth required: nlm login"
        content_hash = hashlib.sha256(message.encode()).hexdigest()
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")

        existing = conn.execute(
            """SELECT id FROM notifications
               WHERE content_hash = ? AND status = 'PENDING'""",
            (content_hash,),
        ).fetchone()

        if not existing:
            conn.execute(
                """INSERT INTO notifications
                   (channel, message, template_id, context, content_hash, status, queued_at)
                   VALUES (?, ?, ?, ?, ?, 'PENDING', ?)""",
                (channel, message, "auth_failed", "{}", content_hash, now),
            )
            conn.commit()

        conn.close()
    except Exception as e:
        print(f"[AUTH] Failed to queue notification: {e}", file=sys.stderr)
        print("[AUTH] NotebookLM auth expired. Manual re-auth required: nlm login",
              file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="NotebookLM auth guard")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="Check auth status")

    e = sub.add_parser("ensure", help="Check and attempt recovery")
    e.add_argument("--retries", type=int, default=1, help="Max recovery attempts")

    args = parser.parse_args()

    if args.command == "check":
        nlm = NLMRunner()
        ok = nlm.login_check()
        print("Authenticated" if ok else "Not authenticated")
        sys.exit(0 if ok else 1)
    elif args.command == "ensure":
        ok = ensure_auth(max_retries=args.retries)
        if ok:
            print("Authenticated")
        else:
            print("Authentication failed")
            notify_auth_failure()
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
