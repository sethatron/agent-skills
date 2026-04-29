#!/usr/bin/env python3
"""
Dispatch-notebook environment pre-validation.

Usage:
    python scripts/check_env.py [--verbose] [--json] [--fix] [--skip-auth]
"""

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = Path(os.path.expanduser("~/.zsh/dispatch/notebook"))
INVENTORY_PATH = NOTEBOOK_DIR / "source_inventory.yaml"
DISPATCH_SKILL = Path(os.path.expanduser("~/.claude/skills/dispatch"))

REQUIRED_PACKAGES = ["yaml", "jinja2"]
PACKAGE_INSTALL_NAMES = {"yaml": "pyyaml", "jinja2": "jinja2"}


def _load_yaml(path: Path) -> dict | None:
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def check_nlm_on_path(verbose: bool) -> tuple[bool, str]:
    path = shutil.which("nlm")
    if path:
        return True, f"nlm found at {path}" if verbose else "nlm OK"
    return False, "nlm not found on PATH. Install with: pip install notebooklm-mcp-cli"


def check_nlm_authenticated(verbose: bool) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["nlm", "login", "--check"],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode == 0:
            return True, "nlm authenticated" if not verbose else f"nlm authenticated: {proc.stdout.strip()[:80]}"
        return False, f"nlm not authenticated: {proc.stderr.strip()[:100]}. Run: nlm login"
    except FileNotFoundError:
        return False, "nlm binary not found"
    except subprocess.TimeoutExpired:
        return False, "nlm auth check timed out"


def check_dispatch_alias(verbose: bool) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["nlm", "alias", "get", "dispatch"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            alias_val = proc.stdout.strip().splitlines()[-1].strip()
            return True, f"dispatch alias: {alias_val[:40]}" if verbose else "Dispatch alias OK"
        return False, "dispatch alias not set. Run: /dispatch-notebook init"
    except FileNotFoundError:
        return False, "nlm binary not found"
    except subprocess.TimeoutExpired:
        return False, "nlm alias check timed out"


def check_notebook_dir_writable(verbose: bool, fix: bool) -> tuple[bool, str]:
    if not NOTEBOOK_DIR.exists():
        if fix:
            try:
                NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
                (NOTEBOOK_DIR / "staging").mkdir(exist_ok=True)
                (NOTEBOOK_DIR / "query_cache").mkdir(exist_ok=True)
                return True, f"Created {NOTEBOOK_DIR}" if verbose else "Notebook dir created"
            except Exception as e:
                return False, f"Failed to create notebook dir: {e}"
        return False, f"Notebook dir not found at {NOTEBOOK_DIR}. Run with --fix to create."
    if not os.access(NOTEBOOK_DIR, os.W_OK):
        return False, f"Notebook dir not writable at {NOTEBOOK_DIR}"
    return True, f"Notebook dir writable: {NOTEBOOK_DIR}" if verbose else "Notebook dir OK"


def check_source_inventory(verbose: bool) -> tuple[bool, str]:
    if not INVENTORY_PATH.exists():
        return True, "source_inventory.yaml not yet created (OK for fresh install)" if verbose else "Inventory N/A (OK)"
    data = _load_yaml(INVENTORY_PATH)
    if data is None:
        return False, f"source_inventory.yaml at {INVENTORY_PATH} failed to parse"
    return True, f"source_inventory.yaml valid" if verbose else "Inventory OK"


def check_python_packages(verbose: bool) -> tuple[bool, str]:
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        install = [PACKAGE_INSTALL_NAMES.get(p, p) for p in missing]
        return False, f"Missing: {', '.join(missing)}. Install: pip install {' '.join(install)}"
    return True, f"Packages OK: {', '.join(REQUIRED_PACKAGES)}" if verbose else "Packages OK"


def check_dispatch_skill_present(verbose: bool) -> tuple[bool, str]:
    skill_md = DISPATCH_SKILL / "SKILL.md"
    if DISPATCH_SKILL.exists() and skill_md.exists():
        return True, f"dispatch skill at {DISPATCH_SKILL}" if verbose else "Dispatch skill OK"
    return False, f"dispatch skill not found at {DISPATCH_SKILL}"


def check_slack_mcp(verbose: bool) -> tuple[bool, str]:
    return True, "Slack MCP check deferred to runtime" if verbose else "Slack MCP OK (deferred)"


def run_checks(verbose: bool = False, fix: bool = False, skip_auth: bool = False) -> list[dict]:
    results = []

    def add(name: str, ok: bool, msg: str, skipped: bool = False):
        results.append({"check": name, "ok": ok, "message": msg, "skipped": skipped})
        if verbose:
            status = "SKIP" if skipped else ("OK" if ok else "FAIL")
            print(f"  {status}: {msg}", file=sys.stderr)

    ok, msg = check_nlm_on_path(verbose)
    add("nlm_on_path", ok, msg)

    if skip_auth:
        add("nlm_authenticated", True, "Skipped (--skip-auth)", skipped=True)
        add("dispatch_alias_exists", True, "Skipped (--skip-auth)", skipped=True)
    else:
        ok, msg = check_nlm_authenticated(verbose)
        add("nlm_authenticated", ok, msg)
        ok, msg = check_dispatch_alias(verbose)
        add("dispatch_alias_exists", ok, msg)

    ok, msg = check_notebook_dir_writable(verbose, fix)
    add("notebook_dir_writable", ok, msg)

    ok, msg = check_source_inventory(verbose)
    add("source_inventory_parseable", ok, msg)

    ok, msg = check_python_packages(verbose)
    add("python_packages", ok, msg)

    ok, msg = check_dispatch_skill_present(verbose)
    add("dispatch_skill_present", ok, msg)

    ok, msg = check_slack_mcp(verbose)
    add("slack_mcp_accessible", ok, msg)

    return results


def main():
    parser = argparse.ArgumentParser(description="Dispatch-notebook environment pre-validation")
    parser.add_argument("--verbose", action="store_true", help="Print each check result")
    parser.add_argument("--json", action="store_true", help="Emit results as JSON")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix missing dirs")
    parser.add_argument("--skip-auth", action="store_true", help="Skip nlm auth checks")
    args = parser.parse_args()

    results = run_checks(verbose=args.verbose, fix=args.fix, skip_auth=args.skip_auth)

    if args.json:
        print(json.dumps({"checks": results, "all_ok": all(r["ok"] for r in results)}, indent=2))
    else:
        failed = [r for r in results if not r["ok"] and not r.get("skipped")]
        if failed:
            for r in failed:
                print(f"ERROR: {r['message']}", file=sys.stderr)
            sys.exit(1)
        else:
            print("ENV OK — dispatch-notebook environment validated.")

    if not all(r["ok"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
