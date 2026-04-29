#!/usr/bin/env python3
"""
Dispatch-manager environment pre-validation.

Usage:
    python scripts/check_env.py [--verbose] [--json] [--fix]
"""

import argparse
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ECOSYSTEM_PATH = SKILL_DIR / "config" / "ecosystem.yaml"
REGISTRY_PATH = SKILL_DIR / "contracts" / "registry.yaml"
BACKUPS_DIR = SKILL_DIR / "backups"
DISPATCH_DB = Path(os.path.expanduser("~/.zsh/dispatch/dispatch.db"))
OPTIMUS_DIR = Path(os.path.expanduser("~/.zsh/dispatch/optimus"))

REQUIRED_PACKAGES = ["yaml", "jinja2"]
PACKAGE_INSTALL_NAMES = {"yaml": "pyyaml", "jinja2": "jinja2"}


def _load_yaml(path: Path) -> dict | None:
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _load_ecosystem() -> dict | None:
    return _load_yaml(ECOSYSTEM_PATH)


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


def check_managed_skills_present(verbose: bool) -> tuple[bool, str]:
    data = _load_ecosystem()
    if not data or "skills" not in data:
        return False, "Cannot check managed skills: ecosystem.yaml unreadable or missing 'skills' key."
    skills = data["skills"]
    missing = []
    for name, info in skills.items():
        skill_path = Path(info.get("path", ""))
        if not skill_path.exists() or not (skill_path / "SKILL.md").exists():
            missing.append(name)
    if missing:
        return False, f"Missing skill dir or SKILL.md: {', '.join(missing)}"
    return True, f"All {len(skills)} managed skills present" if verbose else "Managed skills OK"


def check_symlinks_intact(verbose: bool) -> tuple[bool, str]:
    data = _load_ecosystem()
    if not data or "skills" not in data:
        return False, "Cannot check symlinks: ecosystem.yaml unreadable or missing 'skills' key."
    skills = data["skills"]
    broken = []
    for name, info in skills.items():
        symlink = info.get("symlink", "")
        if not symlink:
            broken.append(f"{name} (no symlink field)")
            continue
        resolved = Path(os.path.expanduser(symlink)).resolve()
        if not resolved.is_dir():
            broken.append(name)
    if broken:
        return False, f"Broken symlinks: {', '.join(broken)}"
    return True, f"All {len(skills)} symlinks intact" if verbose else "Symlinks OK"


def check_registry_parseable(verbose: bool) -> tuple[bool, str]:
    if not REGISTRY_PATH.exists():
        return False, f"registry.yaml not found at {REGISTRY_PATH}"
    data = _load_yaml(REGISTRY_PATH)
    if data is None:
        return False, "registry.yaml failed to parse as valid YAML."
    if "contracts" not in data:
        return False, "registry.yaml is missing 'contracts' key."
    count = len(data["contracts"])
    return True, f"registry.yaml valid ({count} contracts)" if verbose else "Registry OK"


def check_ecosystem_parseable(verbose: bool) -> tuple[bool, str]:
    if not ECOSYSTEM_PATH.exists():
        return False, f"ecosystem.yaml not found at {ECOSYSTEM_PATH}"
    data = _load_yaml(ECOSYSTEM_PATH)
    if data is None:
        return False, "ecosystem.yaml failed to parse as valid YAML."
    if "skills" not in data:
        return False, "ecosystem.yaml is missing 'skills' key."
    count = len(data["skills"])
    return True, f"ecosystem.yaml valid ({count} skills)" if verbose else "Ecosystem OK"


def check_dispatch_db_accessible(verbose: bool) -> tuple[bool, str]:
    if not DISPATCH_DB.exists():
        try:
            dispatch_scripts = Path.home() / ".claude" / "skills" / "dispatch" / "scripts"
            sys.path.insert(0, str(dispatch_scripts))
            from state_store import StateStore
            store = StateStore()
            store.schema_init()
            store.close()
            return True, f"dispatch.db auto-initialized at {DISPATCH_DB}" if verbose else "Dispatch DB OK (initialized)"
        except Exception as e:
            return False, f"dispatch.db not found and auto-init failed: {e}"
    if not os.access(DISPATCH_DB, os.R_OK):
        return False, f"dispatch.db not readable at {DISPATCH_DB}"
    return True, f"dispatch.db readable: {DISPATCH_DB}" if verbose else "Dispatch DB OK"


def check_optimus_dir_readable(verbose: bool) -> tuple[bool, str]:
    if not OPTIMUS_DIR.exists():
        return False, f"optimus/ directory not found at {OPTIMUS_DIR}"
    if not OPTIMUS_DIR.is_dir():
        return False, f"{OPTIMUS_DIR} exists but is not a directory."
    if not os.access(OPTIMUS_DIR, os.R_OK):
        return False, f"optimus/ directory not readable at {OPTIMUS_DIR}"
    return True, f"optimus/ readable: {OPTIMUS_DIR}" if verbose else "Optimus dir OK"


def check_backups_writable(verbose: bool, fix: bool) -> tuple[bool, str]:
    if not BACKUPS_DIR.exists():
        if fix:
            try:
                BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
                return True, f"Created backups/ at {BACKUPS_DIR}" if verbose else "Backups dir created"
            except Exception as e:
                return False, f"Failed to create backups/: {e}"
        return False, f"backups/ directory not found at {BACKUPS_DIR}. Run with --fix to create."
    if not os.access(BACKUPS_DIR, os.W_OK):
        return False, f"backups/ directory not writable at {BACKUPS_DIR}"
    return True, f"backups/ writable: {BACKUPS_DIR}" if verbose else "Backups dir OK"


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
        ("managed_skills_present", lambda: check_managed_skills_present(verbose)),
        ("symlinks_intact", lambda: check_symlinks_intact(verbose)),
        ("registry_parseable", lambda: check_registry_parseable(verbose)),
        ("ecosystem_parseable", lambda: check_ecosystem_parseable(verbose)),
        ("dispatch_db_accessible", lambda: check_dispatch_db_accessible(verbose)),
        ("optimus_dir_readable", lambda: check_optimus_dir_readable(verbose)),
        ("backups_writable", lambda: check_backups_writable(verbose, fix)),
        ("git_binary", lambda: check_git_binary(verbose)),
    ]

    for name, check_fn in checks:
        ok, msg = check_fn()
        add(name, ok, msg)

    return results


def main():
    parser = argparse.ArgumentParser(description="Dispatch-manager environment pre-validation")
    parser.add_argument("--verbose", action="store_true", help="Print each check result")
    parser.add_argument("--json", action="store_true", help="Emit results as JSON")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix missing dirs")
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
            print("ENV OK — dispatch-manager environment validated.")

    if not all(r["ok"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
