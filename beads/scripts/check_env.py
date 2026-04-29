#!/usr/bin/env python3
"""
Environment pre-validation for the beads skill.

Usage:
    python scripts/check_env.py [--verbose] [--json] [--skip-init-check]
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DISPATCH_DIR = Path.home() / ".zsh" / "dispatch"
BEADS_DIR = DISPATCH_DIR / ".beads"
MIN_VERSION = "0.1.14"


def _version_tuple(v: str):
    return tuple(int(x) for x in v.strip().lstrip("v").split(".") if x.isdigit())


def check_br_on_path() -> dict:
    br = shutil.which("br")
    if br:
        return {"check": "br_on_path", "ok": True, "message": f"br found at {br}", "skipped": False}
    return {"check": "br_on_path", "ok": False, "message": "br not found. Install from https://github.com/Dicklesworthstone/beads_rust", "skipped": False}


def check_project_dir() -> dict:
    if DISPATCH_DIR.is_dir():
        return {"check": "project_dir", "ok": True, "message": f"Project dir exists: {DISPATCH_DIR}", "skipped": False}
    return {"check": "project_dir", "ok": False, "message": f"Project dir not found: {DISPATCH_DIR}", "skipped": False}


def check_beads_init(skip: bool = False) -> dict:
    if skip:
        return {"check": "beads_init", "ok": True, "message": "Skipped (--skip-init-check)", "skipped": True}
    if BEADS_DIR.is_dir() and (BEADS_DIR / "beads.db").exists():
        return {"check": "beads_init", "ok": True, "message": f".beads/ initialized at {BEADS_DIR}", "skipped": False}
    return {"check": "beads_init", "ok": False, "message": f".beads/ not initialized. Run: /beads init", "skipped": False}


def check_br_works() -> dict:
    try:
        result = subprocess.run(
            ["br", "info"], cwd=str(DISPATCH_DIR),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"check": "br_works", "ok": True, "message": "br runs in project dir", "skipped": False}
        return {"check": "br_works", "ok": False, "message": f"br info failed: {result.stderr[:100]}", "skipped": False}
    except FileNotFoundError:
        return {"check": "br_works", "ok": False, "message": "br binary not found", "skipped": False}
    except subprocess.TimeoutExpired:
        return {"check": "br_works", "ok": False, "message": "br info timed out", "skipped": False}
    except Exception as e:
        return {"check": "br_works", "ok": False, "message": str(e), "skipped": False}


def check_db_readable() -> dict:
    try:
        result = subprocess.run(
            ["br", "stats"], cwd=str(DISPATCH_DIR),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"check": "db_readable", "ok": True, "message": "Database readable", "skipped": False}
        return {"check": "db_readable", "ok": False, "message": f"br stats failed: {result.stderr[:100]}", "skipped": False}
    except Exception as e:
        return {"check": "db_readable", "ok": False, "message": str(e), "skipped": False}


def check_br_version() -> dict:
    try:
        result = subprocess.run(
            ["br", "--version"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split()[-1] if result.stdout.strip() else "unknown"
            if _version_tuple(version) >= _version_tuple(MIN_VERSION):
                return {"check": "br_version", "ok": True, "message": f"br {version} >= {MIN_VERSION}", "skipped": False}
            return {"check": "br_version", "ok": False, "message": f"br {version} < {MIN_VERSION}. Update recommended.", "skipped": False}
        return {"check": "br_version", "ok": False, "message": "Could not determine br version", "skipped": False}
    except Exception as e:
        return {"check": "br_version", "ok": False, "message": str(e), "skipped": False}


def run_all(skip_init: bool = False) -> list[dict]:
    checks = [
        check_br_on_path(),
        check_project_dir(),
        check_beads_init(skip=skip_init),
        check_br_works(),
        check_db_readable(),
        check_br_version(),
    ]
    return checks


def main():
    parser = argparse.ArgumentParser(description="Beads environment validator")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skip-init-check", action="store_true")
    args = parser.parse_args()

    checks = run_all(skip_init=args.skip_init_check)
    all_ok = all(c["ok"] for c in checks)

    if args.json:
        print(json.dumps({"checks": checks, "all_ok": all_ok}, indent=2))
    elif args.verbose:
        for c in checks:
            status = "SKIP" if c.get("skipped") else ("OK" if c["ok"] else "FAIL")
            print(f"  {status}: {c['message']}")
        print(f"{'ENV OK' if all_ok else 'ENV FAILED'}")
    else:
        if all_ok:
            print("ENV OK")
        else:
            for c in checks:
                if not c["ok"] and not c.get("skipped"):
                    print(f"  FAIL: {c['message']}")
            print("ENV FAILED")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
