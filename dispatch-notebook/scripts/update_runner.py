#!/usr/bin/env python3
"""
Notebook update orchestration — 9-step daily update sequence.

Usage:
    python scripts/update_runner.py [--auto] [--tier tier1|tier2|tier3] [--dry-run]
"""

import argparse
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config" / "notebook.yaml"
TIER1_MANIFEST = SKILL_DIR / "config" / "tier1_manifest.yaml"
QUERIES_DIR = SKILL_DIR / "queries"
STATE_ROOT = Path.home() / ".zsh" / "dispatch"
NOTEBOOK_DIR = STATE_ROOT / "notebook"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from nlm_runner import NLMRunner, NLMError
from source_manager import SourceManager
from source_renderer import SourceRenderer
from query_runner import QueryRunner
from briefing_loader import BriefingLoader


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


def _log(step: int, msg: str) -> None:
    print(f"  [{step}/9] {msg}")


def _date_range(days_back: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    dates = []
    for i in range(days_back):
        d = today - timedelta(days=i)
        dates.append(d.isoformat())
    return dates


def _find_files(base: Path, dates: list[str], filename: str) -> list[Path]:
    found = []
    for date_str in dates:
        parts = date_str.split("-")
        if len(parts) != 3:
            continue
        path = base / parts[0] / parts[1] / parts[2] / filename
        if path.exists():
            found.append(path)
    return found


class UpdateRunner:
    def __init__(self, config_path: Optional[Path] = None, dry_run: bool = False):
        self.config_path = config_path or CONFIG_PATH
        self.dry_run = dry_run
        self._config = yaml.safe_load(self.config_path.read_text()) if self.config_path.exists() else {}
        self._nlm = NLMRunner()
        self._sources = SourceManager(config_path=self.config_path)
        self._renderer = SourceRenderer()
        self._errors = []
        self._start_time = None
        self._stats = {
            "tier1": {"added": 0, "unchanged": 0, "errored": 0},
            "tier2": {"added": 0, "unchanged": 0, "errored": 0},
            "tier3": {"added": 0, "unchanged": 0, "errored": 0},
            "pruned": 0,
            "reconciliation": {},
            "briefing": None,
        }

    def execute(self) -> dict:
        self._start_time = time.time()
        self.step_01_auth_check()

        steps = [
            self.step_02_inventory_reconciliation,
            self.step_03_tier2_update,
            self.step_04_tier3_update,
            self.step_05_tier1_update,
            self.step_06_prune_expired,
            self.step_07_generate_briefing,
        ]
        for step_fn in steps:
            try:
                step_fn()
            except Exception as e:
                self._errors.append(f"{step_fn.__name__}: {e}")

        try:
            self.step_08_slack_notify(self._stats)
        except Exception as e:
            self._errors.append(f"step_08_slack_notify: {e}")

        try:
            self.step_09_write_update_log(self._stats)
        except Exception as e:
            self._errors.append(f"step_09_write_update_log: {e}")

        return {**self._stats, "errors": self._errors}

    def step_01_auth_check(self) -> bool:
        _log(1, "Checking authentication...")
        try:
            from auth_guard import ensure_auth, notify_auth_failure
            if ensure_auth(self._nlm):
                _log(1, "Authenticated")
                return True
            notify_auth_failure()
        except ImportError:
            if self._nlm.login_check():
                _log(1, "Authenticated")
                return True
        raise RuntimeError("NotebookLM authentication failed. Run: nlm login")

    def step_02_inventory_reconciliation(self) -> dict:
        _log(2, "Reconciling inventory...")
        if self.dry_run:
            _log(2, "DRY RUN: skipping reconciliation")
            return {}
        inv = self._sources.load_inventory()
        live = self._sources._runner.source_list(self._sources._alias)
        result = self._sources.reconcile(live, inv)
        self._stats["reconciliation"] = result
        missing_r = len(result.get("missing_remote", []))
        missing_l = len(result.get("missing_local", []))
        _log(2, f"Synced: {len(result.get('synced', []))}, "
                f"missing remote: {missing_r}, missing local: {missing_l}")
        return result

    def step_03_tier2_update(self) -> dict:
        _log(3, "Updating TIER 2 (Optimus reports)...")
        tier2_days = self._config.get("tier2_days", 30)
        tier2_max = self._config.get("tier2_max", 20)
        dates = _date_range(tier2_days)
        reports = _find_files(STATE_ROOT, dates, "optimus_report.md")

        if not reports:
            _log(3, "No Optimus reports found")
            return self._stats["tier2"]

        reports = reports[:tier2_max]
        stats = self._stats["tier2"]

        for path in reports:
            date_parts = path.parts[-4:-1]
            title = f"Optimus Report {'-'.join(date_parts)}"
            try:
                content = self._renderer.render_optimus_report(path)
                if self.dry_run:
                    _log(3, f"DRY RUN: would upload {title}")
                    continue
                old_hash = self._get_existing_hash(title)
                new_hash = self._sources.get_content_hash(content)
                if old_hash == new_hash:
                    stats["unchanged"] += 1
                    continue
                self._sources.upload_source(content, title, "tier2", str(path))
                stats["added"] += 1
            except Exception as e:
                stats["errored"] += 1
                self._errors.append(f"tier2 {title}: {e}")

        _log(3, f"TIER 2: {stats['added']} added, {stats['unchanged']} unchanged, {stats['errored']} errored")
        return stats

    def step_04_tier3_update(self) -> dict:
        _log(4, "Updating TIER 3 (session summaries)...")
        tier3_days = self._config.get("tier3_days", 7)
        tier3_max = self._config.get("tier3_max", 12)
        dates = _date_range(tier3_days)
        sessions = _find_files(STATE_ROOT, dates, "session.yaml")

        if not sessions:
            _log(4, "No session files found")
            return self._stats["tier3"]

        sessions = sessions[:tier3_max]
        stats = self._stats["tier3"]

        for path in sessions:
            date_parts = path.parts[-4:-1]
            title = f"Session Summary {'-'.join(date_parts)}"
            try:
                data = yaml.safe_load(path.read_text()) or {}
                content = self._renderer.render_session_summary(data)
                if self.dry_run:
                    _log(4, f"DRY RUN: would upload {title}")
                    continue
                old_hash = self._get_existing_hash(title)
                new_hash = self._sources.get_content_hash(content)
                if old_hash == new_hash:
                    stats["unchanged"] += 1
                    continue
                self._sources.upload_source(content, title, "tier3", str(path))
                stats["added"] += 1
            except Exception as e:
                stats["errored"] += 1
                self._errors.append(f"tier3 {title}: {e}")

        _log(4, f"TIER 3: {stats['added']} added, {stats['unchanged']} unchanged, {stats['errored']} errored")
        return stats

    def step_05_tier1_update(self) -> dict:
        _log(5, "Updating TIER 1 (framework core)...")
        if not TIER1_MANIFEST.exists():
            _log(5, "SKIP: tier1_manifest.yaml not found")
            return self._stats["tier1"]

        manifest = yaml.safe_load(TIER1_MANIFEST.read_text()) or {}
        sources = manifest.get("sources", [])
        stats = self._stats["tier1"]

        for entry in sources:
            title = entry.get("title", "")
            path = Path(entry.get("path", ""))
            render_type = entry.get("render", "skill_md")

            if not path.exists():
                stats["errored"] += 1
                self._errors.append(f"tier1 {title}: file not found at {path}")
                continue

            try:
                if render_type == "yaml":
                    content = self._renderer.render_yaml_file(path, title)
                else:
                    content = self._renderer.render_skill_md(path)

                if self.dry_run:
                    _log(5, f"DRY RUN: would upload {title}")
                    continue

                old_hash = self._get_existing_hash(title)
                new_hash = self._sources.get_content_hash(content)
                if old_hash == new_hash:
                    stats["unchanged"] += 1
                    continue

                self._sources.upload_source(content, title, "tier1", str(path))
                stats["added"] += 1
            except Exception as e:
                stats["errored"] += 1
                self._errors.append(f"tier1 {title}: {e}")

        _log(5, f"TIER 1: {stats['added']} added, {stats['unchanged']} unchanged, {stats['errored']} errored")
        return stats

    def step_06_prune_expired(self) -> list[str]:
        _log(6, "Pruning expired sources...")
        if self.dry_run:
            _log(6, "DRY RUN: skipping prune")
            return []
        deleted = self._sources.prune_expired()
        self._stats["pruned"] = len(deleted)
        _log(6, f"Pruned {len(deleted)} expired sources")
        return deleted

    def step_07_generate_briefing(self) -> str:
        _log(7, "Generating morning briefing...")
        queries_path = QUERIES_DIR / "morning_briefing.yaml"
        if not queries_path.exists():
            _log(7, "SKIP: morning_briefing.yaml not found")
            return ""

        if self.dry_run:
            _log(7, "DRY RUN: skipping briefing generation")
            return ""

        qr = QueryRunner(config_path=self.config_path)
        results = qr.run_query_set(queries_path)
        bl = BriefingLoader(config_path=self.config_path)
        path = bl.generate_briefing(results)
        self._stats["briefing"] = path
        _log(7, f"Briefing written to {path}")
        return path

    def step_08_slack_notify(self, stats: dict) -> None:
        _log(8, "Sending notification...")
        total_added = sum(stats.get(t, {}).get("added", 0) for t in ("tier1", "tier2", "tier3"))
        total_errors = sum(stats.get(t, {}).get("errored", 0) for t in ("tier1", "tier2", "tier3"))
        pruned = stats.get("pruned", 0)
        print(f"[NOTEBOOK] Update complete: {total_added} refreshed, {pruned} pruned, {total_errors} errors")

    def step_09_write_update_log(self, stats: dict) -> Path:
        _log(9, "Writing update log...")
        log_path = NOTEBOOK_DIR / "update_log.yaml"
        duration = time.time() - self._start_time if self._start_time else 0

        entry = {
            "update_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notebook_alias": self._config.get("notebook_alias", "dispatch"),
            "duration_seconds": round(duration, 1),
            "sources_added": sum(stats.get(t, {}).get("added", 0) for t in ("tier1", "tier2", "tier3")),
            "sources_unchanged": sum(stats.get(t, {}).get("unchanged", 0) for t in ("tier1", "tier2", "tier3")),
            "sources_errored": sum(stats.get(t, {}).get("errored", 0) for t in ("tier1", "tier2", "tier3")),
            "sources_pruned": stats.get("pruned", 0),
            "tier_summary": {
                "tier1": stats.get("tier1", {}),
                "tier2": stats.get("tier2", {}),
                "tier3": stats.get("tier3", {}),
            },
            "briefing_path": stats.get("briefing"),
            "errors": self._errors if self._errors else None,
        }

        existing = []
        if log_path.exists():
            try:
                existing = yaml.safe_load(log_path.read_text()) or []
                if not isinstance(existing, list):
                    existing = [existing]
            except yaml.YAMLError:
                existing = []

        existing.append(entry)
        _atomic_write(log_path, yaml.dump(existing, default_flow_style=False, sort_keys=False))
        _log(9, f"Update log written to {log_path}")
        return log_path

    def _get_existing_hash(self, title: str) -> Optional[str]:
        inv = self._sources.load_inventory()
        for entry in inv.get("sources", []):
            if entry.get("title") == title:
                return entry.get("content_hash")
        return None


def main():
    parser = argparse.ArgumentParser(description="Notebook update orchestration")
    parser.add_argument("--auto", action="store_true", help="Run full update without prompts")
    parser.add_argument("--tier", choices=["tier1", "tier2", "tier3"], help="Update single tier")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    args = parser.parse_args()

    runner = UpdateRunner(dry_run=args.dry_run)
    if args.tier:
        tier_map = {
            "tier1": "step_05_tier1_update",
            "tier2": "step_03_tier2_update",
            "tier3": "step_04_tier3_update",
        }
        getattr(runner, tier_map[args.tier])()
    else:
        result = runner.execute()
        errors = result.get("errors", [])
        if errors:
            print(f"\n{len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")


if __name__ == "__main__":
    main()
