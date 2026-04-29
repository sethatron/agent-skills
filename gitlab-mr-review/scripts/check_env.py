#!/usr/bin/env python3
"""
GitLab MR Review skill environment pre-validation.

Run first on every /mr-review invocation. Validates Python version,
required packages, git binary, GITLAB_TOKEN, token scopes, and
writable directories.

Usage:
    python scripts/check_env.py [--verbose] [--json]
"""

import argparse
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REQUIRED_PACKAGES = ["requests", "jinja2", "git"]
PACKAGE_INSTALL_NAMES = {"requests": "requests", "jinja2": "jinja2", "git": "gitpython"}
REQUIRED_TOKEN_SCOPES = ["read_api", "read_repository"]
TOKEN_ENV_PATH = Path(os.path.expanduser("~/.config/git/token.env"))


def _load_token_env():
    if os.environ.get("GITLAB_TOKEN"):
        return
    if TOKEN_ENV_PATH.exists():
        for line in TOKEN_ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("export GITLAB_TOKEN="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["GITLAB_TOKEN"] = value
                return


def check_python_version(verbose: bool) -> tuple[bool, str]:
    v = sys.version_info
    if v >= (3, 10):
        msg = f"Python {v.major}.{v.minor}.{v.micro}" if verbose else "Python version OK"
        return True, msg
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
    if verbose:
        return True, f"All required packages present: {', '.join(REQUIRED_PACKAGES)}"
    return True, "Required packages present"


def check_git_binary(verbose: bool) -> tuple[bool, str]:
    path = shutil.which("git")
    if path:
        return True, f"git found at {path}" if verbose else "git found"
    return False, "git not found on PATH. Install git and ensure it is executable."


def check_gitlab_token(verbose: bool) -> tuple[bool, str]:
    _load_token_env()
    token = os.environ.get("GITLAB_TOKEN", "")
    if token:
        masked = token[:4] + "..." + token[-4:] if len(token) > 8 else "***"
        return True, f"GITLAB_TOKEN set ({masked})" if verbose else "GITLAB_TOKEN set"
    return False, "GITLAB_TOKEN is not set. Set it with: export GITLAB_TOKEN=<your-token>"


def check_gitlab_url(verbose: bool) -> tuple[bool, str]:
    url = os.environ.get("GITLAB_URL", "https://gitlab.com")
    try:
        import requests
        resp = requests.get(url, timeout=10, allow_redirects=True)
        if resp.status_code in (200, 302):
            return True, f"GITLAB_URL reachable: {url}" if verbose else "GITLAB_URL reachable"
        return False, f"GITLAB_URL '{url}' returned status {resp.status_code}"
    except ImportError:
        return False, "Cannot check GITLAB_URL: requests package not installed"
    except Exception as e:
        return False, f"GITLAB_URL '{url}' is not reachable. Check network and URL. ({e})"


def check_token_scopes(verbose: bool) -> tuple[bool, str]:
    token = os.environ.get("GITLAB_TOKEN", "")
    url = os.environ.get("GITLAB_URL", "https://gitlab.com")
    if not token:
        return False, "Cannot validate token scopes: GITLAB_TOKEN not set"
    try:
        import requests
        resp = requests.get(
            f"{url.rstrip('/')}/api/v4/personal_access_tokens/self",
            headers={"PRIVATE-TOKEN": token},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            scopes = data.get("scopes", [])
            missing = [s for s in REQUIRED_TOKEN_SCOPES if s not in scopes]
            if missing:
                return False, (
                    f"GITLAB_TOKEN is missing required scope(s): {', '.join(missing)}.\n"
                    f"Required scopes: {', '.join(REQUIRED_TOKEN_SCOPES)}.\n"
                    f"Re-generate your token at: {url}/-/user_settings/personal_access_tokens"
                )
            if verbose:
                return True, f"Token scopes valid: {', '.join(scopes)}"
            return True, "Token scopes valid"
        elif resp.status_code in (401, 403):
            return False, "GITLAB_TOKEN is invalid or expired."
        return False, f"Token scope check returned status {resp.status_code}"
    except ImportError:
        return False, "Cannot validate scopes: requests package not installed"
    except Exception as e:
        return False, f"Token scope validation failed: {e}"


def check_cache_dir(verbose: bool) -> tuple[bool, str]:
    dirs = [SKILL_DIR / "cache" / "mrs", SKILL_DIR / "cache" / "direct"]
    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            test = d / ".write_test"
            test.write_text("test")
            test.unlink()
        except Exception as e:
            return False, f"Cache directory is not writable: {d} ({e})"
    if verbose:
        return True, f"Cache directories writable: {', '.join(str(d) for d in dirs)}"
    return True, "Cache directories writable"


def check_review_output_dir(verbose: bool) -> tuple[bool, str]:
    base = Path(os.path.expanduser("~/.zsh/review"))
    try:
        base.mkdir(parents=True, exist_ok=True)
        test = base / ".write_test"
        test.write_text("test")
        test.unlink()
        return True, f"Review output directory creatable: {base}" if verbose else "Review output dir OK"
    except Exception as e:
        return False, f"Cannot create review output directory: {base} ({e})"


def run_checks(verbose: bool = False) -> list[dict]:
    results = []

    def add(name: str, ok: bool, msg: str):
        results.append({"check": name, "ok": ok, "message": msg})
        if verbose:
            status = "OK" if ok else "FAIL"
            print(f"  {status}: {msg}", file=sys.stderr)

    checks = [
        ("python_version", lambda: check_python_version(verbose)),
        ("packages", lambda: check_packages(verbose)),
        ("git_binary", lambda: check_git_binary(verbose)),
        ("gitlab_token", lambda: check_gitlab_token(verbose)),
        ("gitlab_url", lambda: check_gitlab_url(verbose)),
        ("token_scopes", lambda: check_token_scopes(verbose)),
        ("cache_dir", lambda: check_cache_dir(verbose)),
        ("review_output_dir", lambda: check_review_output_dir(verbose)),
    ]

    for name, check_fn in checks:
        ok, msg = check_fn()
        add(name, ok, msg)
        if not ok and name in ("python_version", "gitlab_token"):
            break

    return results


def main():
    parser = argparse.ArgumentParser(description="GitLab MR Review environment pre-validation")
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
            print("ENV OK — all preconditions satisfied.")

    if not all(r["ok"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
