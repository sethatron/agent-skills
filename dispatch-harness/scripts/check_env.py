#!/usr/bin/env python3
"""
Environment pre-validation for the dispatch-harness skill.

Usage:
    python scripts/check_env.py [--verbose] [--json] [--skip-validation]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DISPATCH_DIR = Path.home() / ".zsh" / "dispatch"
SKILLS_DIR = Path.home() / ".claude" / "skills"
CLAUDE_DIR = Path.home() / ".claude"
CONTRACTS_DIR = DISPATCH_DIR / "contracts"
HARNESS_DIR = DISPATCH_DIR / "harness"
REGISTRY_PATH = Path("/Users/sethallen/agent-skills/dispatch-manager/contracts/registry.yaml")
VALIDATOR_PATH = Path("/Users/sethallen/agent-skills/dispatch-manager/scripts/dsi_validator.py")

REQUIRED_SKILLS = [
    "dispatch",
    "jira",
    "gitlab-mr-review",
    "dispatch-manager",
    "dispatch-notebook",
    "beads",
]


def check_skill_symlinks() -> dict:
    missing = []
    broken = []
    for skill in REQUIRED_SKILLS:
        link = SKILLS_DIR / skill
        if not link.exists() and not link.is_symlink():
            missing.append(skill)
        elif link.is_symlink() and not link.resolve().exists():
            broken.append(skill)

    if missing or broken:
        parts = []
        if missing:
            parts.append(f"missing: {', '.join(missing)}")
        if broken:
            parts.append(f"broken: {', '.join(broken)}")
        return {"check": "skill_symlinks", "ok": False, "message": f"Skill symlinks {'; '.join(parts)}", "skipped": False}
    return {"check": "skill_symlinks", "ok": True, "message": f"All {len(REQUIRED_SKILLS)} skill symlinks resolve", "skipped": False}


def check_manager_validate(skip: bool = False) -> dict:
    if skip:
        return {"check": "manager_validate", "ok": True, "message": "Skipped (--skip-validation)", "skipped": True}
    try:
        harness_dir = str(Path(__file__).resolve().parent.parent)
        result = subprocess.run(
            ["python3", str(VALIDATOR_PATH), harness_dir, "--type", "B", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode in (0, 1):
            try:
                data = json.loads(result.stdout)
                if data.get("compliant"):
                    return {"check": "manager_validate", "ok": True, "message": f"DSI validator: compliant ({data.get('pass_count', 0)} pass, {data.get('warn_count', 0)} warn)", "skipped": False}
            except (json.JSONDecodeError, KeyError):
                pass
            if result.returncode == 0:
                return {"check": "manager_validate", "ok": True, "message": "DSI validator passed", "skipped": False}
        detail = result.stderr.strip()[:120] or result.stdout.strip()[:120]
        return {"check": "manager_validate", "ok": False, "message": f"DSI validator failed: {detail}", "skipped": False}
    except FileNotFoundError:
        return {"check": "manager_validate", "ok": False, "message": f"Validator not found: {VALIDATOR_PATH}", "skipped": False}
    except subprocess.TimeoutExpired:
        return {"check": "manager_validate", "ok": False, "message": "DSI validator timed out", "skipped": False}
    except Exception as e:
        return {"check": "manager_validate", "ok": False, "message": str(e), "skipped": False}


def check_br_available() -> dict:
    br = shutil.which("br")
    if br:
        return {"check": "br_available", "ok": True, "message": f"br found at {br}", "skipped": False}
    return {"check": "br_available", "ok": False, "message": "br not found on PATH", "skipped": False}


def check_contracts_writable() -> dict:
    if CONTRACTS_DIR.is_dir() and os.access(CONTRACTS_DIR, os.W_OK):
        return {"check": "contracts_writable", "ok": True, "message": f"Contracts dir writable: {CONTRACTS_DIR}", "skipped": False}
    if DISPATCH_DIR.is_dir() and os.access(DISPATCH_DIR, os.W_OK):
        return {"check": "contracts_writable", "ok": True, "message": f"Parent writable, can create {CONTRACTS_DIR}", "skipped": False}
    return {"check": "contracts_writable", "ok": False, "message": f"Cannot write to {CONTRACTS_DIR} or parent", "skipped": False}


def check_harness_writable() -> dict:
    if HARNESS_DIR.is_dir() and os.access(HARNESS_DIR, os.W_OK):
        return {"check": "harness_writable", "ok": True, "message": f"Harness dir writable: {HARNESS_DIR}", "skipped": False}
    if DISPATCH_DIR.is_dir() and os.access(DISPATCH_DIR, os.W_OK):
        return {"check": "harness_writable", "ok": True, "message": f"Parent writable, can create {HARNESS_DIR}", "skipped": False}
    return {"check": "harness_writable", "ok": False, "message": f"Cannot write to {HARNESS_DIR} or parent", "skipped": False}


def check_python_packages() -> dict:
    missing = []
    for pkg in ["yaml", "graphlib", "pathlib"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        return {"check": "python_packages", "ok": False, "message": f"Missing packages: {', '.join(missing)}", "skipped": False}
    return {"check": "python_packages", "ok": True, "message": "yaml, graphlib, pathlib all importable", "skipped": False}


def check_registry_parseable() -> dict:
    try:
        import yaml
    except ImportError:
        return {"check": "registry_parseable", "ok": False, "message": "Cannot import yaml to parse registry", "skipped": False}

    if not REGISTRY_PATH.is_file():
        return {"check": "registry_parseable", "ok": False, "message": f"Registry not found: {REGISTRY_PATH}", "skipped": False}

    try:
        data = yaml.safe_load(REGISTRY_PATH.read_text())
        if isinstance(data, dict) and "contracts" in data:
            return {"check": "registry_parseable", "ok": True, "message": "Registry parsed, 'contracts' key present", "skipped": False}
        return {"check": "registry_parseable", "ok": False, "message": "Registry parsed but missing 'contracts' key", "skipped": False}
    except Exception as e:
        return {"check": "registry_parseable", "ok": False, "message": f"Registry parse error: {e}", "skipped": False}


def check_slack_mcp() -> dict:
    mcp_paths = [
        CLAUDE_DIR / "claude_desktop_config.json",
        CLAUDE_DIR / "mcp.json",
        CLAUDE_DIR / "settings.json",
    ]
    for p in mcp_paths:
        if p.is_file():
            try:
                content = p.read_text().lower()
                if "slack" in content:
                    return {"check": "slack_mcp", "ok": True, "message": f"WARN: Slack MCP config found in {p.name} (not validated)", "skipped": False}
            except Exception:
                pass
    return {"check": "slack_mcp", "ok": True, "message": "WARN: No Slack MCP config detected; Slack tools may be unavailable", "skipped": False}


def run_all(skip_validation: bool = False) -> list[dict]:
    return [
        check_skill_symlinks(),
        check_manager_validate(skip=skip_validation),
        check_br_available(),
        check_contracts_writable(),
        check_harness_writable(),
        check_python_packages(),
        check_registry_parseable(),
        check_slack_mcp(),
    ]


def main():
    parser = argparse.ArgumentParser(description="Dispatch harness environment validator")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    checks = run_all(skip_validation=args.skip_validation)
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
