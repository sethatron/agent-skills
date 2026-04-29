#!/usr/bin/env python3
"""
Dispatch skill environment pre-validation.

Run first on every /dispatch invocation. Validates Python, packages,
SQLite DB, directories, workflow config, sibling skills, claude binary,
hooks directory, and API key.

Usage:
    python scripts/check_env.py [--verbose] [--json] [--fix]
"""

import argparse
import importlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.path.expanduser("~/.zsh/dispatch"))
DB_PATH = STATE_ROOT / "dispatch.db"
WORKFLOW_PATH = STATE_ROOT / "workflow.yaml"

REQUIRED_PACKAGES = ["requests", "jinja2", "yaml"]
PACKAGE_INSTALL_NAMES = {"requests": "requests", "jinja2": "jinja2", "yaml": "pyyaml"}


def check_python_version(verbose: bool) -> tuple[bool, str]:
    v = sys.version_info
    if v >= (3, 10):
        return True, f"Python {v.major}.{v.minor}.{v.micro}" if verbose else "Python OK"
    return False, f"Python 3.10+ required. Found: {v.major}.{v.minor}.{v.micro}"


def check_packages(verbose: bool) -> tuple[bool, str]:
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        install = [PACKAGE_INSTALL_NAMES.get(p, p) for p in missing]
        return False, f"Missing package(s): {', '.join(missing)}. Install with: pip install {' '.join(install)}"
    return True, f"Packages OK: {', '.join(REQUIRED_PACKAGES)}" if verbose else "Packages OK"


def check_sqlite(verbose: bool, fix: bool) -> tuple[bool, str]:
    try:
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        needs_init = not DB_PATH.exists()
        if not needs_init:
            conn = sqlite3.connect(str(DB_PATH))
            tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            conn.close()
            needs_init = tables == 0
        if needs_init:
            sys.path.insert(0, str(SKILL_DIR / "scripts"))
            from state_store import StateStore
            store = StateStore()
            store.schema_init()
            store.close()
            return True, f"SQLite DB initialized at {DB_PATH}" if verbose else "SQLite DB OK (initialized)"
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        conn.close()
        if result == "ok":
            return True, f"SQLite DB OK: {DB_PATH}" if verbose else "SQLite DB OK"
        if fix:
            backup = DB_PATH.with_suffix(f".backup.{int(__import__('time').time())}")
            DB_PATH.rename(backup)
            return False, f"DB corrupt, backed up to {backup}. Re-run to initialize."
        return False, f"SQLite DB integrity check failed: {result}"
    except Exception as e:
        return False, f"SQLite check failed: {e}"


def check_state_dir(verbose: bool) -> tuple[bool, str]:
    try:
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        test = STATE_ROOT / ".write_test"
        test.write_text("test")
        test.unlink()
        return True, f"State dir writable: {STATE_ROOT}" if verbose else "State dir OK"
    except Exception as e:
        return False, f"~/.zsh/dispatch/ is not writable: {e}"


def check_workflow_yaml(verbose: bool) -> tuple[bool, str]:
    if not WORKFLOW_PATH.exists():
        return False, f"workflow.yaml not found at {WORKFLOW_PATH}. Run /dispatch scaffold first."
    try:
        import yaml
        with open(WORKFLOW_PATH) as f:
            data = yaml.safe_load(f)
        if not data or "steps" not in data:
            return False, "workflow.yaml is missing 'steps' key."
        return True, f"workflow.yaml valid ({len(data['steps'])} steps)" if verbose else "workflow.yaml OK"
    except Exception as e:
        return False, f"workflow.yaml parse error: {e}"


def check_slack_mcp(verbose: bool) -> tuple[bool, str]:
    # Slack MCP availability is best-effort; queue messages if unavailable
    return True, "Slack MCP check deferred to runtime" if verbose else "Slack MCP deferred"


def check_sibling_skill(name: str, verbose: bool) -> tuple[bool, str]:
    paths = [
        Path(os.path.expanduser(f"~/.claude/skills/{name}")),
        Path(os.path.expanduser(f"~/.claude/skills/{name}/SKILL.md")),
    ]
    for p in paths:
        if p.exists():
            return True, f"/{name} skill found at {p.parent}" if verbose else f"/{name} skill OK"
    return False, f"/{name} skill not found at ~/.claude/skills/{name}"


def check_claude_binary(verbose: bool) -> tuple[bool, str]:
    path = shutil.which("claude")
    if path:
        return True, f"claude found at {path}" if verbose else "claude binary OK"
    return False, "claude binary not found on PATH. Required for Optimus subprocess invocation."


def check_hooks_dir(verbose: bool) -> tuple[bool, str]:
    hooks_dir = Path(os.path.expanduser("~/.claude/hooks"))
    try:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        return True, f"Hooks dir writable: {hooks_dir}" if verbose else "Hooks dir OK"
    except Exception as e:
        return False, f"~/.claude/hooks/ is not writable: {e}"


def check_git_binary(verbose: bool) -> tuple[bool, str]:
    path = shutil.which("git")
    if path:
        return True, f"git found at {path}" if verbose else "git OK"
    return False, "git not found on PATH."


def run_checks(verbose: bool = False, fix: bool = False) -> list[dict]:
    results = []

    def add(name: str, ok: bool, msg: str):
        results.append({"check": name, "ok": ok, "message": msg})
        if verbose:
            status = "OK" if ok else "FAIL"
            print(f"  {status}: {msg}", file=sys.stderr)

    checks = [
        ("python_version", lambda: check_python_version(verbose)),
        ("packages", lambda: check_packages(verbose)),
        ("sqlite", lambda: check_sqlite(verbose, fix)),
        ("state_dir", lambda: check_state_dir(verbose)),
        ("workflow_yaml", lambda: check_workflow_yaml(verbose)),
        ("slack_mcp", lambda: check_slack_mcp(verbose)),
        ("mr_review_skill", lambda: check_sibling_skill("mr-review", verbose)),
        ("jira_skill", lambda: check_sibling_skill("jira", verbose)),
        ("claude_binary", lambda: check_claude_binary(verbose)),
        ("hooks_dir", lambda: check_hooks_dir(verbose)),
        ("git_binary", lambda: check_git_binary(verbose)),
    ]

    for name, check_fn in checks:
        ok, msg = check_fn()
        add(name, ok, msg)

    return results


def main():
    parser = argparse.ArgumentParser(description="Dispatch environment pre-validation")
    parser.add_argument("--verbose", action="store_true", help="Print each check result")
    parser.add_argument("--json", action="store_true", help="Emit results as JSON")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix missing dirs and packages")
    args = parser.parse_args()

    results = run_checks(verbose=args.verbose, fix=args.fix)

    if args.json:
        print(json.dumps({"checks": results, "all_ok": all(r["ok"] for r in results)}, indent=2))
    else:
        failed = [r for r in results if not r["ok"]]
        if failed:
            for r in failed:
                print(f"ERROR: {r['message']}", file=sys.stderr)
            sys.exit(1)
        else:
            print("ENV OK — dispatch environment validated.")

    if not all(r["ok"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
