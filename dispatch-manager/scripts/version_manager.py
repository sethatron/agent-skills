#!/usr/bin/env python3
"""
Semantic version management for managed skills.

Usage (CLI):
    python scripts/version_manager.py read --skill dispatch
    python scripts/version_manager.py bump --skill dispatch --level PATCH
    python scripts/version_manager.py set --skill dispatch --version 2.0.0

Usage (module):
    from version_manager import VersionManager
    vm = VersionManager()
    vm.bump_version("dispatch", "MINOR")
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
ECOSYSTEM_PATH = SKILL_DIR / "config" / "ecosystem.yaml"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class VersionManager:

    def parse_semver(self, version: str) -> Tuple[int, int, int]:
        version = version.strip().strip('"').strip("'")
        m = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version)
        if not m:
            raise ValueError(f"Invalid semver: {version}")
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    def _resolve_skill_md(self, skill_name: str) -> Path:
        if not ECOSYSTEM_PATH.exists():
            raise FileNotFoundError(f"ecosystem.yaml not found at {ECOSYSTEM_PATH}")
        eco = yaml.safe_load(ECOSYSTEM_PATH.read_text()) or {}
        skills = eco.get("skills", {})
        extended = eco.get("extended_skills", {})
        entry = skills.get(skill_name) or extended.get(skill_name)
        if not entry:
            for name, e in {**skills, **extended}.items():
                if skill_name in e.get("aliases", []):
                    entry = e
                    break
        if not entry:
            raise ValueError(f"Skill '{skill_name}' not found in ecosystem.yaml")
        skill_path = Path(os.path.expanduser(entry["path"]))
        return skill_path / "SKILL.md"

    def read_version(self, skill_name: str) -> Optional[str]:
        skill_md = self._resolve_skill_md(skill_name)
        if not skill_md.exists():
            return None
        content = skill_md.read_text()
        m = re.search(r'^version:\s*["\']?([^"\'\n]+)', content, re.MULTILINE)
        return m.group(1).strip() if m else None

    def update_frontmatter(self, skill_md_path: Path, version: str) -> None:
        content = skill_md_path.read_text()
        new_content = re.sub(
            r'^(version:\s*)["\']?[^"\'\n]+["\']?',
            f'\\1"{version}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )
        _atomic_write(skill_md_path, new_content)

    def bump_version(self, skill_name: str, level: str = "PATCH") -> str:
        current = self.read_version(skill_name)
        if not current:
            raise ValueError(f"No version found for skill '{skill_name}'")
        major, minor, patch = self.parse_semver(current)
        if level == "MAJOR":
            major, minor, patch = major + 1, 0, 0
        elif level == "MINOR":
            major, minor, patch = major, minor + 1, 0
        else:
            patch += 1
        new_version = f"{major}.{minor}.{patch}"
        self.set_version(skill_name, new_version)
        return new_version

    def set_version(self, skill_name: str, version: str) -> None:
        self.parse_semver(version)
        skill_md = self._resolve_skill_md(skill_name)
        self.update_frontmatter(skill_md, version)


def main():
    parser = argparse.ArgumentParser(description="Skill version manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_read = sub.add_parser("read", help="Read current version")
    p_read.add_argument("--skill", required=True)

    p_bump = sub.add_parser("bump", help="Bump version")
    p_bump.add_argument("--skill", required=True)
    p_bump.add_argument("--level", choices=["MAJOR", "MINOR", "PATCH"], default="PATCH")

    p_set = sub.add_parser("set", help="Set explicit version")
    p_set.add_argument("--skill", required=True)
    p_set.add_argument("--version", required=True)

    args = parser.parse_args()
    vm = VersionManager()

    if args.command == "read":
        v = vm.read_version(args.skill)
        print(v or "No version found")
    elif args.command == "bump":
        new_v = vm.bump_version(args.skill, args.level)
        print(f"Bumped to {new_v}")
    elif args.command == "set":
        vm.set_version(args.skill, args.version)
        print(f"Set to {args.version}")


if __name__ == "__main__":
    main()
