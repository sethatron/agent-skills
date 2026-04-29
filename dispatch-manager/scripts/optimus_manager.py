#!/usr/bin/env python3
"""
Optimus finding lifecycle manager.

Usage (CLI):
    python scripts/optimus_manager.py ingest <report-path>
    python scripts/optimus_manager.py list [--status PENDING]
    python scripts/optimus_manager.py implement <finding-id>
    python scripts/optimus_manager.py decline <finding-id> --reason "..."

Usage (module):
    from optimus_manager import OptimusManager
    om = OptimusManager()
    om.ingest_findings("~/.zsh/dispatch/2026/04/01/optimus_report.md")
"""

import argparse
import hashlib
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
FINDINGS_PATH = SKILL_DIR / "optimus" / "findings.yaml"
RESOLVED_FINDINGS_PATH = Path(os.path.expanduser("~/.zsh/dispatch/optimus/resolved_findings.md"))
STATE_STORE_PATH = Path(__file__).resolve().parents[2] / "dispatch" / "scripts"

FINDING_STATES = ["PENDING", "REVIEWING", "ACCEPTED", "IN_PROGRESS",
                  "IMPLEMENTED", "DECLINED", "DEFERRED"]

FINDING_CATEGORIES = ["workflow_gap", "tooling", "process", "automation",
                      "mcp_integration", "new_skill", "coherency", "performance"]


def _get_store():
    if str(STATE_STORE_PATH) not in sys.path:
        sys.path.insert(0, str(STATE_STORE_PATH))
    from state_store import StateStore
    store = StateStore()
    store.schema_init()
    return store

VALID_TRANSITIONS = {
    "PENDING": ["REVIEWING", "DECLINED", "DEFERRED"],
    "REVIEWING": ["ACCEPTED", "DECLINED", "DEFERRED"],
    "ACCEPTED": ["IN_PROGRESS", "DECLINED", "DEFERRED"],
    "IN_PROGRESS": ["IMPLEMENTED", "DECLINED", "DEFERRED"],
    "IMPLEMENTED": [],
    "DECLINED": [],
    "DEFERRED": ["PENDING"],
}

PLAN_TEMPLATES = {
    "workflow_gap": "Add or modify workflow.yaml step",
    "tooling": "Install tool and update configuration",
    "process": "Modify bottleneck rule or Slack template",
    "automation": "Generate cron job candidate",
    "mcp_integration": "Wire MCP tool into skill",
    "new_skill": "Invoke skill authoring workflow",
}


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


def _now():
    return datetime.now(timezone.utc).isoformat()


def _generate_id(title: str, category: str) -> str:
    h = hashlib.sha256(f"{title}:{category}".encode()).hexdigest()[:6]
    return f"OPT-{h}"


