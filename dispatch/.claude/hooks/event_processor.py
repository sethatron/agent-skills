#!/usr/bin/env python3
"""
Event bus consumer. Processes pending events from dispatch.db.

Called from post_bash/post_edit/post_write hooks after each tool execution.
Processes up to 10 pending events per invocation. Exits immediately if queue empty.
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~/.zsh/dispatch/dispatch.db"))
DISPATCH_DIR = Path(os.path.expanduser("~/.zsh/dispatch"))

SEVERITY_TO_PRIORITY = {
    "CRITICAL": "0",
    "HIGH": "1",
    "MEDIUM": "2",
    "LOW": "3",
}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _run_br(args, capture=True):
    try:
        result = subprocess.run(
            ["br"] + args,
            cwd=str(DISPATCH_DIR),
            capture_output=capture,
            text=True,
            timeout=30,
        )
        return result
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": str(e)})()


def _extract_issue_id(br_output):
    match = re.search(r"(dsp-[\w.]+)", br_output)
    return match.group(1) if match else None


def handle_beads_board_mutated(payload, conn):
    result = _run_br(["sync", "--flush-only"])
    if result.returncode != 0:
        raise RuntimeError(f"br sync failed: {result.stderr}")


def handle_grade_evaluated(payload, conn):
    trend = payload.get("trend")
    skill = payload.get("skill_slug", "unknown")
    grade = payload.get("overall_grade", "?")

    if trend == "regression":
        priority = "0" if grade in ("D", "F") else "1"
        _run_br([
            "create", f"Grade regression: {skill} dropped to {grade}",
            "-t", "bug", "-p", priority,
            "-l", f"scope:{skill},kind:bug,source:harness",
        ])
    elif trend == "improvement":
        result = _run_br([
            "search", f"scope:{skill} kind:bug source:entropy source:harness",
        ])
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                issue_id = _extract_issue_id(line)
                if issue_id:
                    _run_br(["close", issue_id, "-r", f"Grade improved to {grade}"])


def handle_finding_created(payload, conn):
    severity = payload.get("severity", "MEDIUM")
    priority = SEVERITY_TO_PRIORITY.get(severity, "2")
    title = payload.get("title", "Untitled finding")
    skill = payload.get("affected_skill", "ecosystem")
    finding_id = payload.get("finding_id", "")

    result = _run_br([
        "create", title,
        "-t", "task", "-p", priority,
        "-l", f"scope:{skill},source:optimus,kind:improvement",
        "--external-ref", finding_id,
        "--silent",
    ])
    if result.returncode == 0:
        issue_id = result.stdout.strip().split("\n")[0]
        if issue_id and finding_id:
            try:
                conn.execute(
                    "UPDATE optimus_findings SET beads_issue_id = ? WHERE finding_id = ?",
                    (issue_id, finding_id),
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass


def handle_finding_status_changed(payload, conn):
    new_status = payload.get("new_status")
    beads_id = payload.get("beads_issue_id")
    summary = payload.get("resolution_summary", "Implemented")

    if not beads_id:
        return

    if new_status == "IMPLEMENTED":
        _run_br(["close", beads_id, "-r", summary])
    elif new_status == "DECLINED":
        _run_br(["close", beads_id, "-r", "Finding declined"])


def handle_circuit_breaker_tripped(payload, conn):
    component = payload.get("component", "unknown")
    error = payload.get("error", "")
    print(
        f"[CIRCUIT BREAKER] {component} is degraded: {error[:100]}",
        file=sys.stderr,
    )


def handle_circuit_breaker_recovered(payload, conn):
    component = payload.get("component", "unknown")
    print(f"[RECOVERED] {component} is healthy", file=sys.stderr)


def handle_artifact_updated(payload, conn):
    origin_path = payload.get("path", "")
    if not origin_path or not Path(origin_path).exists():
        return

    content = Path(origin_path).read_text()
    new_hash = hashlib.sha256(content.encode()).hexdigest()

    row = conn.execute(
        "SELECT content_hash FROM notebook_sources WHERE origin_path = ?",
        (origin_path,),
    ).fetchone()

    if row and row[0] == new_hash:
        return

    try:
        sm_path = str(Path(__file__).resolve().parents[2] / "dispatch-notebook" / "scripts")
        if sm_path not in sys.path:
            sys.path.insert(0, sm_path)
        from source_manager import SourceManager
        sm = SourceManager()
        title = payload.get("title", Path(origin_path).stem)
        tier = payload.get("tier", "tier2")
        sm.upload_source(content, title, tier, origin_path=origin_path)
    except Exception as e:
        conn.execute(
            """INSERT INTO events (event_type, source_skill, payload_json, emitted_at)
               VALUES ('source_upload_failed', 'dispatch-notebook', ?, ?)""",
            (json.dumps({"origin_path": origin_path, "error": str(e)[:200]}), _now()),
        )
        conn.commit()
        raise


def handle_session_ended(payload, conn):
    result = _run_br(["sync", "--flush-only"])
    if result.returncode != 0:
        print(f"[WARN] EOD beads sync failed: {result.stderr}", file=sys.stderr)


def handle_source_upload_failed(payload, conn):
    pass


def handle_contract_updated(payload, conn):
    try:
        cv_path = str(Path(__file__).resolve().parents[2] / "dispatch-manager" / "scripts")
        if cv_path not in sys.path:
            sys.path.insert(0, cv_path)
        from contract_validator import ContractValidator
        cv = ContractValidator()
        cv.validate_all()
    except Exception:
        pass


def handle_skill_registered(payload, conn):
    skill = payload.get("skill_slug", "")
    path = payload.get("path", "")
    if skill:
        _run_br([
            "create", f"[EPIC] {skill} skill integration",
            "-t", "epic", "-p", "2",
            "-l", f"scope:{skill},kind:new-feature,source:operator",
        ])


def handle_skill_upgraded(payload, conn):
    skill = payload.get("skill_slug", "")
    if not skill:
        return
    result = _run_br(["search", f"scope:{skill} kind:stub phase:stub"])
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            issue_id = _extract_issue_id(line)
            if issue_id:
                _run_br(["close", issue_id, "-r", f"Implemented in {skill} upgrade"])


EVENT_HANDLERS = {
    "beads_board_mutated": handle_beads_board_mutated,
    "grade_evaluated": handle_grade_evaluated,
    "finding_created": handle_finding_created,
    "finding_status_changed": handle_finding_status_changed,
    "circuit_breaker_tripped": handle_circuit_breaker_tripped,
    "circuit_breaker_recovered": handle_circuit_breaker_recovered,
    "artifact_updated": handle_artifact_updated,
    "session_ended": handle_session_ended,
    "source_upload_failed": handle_source_upload_failed,
    "contract_updated": handle_contract_updated,
    "skill_registered": handle_skill_registered,
    "skill_upgraded": handle_skill_upgraded,
}


def process_pending_events(max_events=10):
    if not DB_PATH.exists():
        return 0

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
    except Exception:
        return 0

    processed = 0
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE status = 'PENDING' ORDER BY id LIMIT ?",
            (max_events,),
        ).fetchall()

        if not rows:
            conn.close()
            return 0

        for row in rows:
            event_id = row["id"]
            event_type = row["event_type"]
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}

            conn.execute(
                "UPDATE events SET status = 'PROCESSING', processor = 'event_processor' WHERE id = ?",
                (event_id,),
            )
            conn.commit()

            handler = EVENT_HANDLERS.get(event_type)
            if not handler:
                conn.execute(
                    "UPDATE events SET status = 'PROCESSED', processed_at = ? WHERE id = ?",
                    (_now(), event_id),
                )
                conn.commit()
                processed += 1
                continue

            try:
                handler(payload, conn)
                conn.execute(
                    "UPDATE events SET status = 'PROCESSED', processed_at = ? WHERE id = ?",
                    (_now(), event_id),
                )
                conn.commit()
                processed += 1
            except Exception as e:
                error_detail = str(e)[:500]
                retry_count = row["retry_count"] + 1
                max_retries = row["max_retries"]
                if retry_count >= max_retries:
                    conn.execute(
                        "UPDATE events SET status = 'DEAD', error_detail = ?, retry_count = ?, dead_at = ? WHERE id = ?",
                        (error_detail, retry_count, _now(), event_id),
                    )
                else:
                    conn.execute(
                        "UPDATE events SET status = 'PENDING', error_detail = ?, retry_count = ? WHERE id = ?",
                        (error_detail, retry_count, event_id),
                    )
                conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    return processed
