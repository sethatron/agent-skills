#!/usr/bin/env python3
"""
Jira skill environment pre-validation.

Run first on every /jira invocation. Validates jiratui installation,
config, Jira API connectivity, required packages, and writable dirs.

Usage:
    python scripts/check_env.py [--verbose] [--json]
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
REQUIRED_CONFIG_FIELDS = ["jira_api_username", "jira_api_token", "jira_api_base_url"]
REQUIRED_PACKAGES = ["requests", "yaml", "jinja2"]
PACKAGE_INSTALL_NAMES = {"yaml": "pyyaml", "jinja2": "jinja2", "requests": "requests"}


def find_jiratui_config() -> Path | None:
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    candidates = []
    if xdg:
        candidates.append(Path(xdg) / "jiratui" / "config.yaml")
    candidates.append(Path.home() / ".config" / "jiratui" / "config.yaml")
    for c in candidates:
        if c.is_file():
            return c
    return None


def parse_config(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def check_jiratui_installed(verbose: bool) -> tuple[bool, str]:
    path = shutil.which("jiratui")
    if path:
        if verbose:
            try:
                result = subprocess.run(
                    ["jiratui", "version"], capture_output=True, text=True, timeout=10
                )
                ver = result.stdout.strip() or "unknown"
            except Exception:
                ver = "unknown"
            return True, f"jiratui found at {path} (version: {ver})"
        return True, "jiratui found"
    return False, (
        "jiratui not found on PATH.\n"
        "Install with: uv tool install jiratui  (or: pip install jiratui)"
    )


def check_config_exists(verbose: bool) -> tuple[bool, str, Path | None]:
    path = find_jiratui_config()
    if path:
        msg = f"jiratui config found at {path}" if verbose else "jiratui config found"
        return True, msg, path
    return False, (
        "jiratui config not found at expected location.\n"
        "Create it at ~/.config/jiratui/config.yaml with fields:\n"
        "  jira_api_username, jira_api_token, jira_api_base_url"
    ), None


def check_config_fields(config: dict, verbose: bool) -> tuple[bool, str]:
    missing = [f for f in REQUIRED_CONFIG_FIELDS if f not in config or not config[f]]
    if missing:
        return False, f"jiratui config is missing field(s): {', '.join(missing)}"
    if verbose:
        return True, f"All required config fields present: {', '.join(REQUIRED_CONFIG_FIELDS)}"
    return True, "Config fields valid"


def check_jira_reachable(base_url: str, username: str, token: str, verbose: bool) -> tuple[bool, str]:
    try:
        import requests
    except ImportError:
        return False, "Cannot check connectivity: requests package not installed"

    url = f"{base_url.rstrip('/')}/rest/api/3/myself"
    try:
        resp = requests.get(url, auth=(username, token), timeout=10)
    except requests.ConnectionError:
        return False, f"Jira instance at {base_url} is not reachable. Check network/VPN."
    except requests.Timeout:
        return False, f"Jira instance at {base_url} timed out. Check network/VPN."
    except Exception as e:
        return False, f"Jira connectivity check failed: {e}"

    if resp.status_code == 200:
        if verbose:
            data = resp.json()
            return True, f"Jira API OK — authenticated as {data.get('displayName', 'unknown')}"
        return True, "Jira API connectivity confirmed"
    if resp.status_code in (401, 403):
        return False, (
            "Jira API token is invalid or expired.\n"
            "Regenerate at: https://id.atlassian.com/manage-profile/security/api-tokens"
        )
    return False, f"Jira API returned unexpected status {resp.status_code}"


def check_packages(verbose: bool) -> tuple[bool, str]:
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        install_names = [PACKAGE_INSTALL_NAMES.get(p, p) for p in missing]
        return False, f"Missing package(s): {', '.join(missing)}. Install with: pip install {' '.join(install_names)}"
    if verbose:
        return True, f"All required packages present: {', '.join(REQUIRED_PACKAGES)}"
    return True, "Required packages present"


def check_directories(verbose: bool) -> tuple[bool, str]:
    dirs_to_check = [
        SKILL_DIR / "cache" / "jira",
    ]
    export_path = Path(os.path.expanduser("~/.zsh/jira/exports"))
    dirs_to_check.append(export_path)

    errors = []
    for d in dirs_to_check:
        try:
            d.mkdir(parents=True, exist_ok=True)
            test_file = d / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except Exception as e:
            errors.append(f"Directory not writable: {d} ({e})")

    if errors:
        return False, "\n".join(errors)
    if verbose:
        return True, f"Directories writable: {', '.join(str(d) for d in dirs_to_check)}"
    return True, "Output and cache directories writable"


def run_checks(verbose: bool = False) -> list[dict]:
    results = []

    def add(name: str, ok: bool, msg: str):
        results.append({"check": name, "ok": ok, "message": msg})
        if verbose and not ok:
            print(f"  FAIL: {msg}", file=sys.stderr)
        elif verbose:
            print(f"  OK: {msg}", file=sys.stderr)

    ok, msg = check_jiratui_installed(verbose)
    add("jiratui_installed", ok, msg)
    if not ok:
        return results

    ok, msg, config_path = check_config_exists(verbose)
    add("config_exists", ok, msg)
    if not ok:
        return results

    config = parse_config(config_path)
    ok, msg = check_config_fields(config, verbose)
    add("config_fields", ok, msg)
    if not ok:
        return results

    base_url = config.get("jira_api_base_url", "")
    username = config.get("jira_api_username", "")
    token = config.get("jira_api_token", "")

    ok, msg = check_jira_reachable(base_url, username, token, verbose)
    add("jira_reachable", ok, msg)

    ok, msg = check_packages(verbose)
    add("packages", ok, msg)

    ok, msg = check_directories(verbose)
    add("directories", ok, msg)

    return results


def main():
    parser = argparse.ArgumentParser(description="Jira skill environment pre-validation")
    parser.add_argument("--verbose", action="store_true", help="Print each check result")
    parser.add_argument("--json", action="store_true", help="Emit results as JSON")
    args = parser.parse_args()

    results = run_checks(verbose=args.verbose)

    if args.json:
        print(json.dumps({"checks": results, "all_ok": all(r["ok"] for r in results)}, indent=2))
    else:
        failed = [r for r in results if not r["ok"]]
        if failed:
            for r in failed:
                print(f"ERROR: {r['message']}", file=sys.stderr)
            sys.exit(1)
        else:
            print("ENV OK — jiratui and Jira API connectivity confirmed.")

    if not all(r["ok"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
