#!/usr/bin/env python3
"""
Bottleneck detection for dispatch.

Evaluates conditions across task state, MR status, and Jira data.
Writes findings to dispatch.db. Alerts Slack on CRITICAL/HIGH severity.
Does NOT call dispatch-notebook directly.

Usage (CLI):
    python scripts/bottleneck_detector.py scan [--severity CRITICAL|HIGH|MEDIUM] [--json]
    python scripts/bottleneck_detector.py status

Usage (module):
    from bottleneck_detector import BottleneckDetector
    detector = BottleneckDetector(store, notifier)
    results = detector.run()
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _parse_ts(ts):
    if not ts:
        return None
    try:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def _hours_since(ts_str):
    ts = _parse_ts(ts_str)
    if not ts:
        return None
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = now - ts
    return delta.total_seconds() / 3600


@dataclass
class BottleneckResult:
    severity: str
    type: str
    resource_id: str
    description: str
    already_open: bool = False


class BottleneckDetector:
    def __init__(self, store, notifier=None):
        self.store = store
        self.notifier = notifier

    def run(self):
        results = []
        for check in [
            self.check_pipeline_blocked,
            self.check_mr_review_stale,
            self.check_jira_comment_pending,
            self.check_mr_review_backlog,
            self.check_concurrent_tasks,
            self.check_repeated_deferral,
        ]:
            outcome = check()
            if outcome is None:
                continue
            if isinstance(outcome, list):
                results.extend(outcome)
            else:
                results.append(outcome)

        for r in results:
            self.write_finding(r)

        return results

    def check_pipeline_blocked(self):
        tasks = self.store.list_tasks(status="BLOCKED")
        for t in tasks:
            blocker = (t.get("blocker") or "").lower()
            if "pipeline" in blocker:
                hours = _hours_since(t.get("started_at"))
                if hours and hours > 2:
                    return BottleneckResult(
                        severity="CRITICAL",
                        type="pipeline_blocked",
                        resource_id=t["task_id"],
                        description=f"Pipeline blocked for {hours:.0f}h: {t.get('blocker')}",
                    )
        return None

    def check_mr_review_stale(self):
        tasks = self.store.list_tasks(status="IN_REVIEW")
        results = []
        for t in tasks:
            hours = _hours_since(t.get("started_at"))
            if hours and hours > 48:
                results.append(BottleneckResult(
                    severity="HIGH",
                    type="mr_review_stale",
                    resource_id=t["task_id"],
                    description=f"MR in review for {hours:.0f}h: {t['title']}",
                ))
        return results

    def check_jira_comment_pending(self):
        tasks = self.store.list_tasks(status="BLOCKED")
        results = []
        for t in tasks:
            blocker = (t.get("blocker") or "").lower()
            if any(kw in blocker for kw in ("comment", "response", "reply", "feedback")):
                hours = _hours_since(t.get("started_at"))
                if hours and hours > 24:
                    results.append(BottleneckResult(
                        severity="HIGH",
                        type="jira_comment_pending",
                        resource_id=t["task_id"],
                        description=f"Awaiting response for {hours:.0f}h: {t.get('blocker')}",
                    ))
        return results

    def check_mr_review_backlog(self):
        tasks = self.store.list_tasks(status="IN_REVIEW")
        if len(tasks) > 5:
            return BottleneckResult(
                severity="MEDIUM",
                type="mr_review_backlog",
                resource_id="operator",
                description=f"{len(tasks)} MRs pending review (threshold: 5)",
            )
        return None

    def check_concurrent_tasks(self):
        tasks = self.store.list_tasks(status="IN_PROGRESS")
        if len(tasks) > 3:
            return BottleneckResult(
                severity="MEDIUM",
                type="concurrent_tasks",
                resource_id="operator",
                description=f"{len(tasks)} tasks in progress simultaneously (threshold: 3)",
            )
        return None

    def check_repeated_deferral(self):
        rows = self.store.conn.execute(
            """SELECT * FROM tasks
               WHERE COALESCE(deferral_count, 0) > 2
                 AND status NOT IN ('COMPLETE', 'ABANDONED')"""
        ).fetchall()
        results = []
        for r in rows:
            results.append(BottleneckResult(
                severity="MEDIUM",
                type="repeated_deferral",
                resource_id=r["task_id"],
                description=f"Task deferred {r['deferral_count']} times: {r['title']}",
            ))
        return results

    def write_finding(self, result):
        if self._is_duplicate(result.type, result.resource_id):
            result.already_open = True
            return None
        bn = self.store.create_bottleneck(
            result.severity, result.type, result.resource_id, result.description
        )
        if result.severity in ("CRITICAL", "HIGH") and self.notifier:
            self.notifier.send_template("bottleneck_alert", {
                "severity": result.severity,
                "type": result.type,
                "resource_id": result.resource_id,
                "description": result.description,
            })
        return bn["bottleneck_id"]

    def _is_duplicate(self, type_, resource_id):
        open_bns = self.store.get_open_bottlenecks()
        return any(
            b["type"] == type_ and b["resource_id"] == resource_id
            for b in open_bns
        )


def main():
    parser = argparse.ArgumentParser(description="Dispatch bottleneck detector")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Run bottleneck scan")
    p_scan.add_argument("--severity", choices=["CRITICAL", "HIGH", "MEDIUM"])
    p_scan.add_argument("--json", action="store_true")

    sub.add_parser("status", help="Show open bottlenecks")

    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore
    from slack_notifier import SlackNotifier

    with StateStore() as store:
        store.schema_init()
        notifier = SlackNotifier(store)
        detector = BottleneckDetector(store, notifier)

        if args.command == "scan":
            results = detector.run()
            if args.severity:
                results = [r for r in results if r.severity == args.severity]
            if args.json:
                print(json.dumps([asdict(r) for r in results], indent=2))
            else:
                if not results:
                    print("No bottlenecks detected.")
                for r in results:
                    dup = " [DUPLICATE]" if r.already_open else ""
                    print(f"  [{r.severity}] {r.type}: {r.description}{dup}")
        elif args.command == "status":
            bns = store.get_open_bottlenecks()
            if not bns:
                print("No open bottlenecks.")
            for b in bns:
                print(f"  [{b['severity']}] {b['type']}: {b['description']}")


if __name__ == "__main__":
    main()
