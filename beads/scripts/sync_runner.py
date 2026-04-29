#!/usr/bin/env python3
"""
br sync wrapper and hooks.

Usage:
    python scripts/sync_runner.py flush
    python scripts/sync_runner.py import-only
    python scripts/sync_runner.py status
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DISPATCH_DIR = Path.home() / ".zsh" / "dispatch"
BEADS_DIR = DISPATCH_DIR / ".beads"
STATE_STORE_PATH = Path(__file__).resolve().parents[2] / "dispatch" / "scripts"


def _get_store():
    if str(STATE_STORE_PATH) not in sys.path:
        sys.path.insert(0, str(STATE_STORE_PATH))
    try:
        from state_store import StateStore
        return StateStore()
    except Exception:
        return None


class SyncRunner:
    def __init__(self, cwd: Path = DISPATCH_DIR):
        self.cwd = cwd

    def flush(self, reason: str = "manual") -> bool:
        try:
            result = subprocess.run(
                ["br", "sync", "--flush-only"],
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 and result.stderr:
                print(f"  [WARN] {result.stderr.strip()}", file=sys.stderr)
            if result.returncode == 0:
                store = _get_store()
                if store:
                    store.emit_event("beads_synced", "beads", {
                        "reason": reason,
                        "output": result.stdout[:500],
                    })
                    store.close()
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  [ERROR] br sync --flush-only: {e}", file=sys.stderr)
            return False

    def import_only(self) -> bool:
        try:
            result = subprocess.run(
                ["br", "sync", "--import-only"],
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  [ERROR] br sync --import-only: {e}", file=sys.stderr)
            return False

    def sync_status(self) -> dict:
        jsonl_path = BEADS_DIR / "issues.jsonl"
        db_path = BEADS_DIR / "beads.db"

        last_sync = None
        last_modified = None

        if jsonl_path.exists():
            mtime = jsonl_path.stat().st_mtime
            last_sync = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        if db_path.exists():
            mtime = db_path.stat().st_mtime
            last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        pending = False
        if last_sync and last_modified:
            pending = last_modified > last_sync

        return {
            "last_sync": last_sync,
            "last_modified": last_modified,
            "pending_changes": pending,
            "jsonl_exists": jsonl_path.exists(),
            "db_exists": db_path.exists(),
        }


def main():
    parser = argparse.ArgumentParser(description="br sync wrapper")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("flush")
    sub.add_parser("import-only")
    sub.add_parser("status")

    args = parser.parse_args()
    runner = SyncRunner()

    if args.command == "flush":
        ok = runner.flush()
        print("Sync complete" if ok else "Sync failed")
        sys.exit(0 if ok else 1)
    elif args.command == "import-only":
        ok = runner.import_only()
        print("Import complete" if ok else "Import failed")
        sys.exit(0 if ok else 1)
    elif args.command == "status":
        print(json.dumps(runner.sync_status(), indent=2))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