class OptimusManager:

    def __init__(self, findings_path: Optional[Path] = None):
        self.findings_path = findings_path or FINDINGS_PATH

    def _load_findings(self) -> List[Dict]:
        if not self.findings_path.exists():
            return []
        data = yaml.safe_load(self.findings_path.read_text())
        return data if isinstance(data, list) else []

    def _save_findings(self, findings: List[Dict]) -> None:
        _atomic_write(self.findings_path,
                      yaml.dump(findings, default_flow_style=False, sort_keys=False))

    def ingest_findings(self, report_path: str) -> List[Dict]:
        report = Path(os.path.expanduser(report_path))
        if not report.exists():
            raise FileNotFoundError(f"Report not found: {report}")

        content = report.read_text()
        frontmatter = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1]) or {}

        existing = self._load_findings()
        existing_ids = {f["id"] for f in existing}
        new_findings = []

        by_category = frontmatter.get("findings_by_category", {})
        if not by_category:
            by_category = frontmatter.get("findings", {})

        for category, findings in by_category.items():
            if not isinstance(findings, list):
                continue
            for f in findings:
                if isinstance(f, str):
                    f = {"title": f}
                fid = f.get("id") or _generate_id(f.get("title", ""), category)
                if fid in existing_ids:
                    continue

                entry = {
                    "id": fid,
                    "title": f.get("title", "Untitled"),
                    "category": category if category in FINDING_CATEGORIES else "process",
                    "severity": f.get("severity", "MEDIUM"),
                    "description": f.get("description", ""),
                    "recommendation": f.get("recommendation", ""),
                    "status": "PENDING",
                    "ingested_at": _now(),
                    "source_report": str(report),
                }
                existing.append(entry)
                new_findings.append(entry)
                existing_ids.add(fid)

        self._save_findings(existing)

        try:
            store = _get_store()
            for f in new_findings:
                store.insert_finding(
                    finding_id=f["id"], title=f["title"],
                    category=f["category"], severity=f["severity"],
                    description=f.get("description", ""),
                    recommendation=f.get("recommendation"),
                    affected_skill=f.get("affected_skill"),
                )
                if f["severity"] in ("CRITICAL", "HIGH"):
                    store.emit_event("finding_created", "dispatch-manager", {
                        "finding_id": f["id"],
                        "title": f["title"],
                        "severity": f["severity"],
                        "category": f["category"],
                        "affected_skill": f.get("affected_skill", "ecosystem"),
                    })
            store.export_findings(FINDINGS_PATH)
            store.close()
        except Exception:
            pass

        return new_findings

    def list_findings(self, status: Optional[str] = None,
                      category: Optional[str] = None) -> List[Dict]:
        findings = self._load_findings()
        if status:
            findings = [f for f in findings if f.get("status") == status]
        if category:
            findings = [f for f in findings if f.get("category") == category]
        return findings

    def get_finding(self, finding_id: str) -> Optional[Dict]:
        for f in self._load_findings():
            if f.get("id") == finding_id:
                return f
        return None

    def transition_finding(self, finding_id: str, new_status: str) -> Dict:
        if new_status not in FINDING_STATES:
            raise ValueError(f"Invalid status: {new_status}")

        findings = self._load_findings()
        for f in findings:
            if f.get("id") == finding_id:
                current = f.get("status", "PENDING")
                allowed = VALID_TRANSITIONS.get(current, [])
                if new_status not in allowed:
                    raise ValueError(
                        f"Cannot transition {finding_id} from {current} to {new_status}. "
                        f"Allowed: {allowed}")
                f["status"] = new_status
                f["transitioned_at"] = _now()
                self._save_findings(findings)
                return f

        raise ValueError(f"Finding '{finding_id}' not found")

    def mark_implemented(self, finding_id: str, version: str,
                         skills_affected: List[str]) -> None:
        finding = self.transition_finding(finding_id, "IMPLEMENTED")
        finding["implemented_version"] = version
        finding["skills_affected"] = skills_affected
        findings = self._load_findings()
        for i, f in enumerate(findings):
            if f["id"] == finding_id:
                findings[i] = finding
                break
        self._save_findings(findings)

        entry = (
            f"\n## {finding_id}: {finding.get('title', '')}\n"
            f"Implemented in v{version}. Skills: {', '.join(skills_affected)}. "
            f"Date: {_now()}\n"
        )
        self._append_resolved(entry)

        try:
            store = _get_store()
            summary = f"Implemented in v{version}. Skills: {', '.join(skills_affected)}"
            db_finding = store.get_finding(finding_id)
            beads_id = db_finding.get("beads_issue_id") if db_finding else None
            store.update_finding_status(finding_id, "IMPLEMENTED", summary)
            store.emit_event("finding_status_changed", "dispatch-manager", {
                "finding_id": finding_id,
                "old_status": "IN_PROGRESS",
                "new_status": "IMPLEMENTED",
                "resolution_summary": summary,
                "beads_issue_id": beads_id,
            })
            store.export_findings(FINDINGS_PATH)
            store.export_findings(RESOLVED_FINDINGS_PATH, status_filter="IMPLEMENTED")
            store.close()
        except Exception:
            pass

    def decline_finding(self, finding_id: str, reason: str) -> None:
        finding = self.transition_finding(finding_id, "DECLINED")
        finding["decline_reason"] = reason
        findings = self._load_findings()
        for i, f in enumerate(findings):
            if f["id"] == finding_id:
                findings[i] = finding
                break
        self._save_findings(findings)

        entry = (
            f"\n## {finding_id}: {finding.get('title', '')}\n"
            f"Declined: {reason}. Date: {_now()}\n"
        )
        self._append_resolved(entry)

        try:
            store = _get_store()
            db_finding = store.get_finding(finding_id)
            beads_id = db_finding.get("beads_issue_id") if db_finding else None
            store.update_finding_status(finding_id, "DECLINED", reason)
            store.emit_event("finding_status_changed", "dispatch-manager", {
                "finding_id": finding_id,
                "old_status": "PENDING",
                "new_status": "DECLINED",
                "resolution_summary": reason,
                "beads_issue_id": beads_id,
            })
            store.export_findings(FINDINGS_PATH)
            store.close()
        except Exception:
            pass

    def build_implementation_plan(self, finding_id: str) -> Dict:
        finding = self.get_finding(finding_id)
        if not finding:
            raise ValueError(f"Finding '{finding_id}' not found")

        category = finding.get("category", "process")
        plan_type = PLAN_TEMPLATES.get(category, "Manual implementation")

        return {
            "finding_id": finding_id,
            "title": finding.get("title", ""),
            "category": category,
            "plan_type": plan_type,
            "summary": f"{plan_type}: {finding.get('recommendation', finding.get('description', ''))}",
            "steps": [
                f"1. Review finding: {finding.get('title', '')}",
                f"2. Approach: {plan_type}",
                f"3. Apply change per recommendation",
                f"4. Run DSI + contract validation",
                f"5. Mark implemented with version cross-reference",
            ],
        }

    def _append_resolved(self, entry: str) -> None:
        RESOLVED_FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if RESOLVED_FINDINGS_PATH.exists():
            existing = RESOLVED_FINDINGS_PATH.read_text()
        else:
            existing = "# Resolved Findings\n"
        _atomic_write(RESOLVED_FINDINGS_PATH, existing + entry)


def main():
    parser = argparse.ArgumentParser(description="Optimus finding manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest findings from Optimus report")
    p_ingest.add_argument("report_path")

    p_list = sub.add_parser("list", help="List findings")
    p_list.add_argument("--status", choices=FINDING_STATES)
    p_list.add_argument("--category", choices=FINDING_CATEGORIES)

    p_impl = sub.add_parser("implement", help="Build implementation plan")
    p_impl.add_argument("finding_id")

    p_decline = sub.add_parser("decline", help="Decline a finding")
    p_decline.add_argument("finding_id")
    p_decline.add_argument("--reason", required=True)

    args = parser.parse_args()
    om = OptimusManager()

    if args.command == "ingest":
        findings = om.ingest_findings(args.report_path)
        print(f"Ingested {len(findings)} new finding(s)")
    elif args.command == "list":
        findings = om.list_findings(status=getattr(args, "status", None),
                                    category=getattr(args, "category", None))
        if not findings:
            print("No findings.")
        for f in findings:
            print(f"  [{f['status']}] {f['id']}: {f.get('title', '')}")
    elif args.command == "implement":
        plan = om.build_implementation_plan(args.finding_id)
        print(plan.get("summary", "Plan generated."))
    elif args.command == "decline":
        om.decline_finding(args.finding_id, args.reason)
        print("Finding declined.")


if __name__ == "__main__":
    main()
