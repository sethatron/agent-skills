#!/usr/bin/env python3
"""
Cron job management for dispatch scheduled tasks.

Generates crontab entries from workflow.yaml, manages approval workflow,
and installs to user crontab. No entry is installed without an approval
record in dispatch.db.

Approval sequence: generate -> approve -> install

Usage (CLI):
    python scripts/cron_manager.py generate
    python scripts/cron_manager.py list [--pending | --installed]
    python scripts/cron_manager.py approve <job_id>
    python scripts/cron_manager.py install <job_id>
    python scripts/cron_manager.py install-all
    python scripts/cron_manager.py disable <job_id>
    python scripts/cron_manager.py remove <job_id>
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

STATE_ROOT = Path(os.path.expanduser("~/.zsh/dispatch"))
WORKFLOW_PATH = STATE_ROOT / "workflow.yaml"
SCRIPTS_DIR = Path(__file__).resolve().parent
CRON_MARKER = "# dispatch:managed"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


@dataclass
class CronJob:
    id: int
    name: str
    schedule: str
    command: str
    approved: bool
    approved_at: str | None
    installed_at: str | None
    enabled: bool


class CronManager:
    def __init__(self, store):
        self.store = store

    def generate(self):
        schedule = self._read_workflow_schedule()
        for name, entry in schedule.items():
            cron_expr = entry.get("cron", "")
            command = entry.get("command", "")
            if not cron_expr or not command:
                continue
            existing = self.store.conn.execute(
                "SELECT id FROM cron_jobs WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                self.store.conn.execute(
                    "UPDATE cron_jobs SET schedule = ?, command = ? WHERE name = ?",
                    (cron_expr, command, name),
                )
            else:
                self.store.conn.execute(
                    """INSERT INTO cron_jobs (name, schedule, command, approved, enabled)
                       VALUES (?, ?, ?, 0, 1)""",
                    (name, cron_expr, command),
                )
        self.store.conn.commit()

        all_jobs = self._all_jobs()
        lines = []
        for job in all_jobs:
            if job.approved and job.enabled:
                lines.append(self._build_crontab_line(job))
            else:
                lines.append(f"# [PENDING] {job.name}: {job.schedule} {job.command}")
        return "\n".join(lines)

    def list_pending(self):
        rows = self.store.conn.execute(
            "SELECT * FROM cron_jobs WHERE approved = 0 AND enabled = 1"
        ).fetchall()
        return [self._row_to_cronjob(r) for r in rows]

    def approve(self, job_id):
        job = self._get_job(job_id)
        if job.approved:
            return job
        now = _now()
        self.store.conn.execute(
            "UPDATE cron_jobs SET approved = 1, approved_at = ? WHERE id = ?",
            (now, job_id),
        )
        self.store.conn.commit()
        return self._get_job(job_id)

    def install(self, job_id):
        job = self._get_job(job_id)
        if not job.approved:
            raise ValueError(f"Cannot install unapproved job {job_id}. Approve first.")
        if not job.enabled:
            raise ValueError(f"Cannot install disabled job {job_id}.")
        current = self._get_current_crontab()
        filtered = self._remove_job_from_crontab(current, job.name)
        new_line = self._build_crontab_line(job)
        updated = filtered.rstrip("\n") + "\n" + new_line + "\n" if filtered.strip() else new_line + "\n"
        self._write_crontab(updated)
        now = _now()
        self.store.conn.execute(
            "UPDATE cron_jobs SET installed_at = ? WHERE id = ?", (now, job_id)
        )
        self.store.conn.commit()

    def install_all_approved(self):
        rows = self.store.conn.execute(
            "SELECT * FROM cron_jobs WHERE approved = 1 AND enabled = 1 AND installed_at IS NULL"
        ).fetchall()
        installed = []
        for r in rows:
            job = self._row_to_cronjob(r)
            self.install(job.id)
            installed.append(job.id)
        return installed

    def list_installed(self):
        rows = self.store.conn.execute(
            "SELECT * FROM cron_jobs WHERE installed_at IS NOT NULL AND enabled = 1"
        ).fetchall()
        return [self._row_to_cronjob(r) for r in rows]

    def disable(self, job_id):
        job = self._get_job(job_id)
        self.store.conn.execute(
            "UPDATE cron_jobs SET enabled = 0 WHERE id = ?", (job_id,)
        )
        self.store.conn.commit()
        if job.installed_at:
            current = self._get_current_crontab()
            filtered = self._remove_job_from_crontab(current, job.name)
            self._write_crontab(filtered)

    def remove(self, job_id):
        job = self._get_job(job_id)
        if job.installed_at:
            current = self._get_current_crontab()
            filtered = self._remove_job_from_crontab(current, job.name)
            self._write_crontab(filtered)
        self.store.conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        self.store.conn.commit()

    def _get_job(self, job_id):
        row = self.store.conn.execute(
            "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Cron job {job_id} not found")
        return self._row_to_cronjob(row)

    def _all_jobs(self):
        rows = self.store.conn.execute(
            "SELECT * FROM cron_jobs ORDER BY id"
        ).fetchall()
        return [self._row_to_cronjob(r) for r in rows]

    def _row_to_cronjob(self, row):
        return CronJob(
            id=row["id"],
            name=row["name"],
            schedule=row["schedule"],
            command=row["command"],
            approved=bool(row["approved"]),
            approved_at=row["approved_at"],
            installed_at=row["installed_at"],
            enabled=bool(row["enabled"]),
        )

    def _read_workflow_schedule(self):
        if not WORKFLOW_PATH.exists():
            return {}
        if yaml:
            with open(WORKFLOW_PATH) as f:
                data = yaml.safe_load(f) or {}
            return data.get("schedule", {})
        return {}

    def _build_crontab_line(self, job):
        return f"{job.schedule} cd {SCRIPTS_DIR} && python3 {job.command} {CRON_MARKER}:{job.name}"

    def _get_current_crontab(self):
        try:
            result = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True
            )
            return result.stdout if result.returncode == 0 else ""
        except Exception:
            return ""

    def _write_crontab(self, content):
        subprocess.run(
            ["crontab", "-"], input=content, text=True, check=True
        )

    def _remove_job_from_crontab(self, crontab_text, job_name):
        marker = f"{CRON_MARKER}:{job_name}"
        lines = [l for l in crontab_text.splitlines() if marker not in l]
        return "\n".join(lines) + "\n" if lines else ""


def main():
    parser = argparse.ArgumentParser(description="Dispatch cron manager")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("generate", help="Generate cron entries from workflow.yaml")

    p_list = sub.add_parser("list", help="List cron jobs")
    grp = p_list.add_mutually_exclusive_group()
    grp.add_argument("--pending", action="store_true")
    grp.add_argument("--installed", action="store_true")

    p_approve = sub.add_parser("approve", help="Approve a cron job")
    p_approve.add_argument("job_id", type=int)

    p_install = sub.add_parser("install", help="Install a cron job")
    p_install.add_argument("job_id", type=int)

    sub.add_parser("install-all", help="Install all approved jobs")

    p_disable = sub.add_parser("disable", help="Disable a cron job")
    p_disable.add_argument("job_id", type=int)

    p_remove = sub.add_parser("remove", help="Remove a cron job")
    p_remove.add_argument("job_id", type=int)

    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore

    with StateStore() as store:
        store.schema_init()
        mgr = CronManager(store)

        if args.command == "generate":
            text = mgr.generate()
            print(text)
        elif args.command == "list":
            if args.pending:
                jobs = mgr.list_pending()
            elif args.installed:
                jobs = mgr.list_installed()
            else:
                jobs = mgr._all_jobs()
            for j in jobs:
                status = "approved" if j.approved else "pending"
                installed = f" installed={j.installed_at}" if j.installed_at else ""
                enabled = "" if j.enabled else " [DISABLED]"
                print(f"  [{j.id}] {j.name}: {j.schedule} ({status}{installed}{enabled})")
        elif args.command == "approve":
            job = mgr.approve(args.job_id)
            print(f"Approved: {job.name}")
        elif args.command == "install":
            mgr.install(args.job_id)
            print(f"Installed job {args.job_id}")
        elif args.command == "install-all":
            ids = mgr.install_all_approved()
            print(f"Installed {len(ids)} jobs: {ids}")
        elif args.command == "disable":
            mgr.disable(args.job_id)
            print(f"Disabled job {args.job_id}")
        elif args.command == "remove":
            mgr.remove(args.job_id)
            print(f"Removed job {args.job_id}")


if __name__ == "__main__":
    main()
