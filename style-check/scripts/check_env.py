#!/usr/bin/env python3
import sys
import shutil
from pathlib import Path


def check_env():
    errors = []

    if sys.version_info < (3, 10):
        errors.append(f"Python >= 3.10 required, got {sys.version}")

    try:
        import yaml  # noqa: F401
    except ImportError:
        errors.append("pyyaml not installed")

    try:
        import jinja2  # noqa: F401
    except ImportError:
        errors.append("jinja2 not installed")

    if not shutil.which("git"):
        errors.append("git not found on PATH")

    config = Path(__file__).resolve().parent.parent / "config" / "standards.yaml"
    if not config.exists():
        errors.append(f"Config not found: {config}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print("ENV OK")


if __name__ == "__main__":
    check_env()
