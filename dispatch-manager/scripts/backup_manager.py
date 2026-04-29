#!/usr/bin/env python3
"""
Skill backup and restore manager.

Usage (CLI):
    python scripts/backup_manager.py create --skill dispatch
    python scripts/backup_manager.py list --skill dispatch
    python scripts/backup_manager.py restore --skill dispatch --version 1.0.0
    python scripts/backup_manager.py prune --days 30

Usage (module):
    from backup_manager import BackupManager
    bm = BackupManager()
    bm.create_backup("dispatch")
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from ecosystem_map import EcosystemMap
from version_manager import VersionManager

IGNORE_DIRS = {"backups", ".git", "__pycache__", "node_modules", ".beads"}


class BackupManager:

    def __init__(self, retention_days: int = 30):
        self.retention_days = retention_days
        self._eco = EcosystemMap()
        self._vm = VersionManager()

    def _backup_path(self, skill_name: str, version: str, timestamp: str) -> Path:
        skill_path = self._eco.resolve_path(skill_name)
        if not skill_path:
            raise ValueError(f"Skill '{skill_name}' not found")
        return skill_path / "backups" / f"{version}_{timestamp}"

    def create_backup(self, skill_name: str, version: Optional[str] = None) -> Path:
        skill_path = self._eco.resolve_path(skill_name)
        if not skill_path or not skill_path.exists():
            raise ValueError(f"Skill path not found for '{skill_name}'")

        version = version or self._vm.read_version(skill_name) or "0.0.0"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup_dir = self._backup_path(skill_name, version, timestamp)
        backup_dir.parent.mkdir(parents=True, exist_ok=True)

        def _ignore(directory, contents):
            return [c for c in contents if c in IGNORE_DIRS]

        shutil.copytree(skill_path, backup_dir, ignore=_ignore)
        return backup_dir

    def list_backups(self, skill_name: Optional[str] = None) -> List[Dict]:
        results = []
        all_skills = self._eco._all_skills()
        targets = {skill_name: all_skills[skill_name]} if skill_name else all_skills

        for name, entry in targets.items():
            skill_path = Path(os.path.expanduser(entry["path"]))
            backups_dir = skill_path / "backups"
            if not backups_dir.exists():
                continue
            for d in sorted(backups_dir.iterdir()):
                if not d.is_dir():
                    continue
                m = re.match(r'^(.+?)_(\d{8}T\d{6})$', d.name)
                if not m:
                    continue
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                results.append({
                    "skill": name,
                    "version": m.group(1),
                    "timestamp": m.group(2),
                    "path": str(d),
                    "size_bytes": size,
                })
        return results

    def restore_backup(self, skill_name: str, version: Optional[str] = None,
                       timestamp: Optional[str] = None) -> Path:
        backups = self.list_backups(skill_name)
        if not backups:
            raise ValueError(f"No backups found for '{skill_name}'")

        match = None
        for b in reversed(backups):
            if version and b["version"] != version:
                continue
            if timestamp and b["timestamp"] != timestamp:
                continue
            match = b
            break

        if not match:
            raise ValueError(f"No matching backup for '{skill_name}' v={version} t={timestamp}")

        self.create_backup(skill_name, version="pre-restore")

        skill_path = self._eco.resolve_path(skill_name)
        backup_path = Path(match["path"])

        for item in skill_path.iterdir():
            if item.name in IGNORE_DIRS or item.name == "backups":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for item in backup_path.iterdir():
            dest = skill_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        return backup_path

    def prune_old_backups(self, days: Optional[int] = None) -> List[Path]:
        days = days or self.retention_days
        cutoff = datetime.now(timezone.utc)
        pruned = []

        for b in self.list_backups():
            try:
                ts = datetime.strptime(b["timestamp"], "%Y%m%dT%H%M%S")
                ts = ts.replace(tzinfo=timezone.utc)
                age_days = (cutoff - ts).days
                if age_days > days:
                    shutil.rmtree(b["path"])
                    pruned.append(Path(b["path"]))
            except (ValueError, OSError):
                continue

        return pruned


def main():
    parser = argparse.ArgumentParser(description="Skill backup manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create skill backup")
    p_create.add_argument("--skill", required=True)
    p_create.add_argument("--version", help="Override version label")

    p_list = sub.add_parser("list", help="List available backups")
    p_list.add_argument("--skill", help="Filter by skill name")

    p_restore = sub.add_parser("restore", help="Restore from backup")
    p_restore.add_argument("--skill", required=True)
    p_restore.add_argument("--version", help="Target version")
    p_restore.add_argument("--timestamp", help="Specific backup timestamp")

    p_prune = sub.add_parser("prune", help="Remove old backups")
    p_prune.add_argument("--days", type=int, default=30)

    args = parser.parse_args()
    bm = BackupManager()

    if args.command == "create":
        path = bm.create_backup(args.skill, version=args.version)
        print(f"Backup created: {path}")
    elif args.command == "list":
        backups = bm.list_backups(skill_name=getattr(args, "skill", None))
        for b in backups:
            print(f"  {b['skill']} v{b['version']} @ {b['timestamp']} ({b['size_bytes']} bytes)")
    elif args.command == "restore":
        path = bm.restore_backup(args.skill, version=args.version, timestamp=args.timestamp)
        print(f"Restored from: {path}")
    elif args.command == "prune":
        pruned = bm.prune_old_backups(days=args.days)
        print(f"Pruned {len(pruned)} backup(s)")


if __name__ == "__main__":
    main()
