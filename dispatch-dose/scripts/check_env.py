#!/usr/bin/env python3
"""Environment validation for dispatch-dose."""

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

def check_skill_md():
    path = SKILL_DIR / "SKILL.md"
    return path.exists(), "SKILL.md exists" if path.exists() else "SKILL.md missing"

def main():
    checks = [check_skill_md]
    all_ok = True
    for check in checks:
        ok, msg = check()
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {msg}")
        if not ok:
            all_ok = False
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
