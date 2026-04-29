#!/usr/bin/env python3
"""
MR cache lifecycle management.

Handles cache read/write, staleness checks, operator prompts,
and the --force-refresh / --use-cache override flags.

Cache files stored at: <skill_dir>/cache/mrs/ (team/personal)
                       <skill_dir>/cache/direct/ (per-MR direct mode)

Usage (CLI):
    python scripts/cache_manager.py status --scope team
    python scripts/cache_manager.py prune --days 30

Usage (module):
    from cache_manager import CacheManager
    cm = CacheManager()
    data = cm.read_cache("team")
"""

import argparse
import glob
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = SKILL_DIR / "cache"
MRS_CACHE_DIR = CACHE_DIR / "mrs"
DIRECT_CACHE_DIR = CACHE_DIR / "direct"


class CacheManager:
    """Manages MR list and per-MR cache files."""

    def __init__(self, stale_hours: int = 6, retain_days: int = 30):
        """
        Args:
            stale_hours: Hours after which cache is considered stale.
            retain_days: Days after which old cache files may be pruned.
        """
        self.stale_hours = stale_hours
        self.retain_days = retain_days

    def read_cache(self, scope: str) -> Optional[Dict[str, Any]]:
        """
        Read the most recent cache file for a given scope.

        Args:
            scope: "team" or "personal"

        Returns:
            Parsed JSON data from cache, or None if no cache exists.
        """
        path = self.latest_cache_path(scope)
        if not path:
            return None
        with open(path) as f:
            return json.load(f)

    def write_cache(self, scope: str, data: Any) -> Path:
        """
        Write data to a new timestamped cache file.

        Args:
            scope: "team" or "personal"
            data: JSON-serializable data to cache.

        Returns:
            Path to the written cache file.
        """
        MRS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"mrs_{ts}_{scope}.json"
        path = MRS_CACHE_DIR / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def write_direct_cache(self, project_path: str, iid: int, data: Any) -> Path:
        """
        Write per-MR cache for Direct Mode.

        Args:
            project_path: e.g. "namespace/project"
            iid: MR IID.
            data: Enriched MR data.

        Returns:
            Path to cache file.
        """
        safe_dir = hashlib.sha256(project_path.encode()).hexdigest()[:16]
        cache_dir = DIRECT_CACHE_DIR / safe_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"mr_{iid}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def is_stale(self, scope: str) -> tuple[bool, Optional[datetime], Optional[Path]]:
        """
        Check if the most recent cache for a scope is stale.

        Returns:
            (is_stale, cache_timestamp_or_None, cache_path_or_None)
        """
        path = self.latest_cache_path(scope)
        if not path:
            return (True, None, None)
        parts = path.stem.split("_")
        ts_str = f"{parts[1]}_{parts[2]}"
        ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
        age_hours = (datetime.now() - ts).total_seconds() / 3600
        return (age_hours > self.stale_hours, ts, path)

    def prompt_refresh(self, scope: str) -> bool:
        """
        If cache is stale, prompt operator: "Cache is X hours old. Refresh? [y/N]"

        Returns:
            True if operator wants a refresh, False to use existing cache.
        """
        stale, ts, path = self.is_stale(scope)
        if stale and ts:
            age = (datetime.now() - ts).total_seconds() / 3600
            print(f"Cache is {age:.1f} hours old (stale threshold: {self.stale_hours}h). Refreshing.", file=sys.stderr)
        return stale

    def prune(self, days: Optional[int] = None) -> int:
        """
        Remove cache files older than retain_days.

        Returns:
            Number of files pruned.
        """
        threshold = days or self.retain_days
        cutoff = datetime.now() - timedelta(days=threshold)
        count = 0
        for cache_dir in [MRS_CACHE_DIR, DIRECT_CACHE_DIR]:
            if not cache_dir.exists():
                continue
            for f in cache_dir.rglob("*.json"):
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime < cutoff:
                        f.unlink()
                        count += 1
                except OSError:
                    continue
        return count

    def latest_cache_path(self, scope: str) -> Optional[Path]:
        """Get path to most recent cache file for scope."""
        MRS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(MRS_CACHE_DIR.glob(f"mrs_*_{scope}.json"))
        return files[-1] if files else None


def main():
    parser = argparse.ArgumentParser(description="MR cache manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show cache status")
    p_status.add_argument("--scope", choices=["team", "personal"], required=True)

    p_prune = sub.add_parser("prune", help="Prune old cache files")
    p_prune.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    cm = CacheManager()
    if args.command == "status":
        stale, ts, path = cm.is_stale(args.scope)
        if path:
            age = (datetime.now() - ts).total_seconds() / 3600 if ts else 0
            print(f"Scope: {args.scope}")
            print(f"Path: {path}")
            print(f"Age: {age:.1f} hours")
            print(f"Stale: {stale}")
        else:
            print(f"No cache found for scope '{args.scope}'")
    elif args.command == "prune":
        count = cm.prune(days=args.days)
        print(f"Pruned {count} cache files")


if __name__ == "__main__":
    main()
