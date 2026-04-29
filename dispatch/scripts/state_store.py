#!/usr/bin/env python3
"""
SQLite-backed state store for dispatch skill.

Usage (CLI):
    python scripts/state_store.py init
    python scripts/state_store.py export --table tasks --format json
    python scripts/state_store.py check
    python scripts/state_store.py backup

Usage (module):
    from state_store import StateStore
    with StateStore() as store:
        store.create_task("PLAT-1234", "Fix pipeline", priority=1)
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~/.zsh/dispatch/dispatch.db"))
SCHEMA_VERSION = 3


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    IN_REVIEW = "IN_REVIEW"
    COMPLETE = "COMPLETE"
    DEFERRED = "DEFERRED"
    ABANDONED = "ABANDONED"


VALID_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.IN_PROGRESS, TaskStatus.DEFERRED, TaskStatus.ABANDONED},
    TaskStatus.IN_PROGRESS: {
        TaskStatus.BLOCKED, TaskStatus.IN_REVIEW, TaskStatus.COMPLETE,
        TaskStatus.DEFERRED, TaskStatus.ABANDONED,
    },
    TaskStatus.BLOCKED: {TaskStatus.IN_PROGRESS, TaskStatus.DEFERRED, TaskStatus.ABANDONED},
    TaskStatus.IN_REVIEW: {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETE, TaskStatus.DEFERRED},
    TaskStatus.COMPLETE: set(),
    TaskStatus.DEFERRED: {TaskStatus.PENDING, TaskStatus.IN_PROGRESS},
    TaskStatus.ABANDONED: set(),
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','IN_PROGRESS','BLOCKED','IN_REVIEW',
                          'COMPLETE','DEFERRED','ABANDONED')),
    jira_status TEXT DEFAULT '',
    created_date TEXT NOT NULL,
    started_at TEXT,
    closed_at TEXT,
    deferred_to TEXT,
    git_permission INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 3,
    tags TEXT DEFAULT '[]',
    blocker TEXT,
    mr_links TEXT DEFAULT '[]',
    related_tasks TEXT DEFAULT '[]',
    log_dir TEXT DEFAULT '',
    optimus_reviewed INTEGER DEFAULT 0,
    session_ids TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    mode TEXT DEFAULT '',
    step_count INTEGER DEFAULT 0,
    task_count INTEGER DEFAULT 0,
    context_compaction_count INTEGER DEFAULT 0,
    checkpoints TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS step_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    ended_at TEXT,
    status TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    artifacts_produced TEXT DEFAULT '[]',
    verify_result TEXT DEFAULT '',
    error_detail TEXT,
    tool_calls INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bash_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    task_id TEXT,
    command TEXT NOT NULL,
    cwd TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    blocked INTEGER DEFAULT 0,
    block_reason TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bottlenecks (
    bottleneck_id TEXT PRIMARY KEY,
    detected_at TEXT NOT NULL,
    severity TEXT NOT NULL
        CHECK (severity IN ('CRITICAL','HIGH','MEDIUM')),
    type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    description TEXT NOT NULL,
    slack_notified INTEGER DEFAULT 0,
    resolved_at TEXT,
    resolution TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    channel TEXT NOT NULL,
    template TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    message_text TEXT NOT NULL,
    sent_at TEXT,
    status TEXT DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','SENT','FAILED','DEDUPED')),
    error TEXT,
    template_id TEXT DEFAULT '',
    queued_at TEXT
);

CREATE TABLE IF NOT EXISTS cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,
    command TEXT NOT NULL,
    approved INTEGER DEFAULT 0,
    approved_at TEXT,
    installed_at TEXT,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trajectories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    outcome TEXT DEFAULT '',
    tool_calls INTEGER DEFAULT 0,
    guardrail_triggers INTEGER DEFAULT 0,
    retries INTEGER DEFAULT 0,
    artifacts_produced TEXT DEFAULT '[]',
    context_tokens_start INTEGER,
    context_tokens_end INTEGER,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS optimus_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    tasks_reviewed INTEGER DEFAULT 0,
    brief_path TEXT,
    report_path TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING','COMPLETED','FAILED')),
    total_findings INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL
        CHECK (category IN (
            'environment','secret','repo_relationship','pattern',
            'decision','deployment','tooling','naming_convention'
        )),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    detail TEXT DEFAULT '',
    confidence TEXT DEFAULT 'observed'
        CHECK (confidence IN ('observed','inferred','operator_confirmed','superseded')),
    source_session TEXT,
    source_ticket TEXT,
    source_step TEXT,
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    superseded_by INTEGER,
    superseded_at TEXT,
    active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_key ON knowledge(key);
CREATE INDEX IF NOT EXISTS idx_knowledge_active ON knowledge(active);
CREATE INDEX IF NOT EXISTS idx_knowledge_ticket ON knowledge(source_ticket);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(created_date);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(date);
CREATE INDEX IF NOT EXISTS idx_step_log_session ON step_log(session_id);
CREATE INDEX IF NOT EXISTS idx_step_log_step ON step_log(step_id);
CREATE INDEX IF NOT EXISTS idx_bash_log_session ON bash_log(session_id);
CREATE INDEX IF NOT EXISTS idx_bash_log_timestamp ON bash_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_notifications_hash ON notifications(content_hash);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_bottlenecks_severity ON bottlenecks(severity);
CREATE INDEX IF NOT EXISTS idx_trajectories_session ON trajectories(session_id);
"""

SCHEMA_V3_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    source_skill TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    emitted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED', 'DEAD')),
    processed_at TEXT,
    processor TEXT,
    error_detail TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    dead_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_pending
    ON events(status) WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_events_type
    ON events(event_type, emitted_at);

CREATE TABLE IF NOT EXISTS optimus_findings (
    finding_id TEXT PRIMARY KEY,
    run_id INTEGER,
    title TEXT NOT NULL,
    category TEXT NOT NULL
        CHECK (category IN (
            'workflow_gap', 'tooling', 'process', 'automation',
            'mcp_integration', 'new_skill', 'coherency', 'performance'
        )),
    severity TEXT NOT NULL
        CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    affected_skill TEXT,
    description TEXT NOT NULL,
    recommendation TEXT,
    evidence TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING', 'REVIEWING', 'ACCEPTED', 'IN_PROGRESS',
            'IMPLEMENTED', 'DECLINED', 'DEFERRED'
        )),
    beads_issue_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    implemented_at TEXT,
    resolution_summary TEXT,
    FOREIGN KEY(run_id) REFERENCES optimus_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_findings_status
    ON optimus_findings(status);

CREATE INDEX IF NOT EXISTS idx_findings_severity
    ON optimus_findings(severity, status);

CREATE TABLE IF NOT EXISTS quality_grades (
    skill_slug TEXT NOT NULL,
    component_name TEXT NOT NULL,
    grade TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C', 'D', 'F')),
    evaluated_at TEXT NOT NULL,
    PRIMARY KEY (skill_slug, component_name)
);

CREATE VIEW IF NOT EXISTS quality_grades_overall AS
SELECT
    skill_slug,
    (SELECT grade FROM quality_grades qg2
     WHERE qg2.skill_slug = qg.skill_slug
     GROUP BY grade ORDER BY COUNT(*) DESC, grade ASC LIMIT 1
    ) AS overall_grade,
    MIN(evaluated_at) AS first_evaluated,
    MAX(evaluated_at) AS last_evaluated,
    COUNT(*) AS component_count,
    SUM(CASE WHEN grade = 'F' THEN 1 ELSE 0 END) AS f_count
FROM quality_grades qg
GROUP BY skill_slug;

CREATE TABLE IF NOT EXISTS quality_grade_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_slug TEXT NOT NULL,
    overall_grade TEXT NOT NULL CHECK (overall_grade IN ('A', 'B', 'C', 'D', 'F')),
    components_json TEXT NOT NULL,
    trend TEXT CHECK (trend IN ('improvement', 'stable', 'regression')),
    beads_issue_id TEXT,
    evaluated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_grade_history_skill
    ON quality_grade_history(skill_slug, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS notebook_sources (
    nlm_source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('tier1', 'tier2', 'tier3', 'analysis')),
    origin_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    expires_at TEXT,
    last_verified TEXT,
    upload_status TEXT DEFAULT 'OK'
        CHECK (upload_status IN ('OK', 'PENDING', 'FAILED', 'EXPIRED')),
    error_detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_sources_tier
    ON notebook_sources(tier);

CREATE INDEX IF NOT EXISTS idx_sources_expiry
    ON notebook_sources(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS contracts (
    contract_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    producer_skill TEXT NOT NULL,
    consumers_json TEXT NOT NULL DEFAULT '[]',
    required_fields_json TEXT NOT NULL DEFAULT '[]',
    immutable_fields_json TEXT NOT NULL DEFAULT '[]',
    custom_fields_json TEXT DEFAULT '[]',
    is_extensible INTEGER DEFAULT 1,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    drift_notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS contract_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    validated_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PASS', 'WARN', 'FAIL')),
    findings_json TEXT DEFAULT '[]',
    drift_notes TEXT,
    validated_at TEXT NOT NULL,
    FOREIGN KEY(contract_id) REFERENCES contracts(contract_id)
);

CREATE INDEX IF NOT EXISTS idx_validations_contract
    ON contract_validations(contract_id, validated_at DESC);

CREATE TABLE IF NOT EXISTS circuit_breakers (
    component TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'CLOSED'
        CHECK (state IN ('CLOSED', 'OPEN', 'HALF_OPEN')),
    failure_count INTEGER DEFAULT 0,
    failure_threshold INTEGER DEFAULT 3,
    last_failure_at TEXT,
    last_success_at TEXT,
    opened_at TEXT,
    half_open_after_seconds INTEGER DEFAULT 300,
    error_detail TEXT
);
"""

_JSON_FIELDS = {
    "knowledge": {"tags"},
    "tasks": {"tags", "mr_links", "related_tasks", "session_ids"},
    "sessions": {"checkpoints"},
    "step_log": {"artifacts_produced"},
    "trajectories": {"artifacts_produced"},
}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _row_to_dict(row, table=None):
    if row is None:
        return None
    d = dict(row)
    if table and table in _JSON_FIELDS:
        for field in _JSON_FIELDS[table]:
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
    return d


class StateStore:
    """SQLite state store with WAL mode for concurrent access."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def schema_init(self):
        self.conn.executescript(SCHEMA_SQL)
        self.conn.executescript(SCHEMA_V3_SQL)
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        self.conn.commit()
        self._migrate()
        self._validate_schema()

    def _validate_schema(self):
        expected = {
            "step_log": ["id", "session_id", "step_id", "started_at",
                          "completed_at", "ended_at", "status", "outcome",
                          "artifacts_produced", "verify_result", "error_detail",
                          "tool_calls", "retry_count"],
            "tasks": ["task_id", "title", "status", "created_date", "deferral_count"],
            "sessions": ["session_id", "date", "started_at", "mode",
                          "step_count", "task_count", "checkpoints"],
        }
        for table, columns in expected.items():
            info = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
            actual = {row[1] for row in info}
            missing = set(columns) - actual
            if missing:
                raise RuntimeError(
                    f"Schema validation failed: {table} missing columns: {missing}. "
                    f"Delete dispatch.db and re-run, or run: state_store.py migrate"
                )

    def _migrate(self):
        alterations = [
            ("sessions", "mode", "TEXT DEFAULT ''"),
            ("sessions", "step_count", "INTEGER DEFAULT 0"),
            ("sessions", "task_count", "INTEGER DEFAULT 0"),
            ("sessions", "context_compaction_count", "INTEGER DEFAULT 0"),
            ("sessions", "checkpoints", "TEXT DEFAULT '[]'"),
            ("step_log", "completed_at", "TEXT"),
            ("step_log", "ended_at", "TEXT"),
            ("step_log", "status", "TEXT DEFAULT ''"),
            ("step_log", "artifacts_produced", "TEXT DEFAULT '[]'"),
            ("step_log", "verify_result", "TEXT DEFAULT ''"),
            ("step_log", "error_detail", "TEXT"),
            ("step_log", "tool_calls", "INTEGER DEFAULT 0"),
            ("step_log", "retry_count", "INTEGER DEFAULT 0"),
            ("tasks", "deferral_count", "INTEGER DEFAULT 0"),
        ]
        for table, column, col_type in alterations:
            try:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                )
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def integrity_check(self):
        result = self.conn.execute("PRAGMA integrity_check").fetchone()
        return result[0] == "ok"

    def backup(self, suffix=None):
        if suffix is None:
            suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = self.db_path.with_suffix(f".{suffix}.bak")
        shutil.copy2(str(self.db_path), str(backup_path))
        return backup_path

    # --- Tasks ---

    def create_task(self, task_id, title, **kwargs):
        now = _now()
        self.conn.execute(
            """INSERT INTO tasks
               (task_id, title, description, status, created_date, priority,
                tags, mr_links, related_tasks, session_ids, log_dir,
                git_permission, blocker, jira_status, deferred_to)
               VALUES (?,?,?,'PENDING',?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id, title,
                kwargs.get("description", ""),
                now,
                kwargs.get("priority", 3),
                json.dumps(kwargs.get("tags", [])),
                json.dumps(kwargs.get("mr_links", [])),
                json.dumps(kwargs.get("related_tasks", [])),
                json.dumps(kwargs.get("session_ids", [])),
                kwargs.get("log_dir", ""),
                1 if kwargs.get("git_permission") else 0,
                kwargs.get("blocker"),
                kwargs.get("jira_status", ""),
                kwargs.get("deferred_to"),
            ),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def get_task(self, task_id):
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return _row_to_dict(row, "tasks")

    def update_task(self, task_id, **kwargs):
        if not kwargs:
            return self.get_task(task_id)
        json_set = _JSON_FIELDS.get("tasks", set())
        sets, vals = [], []
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            vals.append(json.dumps(val) if key in json_set and not isinstance(val, str) else val)
        vals.append(task_id)
        self.conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE task_id = ?", vals
        )
        self.conn.commit()
        return self.get_task(task_id)

    def transition_task(self, task_id, new_status, actor="operator"):
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        current = TaskStatus(task["status"])
        target = TaskStatus(new_status)
        if target not in VALID_TRANSITIONS[current]:
            raise ValueError(
                f"Invalid transition: {current.value} -> {target.value}"
            )
        updates = {"status": target.value}
        now = _now()
        if target == TaskStatus.IN_PROGRESS and not task.get("started_at"):
            updates["started_at"] = now
        if target in (TaskStatus.COMPLETE, TaskStatus.ABANDONED):
            updates["closed_at"] = now
        if target == TaskStatus.DEFERRED:
            self.conn.execute(
                "UPDATE tasks SET deferral_count = COALESCE(deferral_count, 0) + 1 WHERE task_id = ?",
                (task_id,),
            )
        return self.update_task(task_id, **updates)

    def list_tasks(self, date=None, status=None):
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if date:
            query += " AND created_date LIKE ?"
            params.append(f"{date}%")
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY priority ASC, created_date DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_dict(r, "tasks") for r in rows]

    def set_git_permission(self, task_id, permitted):
        self.conn.execute(
            "UPDATE tasks SET git_permission = ? WHERE task_id = ?",
            (1 if permitted else 0, task_id),
        )
        self.conn.commit()

    # --- Sessions ---

    def create_session(self, mode):
        date = _today()
        session_id = f"{date}-{mode}-{uuid.uuid4().hex[:8]}"
        now = _now()
        self.conn.execute(
            """INSERT INTO sessions (session_id, date, started_at, mode)
               VALUES (?, ?, ?, ?)""",
            (session_id, date, now, mode),
        )
        self.conn.commit()
        return self.get_session(session_id)

    def get_session(self, session_id):
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return _row_to_dict(row, "sessions")

    def get_today_session(self):
        date = _today()
        row = self.conn.execute(
            """SELECT * FROM sessions
               WHERE date = ? AND ended_at IS NULL
               ORDER BY started_at DESC LIMIT 1""",
            (date,),
        ).fetchone()
        return _row_to_dict(row, "sessions")

    def update_session(self, session_id, **kwargs):
        if not kwargs:
            return self.get_session(session_id)
        json_set = _JSON_FIELDS.get("sessions", set())
        sets, vals = [], []
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            vals.append(json.dumps(val) if key in json_set and not isinstance(val, str) else val)
        vals.append(session_id)
        self.conn.execute(
            f"UPDATE sessions SET {', '.join(sets)} WHERE session_id = ?", vals
        )
        self.conn.commit()
        return self.get_session(session_id)

    def append_checkpoint(self, session_id, checkpoint):
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        cps = session.get("checkpoints", [])
        if isinstance(cps, str):
            cps = json.loads(cps)
        cps.append(checkpoint)
        self.conn.execute(
            "UPDATE sessions SET checkpoints = ? WHERE session_id = ?",
            (json.dumps(cps), session_id),
        )
        self.conn.commit()

    # --- Step log ---

    def log_step(self, session_id, step_id, **kwargs):
        now = _now()
        self.conn.execute(
            """INSERT INTO step_log
               (session_id, step_id, started_at, outcome, artifacts_produced,
                verify_result, error_detail, tool_calls, retry_count)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                session_id, step_id,
                kwargs.get("started_at", now),
                kwargs.get("outcome", ""),
                json.dumps(kwargs.get("artifacts_produced", [])),
                kwargs.get("verify_result", ""),
                kwargs.get("error_detail"),
                kwargs.get("tool_calls", 0),
                kwargs.get("retry_count", 0),
            ),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def update_step_log(self, log_id, **kwargs):
        if not kwargs:
            return
        json_set = _JSON_FIELDS.get("step_log", set())
        sets, vals = [], []
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            vals.append(json.dumps(val) if key in json_set and not isinstance(val, str) else val)
        vals.append(log_id)
        self.conn.execute(
            f"UPDATE step_log SET {', '.join(sets)} WHERE id = ?", vals
        )
        self.conn.commit()

    def get_step_history(self, step_id, days=7):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        rows = self.conn.execute(
            """SELECT * FROM step_log
               WHERE step_id = ? AND started_at >= ?
               ORDER BY started_at DESC""",
            (step_id, cutoff),
        ).fetchall()
        return [_row_to_dict(r, "step_log") for r in rows]

    # --- Bash log ---

    def log_bash(self, session_id, task_id, command, permitted, reason):
        now = _now()
        self.conn.execute(
            """INSERT INTO bash_log
               (session_id, task_id, command, timestamp, blocked, block_reason)
               VALUES (?,?,?,?,?,?)""",
            (session_id, task_id, command, now, 0 if permitted else 1, reason),
        )
        self.conn.commit()

    # --- Bottlenecks ---

    def create_bottleneck(self, severity, type, resource_id, description):
        bid = f"bn-{uuid.uuid4().hex[:8]}"
        now = _now()
        self.conn.execute(
            """INSERT INTO bottlenecks
               (bottleneck_id, detected_at, severity, type, resource_id, description)
               VALUES (?,?,?,?,?,?)""",
            (bid, now, severity, type, resource_id, description),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM bottlenecks WHERE bottleneck_id = ?", (bid,)
        ).fetchone()
        return _row_to_dict(row)

    def resolve_bottleneck(self, bottleneck_id, resolution):
        now = _now()
        self.conn.execute(
            "UPDATE bottlenecks SET resolved_at = ?, resolution = ? WHERE bottleneck_id = ?",
            (now, resolution, bottleneck_id),
        )
        self.conn.commit()

    def get_open_bottlenecks(self):
        rows = self.conn.execute(
            """SELECT * FROM bottlenecks
               WHERE resolved_at IS NULL
               ORDER BY CASE severity
                   WHEN 'CRITICAL' THEN 0
                   WHEN 'HIGH' THEN 1
                   WHEN 'MEDIUM' THEN 2
               END"""
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # --- Notifications ---

    def queue_notification(self, channel, message, template_id=None):
        content_hash = hashlib.sha256(
            f"{channel}{template_id or ''}{message}".encode()
        ).hexdigest()
        now = _now()
        self.conn.execute(
            """INSERT INTO notifications
               (channel, template, message_text, content_hash, template_id, status, queued_at)
               VALUES (?,?,?,?,?,'PENDING',?)""",
            (channel, template_id or "", message, content_hash, template_id or "", now),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def mark_notification_sent(self, notif_id):
        now = _now()
        self.conn.execute(
            "UPDATE notifications SET status = 'SENT', sent_at = ? WHERE id = ?",
            (now, notif_id),
        )
        self.conn.commit()

    def get_pending_notifications(self):
        rows = self.conn.execute(
            "SELECT * FROM notifications WHERE status = 'PENDING' ORDER BY id"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # --- Trajectories ---

    def log_trajectory(self, session_id, step_id, **kwargs):
        now = _now()
        self.conn.execute(
            """INSERT INTO trajectories
               (session_id, step_id, started_at, completed_at, outcome,
                tool_calls, guardrail_triggers, retries, artifacts_produced,
                context_tokens_start, context_tokens_end, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id, step_id,
                kwargs.get("started_at", now),
                kwargs.get("completed_at"),
                kwargs.get("outcome", ""),
                kwargs.get("tool_calls", 0),
                kwargs.get("guardrail_triggers", 0),
                kwargs.get("retries", 0),
                json.dumps(kwargs.get("artifacts_produced", [])),
                kwargs.get("context_tokens_start"),
                kwargs.get("context_tokens_end"),
                kwargs.get("notes", ""),
            ),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # --- Knowledge ---

    def record_knowledge(self, category, key, value, detail='',
                         source_session=None, source_ticket=None,
                         source_step=None, confidence='observed', tags=None):
        now = _now()
        existing = self.conn.execute(
            "SELECT id, value FROM knowledge WHERE category = ? AND key = ? AND active = 1",
            (category, key),
        ).fetchone()
        if existing and existing[1] == value:
            self.conn.execute(
                "UPDATE knowledge SET updated_at = ? WHERE id = ?",
                (now, existing[0]),
            )
            self.conn.commit()
            return existing[0]
        self.conn.execute(
            """INSERT INTO knowledge
               (category, key, value, detail, confidence,
                source_session, source_ticket, source_step,
                tags, created_at, updated_at, active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
            (category, key, value, detail, confidence,
             source_session, source_ticket, source_step,
             json.dumps(tags or []), now, now),
        )
        self.conn.commit()
        new_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if existing and existing[1] != value:
            self.supersede_knowledge(existing[0], new_id,
                                     f"Value changed: {existing[1]} -> {value}")
        return new_id

    def query_knowledge(self, category=None, key_pattern=None,
                        ticket=None, active_only=True, limit=50):
        query = "SELECT * FROM knowledge WHERE 1=1"
        params = []
        if active_only:
            query += " AND active = 1"
        if category:
            query += " AND category = ?"
            params.append(category)
        if key_pattern:
            query += " AND key LIKE ?"
            params.append(f"%{key_pattern}%")
        if ticket:
            query += " AND source_ticket = ?"
            params.append(ticket)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_dict(r, "knowledge") for r in rows]

    def supersede_knowledge(self, old_id, new_id, reason=''):
        now = _now()
        self.conn.execute(
            """UPDATE knowledge
               SET active = 0, superseded_by = ?, superseded_at = ?,
                   confidence = 'superseded'
               WHERE id = ?""",
            (new_id, now, old_id),
        )
        self.conn.commit()

    def get_knowledge_for_brief(self, ticket_id=None, categories=None, limit=30):
        entries = []
        if ticket_id:
            entries.extend(self.query_knowledge(ticket=ticket_id, limit=limit))
        if categories:
            per_cat = max(1, limit // len(categories))
            for cat in categories:
                entries.extend(self.query_knowledge(category=cat, limit=per_cat))
        if not entries:
            entries = self.query_knowledge(limit=limit)
        seen = set()
        unique = []
        for e in entries:
            if e['id'] not in seen:
                seen.add(e['id'])
                unique.append(e)
        return unique[:limit]

    def get_knowledge_stats(self):
        rows = self.conn.execute(
            """SELECT category, COUNT(*) as count
               FROM knowledge WHERE active = 1
               GROUP BY category ORDER BY count DESC"""
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    # --- Optimus Findings ---

    def insert_finding(self, finding_id, title, category, severity,
                       description, run_id=None, affected_skill=None,
                       recommendation=None, evidence=None):
        now = _now()
        self.conn.execute(
            """INSERT OR IGNORE INTO optimus_findings
               (finding_id, run_id, title, category, severity, affected_skill,
                description, recommendation, evidence, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,'PENDING',?,?)""",
            (finding_id, run_id, title, category, severity, affected_skill,
             description, recommendation, evidence, now, now),
        )
        self.conn.commit()

    def update_finding_status(self, finding_id, new_status, resolution_summary=None):
        now = _now()
        updates = "status = ?, updated_at = ?"
        params = [new_status, now]
        if new_status == "IMPLEMENTED":
            updates += ", implemented_at = ?"
            params.append(now)
        if resolution_summary:
            updates += ", resolution_summary = ?"
            params.append(resolution_summary)
        params.append(finding_id)
        self.conn.execute(
            f"UPDATE optimus_findings SET {updates} WHERE finding_id = ?", params
        )
        self.conn.commit()

    def get_finding(self, finding_id):
        row = self.conn.execute(
            "SELECT * FROM optimus_findings WHERE finding_id = ?", (finding_id,)
        ).fetchone()
        return _row_to_dict(row)

    def list_findings(self, status_filter=None, severity_filter=None):
        query = "SELECT * FROM optimus_findings WHERE 1=1"
        params = []
        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)
        if severity_filter:
            query += " AND severity = ?"
            params.append(severity_filter)
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def set_finding_beads_id(self, finding_id, beads_issue_id):
        self.conn.execute(
            "UPDATE optimus_findings SET beads_issue_id = ?, updated_at = ? WHERE finding_id = ?",
            (beads_issue_id, _now(), finding_id),
        )
        self.conn.commit()

    # --- Quality Grades ---

    def upsert_grade(self, skill_slug, component_name, grade):
        now = _now()
        self.conn.execute(
            """INSERT INTO quality_grades (skill_slug, component_name, grade, evaluated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(skill_slug, component_name) DO UPDATE SET
                   grade = excluded.grade, evaluated_at = excluded.evaluated_at""",
            (skill_slug, component_name, grade, now),
        )
        self.conn.commit()

    def get_grades(self, skill_slug=None):
        if skill_slug:
            rows = self.conn.execute(
                "SELECT * FROM quality_grades WHERE skill_slug = ?", (skill_slug,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM quality_grades").fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_overall_grade(self, skill_slug):
        row = self.conn.execute(
            "SELECT overall_grade FROM quality_grades_overall WHERE skill_slug = ?",
            (skill_slug,),
        ).fetchone()
        return row[0] if row else None

    def append_grade_history(self, skill_slug, overall_grade, components_json,
                             trend=None, beads_issue_id=None):
        now = _now()
        self.conn.execute(
            """INSERT INTO quality_grade_history
               (skill_slug, overall_grade, components_json, trend, beads_issue_id, evaluated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (skill_slug, overall_grade,
             json.dumps(components_json) if not isinstance(components_json, str) else components_json,
             trend, beads_issue_id, now),
        )
        self.conn.commit()

    def get_grade_history(self, skill_slug, limit=10):
        rows = self.conn.execute(
            "SELECT * FROM quality_grade_history WHERE skill_slug = ? ORDER BY evaluated_at DESC LIMIT ?",
            (skill_slug, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_previous_overall_grade(self, skill_slug):
        row = self.conn.execute(
            "SELECT overall_grade FROM quality_grade_history WHERE skill_slug = ? ORDER BY evaluated_at DESC LIMIT 1",
            (skill_slug,),
        ).fetchone()
        return row[0] if row else None

    # --- Notebook Sources ---

    def upsert_source(self, nlm_source_id, title, tier, origin_path,
                      content_hash, uploaded_at, expires_at=None):
        self.conn.execute(
            """INSERT INTO notebook_sources
               (nlm_source_id, title, tier, origin_path, content_hash, uploaded_at, expires_at, last_verified, upload_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OK')
               ON CONFLICT(nlm_source_id) DO UPDATE SET
                   title = excluded.title, content_hash = excluded.content_hash,
                   uploaded_at = excluded.uploaded_at, expires_at = excluded.expires_at,
                   last_verified = excluded.uploaded_at, upload_status = 'OK', error_detail = NULL""",
            (nlm_source_id, title, tier, origin_path, content_hash, uploaded_at, expires_at, uploaded_at),
        )
        self.conn.commit()

    def get_source(self, nlm_source_id):
        row = self.conn.execute(
            "SELECT * FROM notebook_sources WHERE nlm_source_id = ?", (nlm_source_id,)
        ).fetchone()
        return _row_to_dict(row)

    def list_sources(self, tier_filter=None, status_filter=None):
        query = "SELECT * FROM notebook_sources WHERE 1=1"
        params = []
        if tier_filter:
            query += " AND tier = ?"
            params.append(tier_filter)
        if status_filter:
            query += " AND upload_status = ?"
            params.append(status_filter)
        query += " ORDER BY tier, title"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def update_source_status(self, nlm_source_id, upload_status, error_detail=None):
        self.conn.execute(
            "UPDATE notebook_sources SET upload_status = ?, error_detail = ? WHERE nlm_source_id = ?",
            (upload_status, error_detail, nlm_source_id),
        )
        self.conn.commit()

    def delete_source(self, nlm_source_id):
        self.conn.execute(
            "DELETE FROM notebook_sources WHERE nlm_source_id = ?", (nlm_source_id,)
        )
        self.conn.commit()

    def get_failed_sources(self):
        return self.list_sources(status_filter="FAILED")

    def export_source_inventory(self, path=None):
        if path is None:
            path = Path(os.path.expanduser("~/.zsh/dispatch/notebook/source_inventory.yaml"))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        sources = self.list_sources()
        import yaml
        with open(path, "w") as f:
            yaml.dump({"generated_at": _now(), "sources": sources}, f,
                       default_flow_style=False, sort_keys=False)

    # --- Contracts ---

    def insert_contract(self, contract_id, description, producer_skill,
                        schema_version="1.0", consumers=None, required_fields=None,
                        immutable_fields=None, custom_fields=None, is_extensible=True):
        now = _now()
        self.conn.execute(
            """INSERT OR REPLACE INTO contracts
               (contract_id, description, schema_version, producer_skill,
                consumers_json, required_fields_json, immutable_fields_json,
                custom_fields_json, is_extensible, discovered_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (contract_id, description, schema_version, producer_skill,
             json.dumps(consumers or []), json.dumps(required_fields or []),
             json.dumps(immutable_fields or []), json.dumps(custom_fields or []),
             1 if is_extensible else 0, now, now),
        )
        self.conn.commit()

    def get_contract(self, contract_id):
        row = self.conn.execute(
            "SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        return _row_to_dict(row)

    def list_contracts(self):
        rows = self.conn.execute("SELECT * FROM contracts ORDER BY contract_id").fetchall()
        return [_row_to_dict(r) for r in rows]

    def insert_validation(self, contract_id, validated_by, status,
                          findings_json=None, drift_notes=None):
        now = _now()
        self.conn.execute(
            """INSERT INTO contract_validations
               (contract_id, validated_by, status, findings_json, drift_notes, validated_at)
               VALUES (?,?,?,?,?,?)""",
            (contract_id, validated_by, status,
             json.dumps(findings_json or []), drift_notes, now),
        )
        self.conn.commit()

    def get_validations(self, contract_id, limit=5):
        rows = self.conn.execute(
            "SELECT * FROM contract_validations WHERE contract_id = ? ORDER BY validated_at DESC LIMIT ?",
            (contract_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def export_registry(self, path=None):
        if path is None:
            path = Path("/Users/sethallen/agent-skills/dispatch-manager/contracts/registry.yaml")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        contracts = self.list_contracts()
        output = {"contracts": {}}
        for c in contracts:
            output["contracts"][c["contract_id"]] = {
                "description": c["description"],
                "schema_version": c["schema_version"],
                "producer": c["producer_skill"],
                "consumers": json.loads(c["consumers_json"]) if isinstance(c["consumers_json"], str) else c["consumers_json"],
                "required_fields": json.loads(c["required_fields_json"]) if isinstance(c["required_fields_json"], str) else c["required_fields_json"],
                "immutable_fields": json.loads(c["immutable_fields_json"]) if isinstance(c["immutable_fields_json"], str) else c["immutable_fields_json"],
                "extensible": bool(c["is_extensible"]),
                "discovered_at": c["discovered_at"],
            }

        import yaml
        with open(path, "w") as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    # --- Exports ---

    def export_quality_grades(self, path=None):
        if path is None:
            path = Path(os.path.expanduser("~/.zsh/dispatch/harness/quality-grades.yaml"))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        grades = {}
        for row in self.conn.execute(
            "SELECT skill_slug, component_name, grade FROM quality_grades"
        ).fetchall():
            grades.setdefault(row[0], {"components": {}})
            grades[row[0]]["components"][row[1]] = row[2]

        for skill, data in grades.items():
            overall = self.get_overall_grade(skill)
            data["overall"] = overall or "F"

        output = {"generated_at": _now(), "generated_by": "dispatch.db", "skills": grades}

        import yaml
        with open(path, "w") as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    def export_findings(self, path, status_filter=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        findings = self.list_findings(status_filter=status_filter)

        if str(path).endswith(".md"):
            lines = ["# Resolved Findings\n"]
            for f in findings:
                lines.append(f"\n## {f['finding_id']}: {f.get('title', '')}")
                lines.append(f"Status: {f['status']}. Date: {f.get('implemented_at', f.get('updated_at', ''))}")
                if f.get("resolution_summary"):
                    lines.append(f"Resolution: {f['resolution_summary']}")
                lines.append("")
            with open(path, "w") as fh:
                fh.write("\n".join(lines))
        else:
            import yaml
            with open(path, "w") as fh:
                yaml.dump(findings, fh, default_flow_style=False, sort_keys=False)

    def export_grade_history(self, path=None):
        if path is None:
            path = Path(os.path.expanduser("~/.zsh/dispatch/harness/grade-history.yaml"))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = self.conn.execute(
            "SELECT * FROM quality_grade_history ORDER BY evaluated_at DESC LIMIT 100"
        ).fetchall()
        entries = []
        for r in rows:
            entry = _row_to_dict(r)
            if isinstance(entry.get("components_json"), str):
                try:
                    entry["components_json"] = json.loads(entry["components_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            entries.append(entry)

        import yaml
        with open(path, "w") as f:
            yaml.dump({"entries": entries}, f, default_flow_style=False, sort_keys=False)

    # --- Events ---

    def emit_event(self, event_type, source_skill, payload):
        now = _now()
        cur = self.conn.execute(
            """INSERT INTO events (event_type, source_skill, payload_json, emitted_at)
               VALUES (?, ?, ?, ?)""",
            (event_type, source_skill, json.dumps(payload), now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_pending_events(self, limit=10):
        rows = self.conn.execute(
            "SELECT * FROM events WHERE status = 'PENDING' ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def mark_event_processing(self, event_id, processor="post_event"):
        self.conn.execute(
            "UPDATE events SET status = 'PROCESSING', processor = ? WHERE id = ?",
            (processor, event_id),
        )
        self.conn.commit()

    def mark_event_processed(self, event_id):
        now = _now()
        self.conn.execute(
            "UPDATE events SET status = 'PROCESSED', processed_at = ? WHERE id = ?",
            (now, event_id),
        )
        self.conn.commit()

    def mark_event_failed(self, event_id, error_detail):
        row = self.conn.execute(
            "SELECT retry_count, max_retries FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not row:
            return
        retry_count = row[0] + 1
        if retry_count >= row[1]:
            now = _now()
            self.conn.execute(
                "UPDATE events SET status = 'DEAD', error_detail = ?, retry_count = ?, dead_at = ? WHERE id = ?",
                (error_detail, retry_count, now, event_id),
            )
        else:
            self.conn.execute(
                "UPDATE events SET status = 'PENDING', error_detail = ?, retry_count = ? WHERE id = ?",
                (error_detail, retry_count, event_id),
            )
        self.conn.commit()

    def get_event_stats(self, hours=24):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM events WHERE emitted_at >= ? GROUP BY status",
            (cutoff,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    # --- Circuit Breakers ---

    def check_circuit(self, component):
        row = self.conn.execute(
            "SELECT state, opened_at, half_open_after_seconds FROM circuit_breakers WHERE component = ?",
            (component,),
        ).fetchone()
        if not row:
            return "CLOSED"
        state, opened_at, half_open_after = row[0], row[1], row[2]
        if state == "OPEN" and opened_at:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(opened_at)).total_seconds()
            if elapsed >= half_open_after:
                self.conn.execute(
                    "UPDATE circuit_breakers SET state = 'HALF_OPEN' WHERE component = ?",
                    (component,),
                )
                self.conn.commit()
                return "HALF_OPEN"
        return state

    def record_success(self, component):
        now = _now()
        self.conn.execute(
            """INSERT INTO circuit_breakers (component, state, failure_count, last_success_at)
               VALUES (?, 'CLOSED', 0, ?)
               ON CONFLICT(component) DO UPDATE SET
                   state = 'CLOSED', failure_count = 0, last_success_at = excluded.last_success_at""",
            (component, now),
        )
        self.conn.commit()

    def record_failure(self, component, error):
        now = _now()
        self.conn.execute(
            """INSERT INTO circuit_breakers (component, failure_count, last_failure_at, error_detail)
               VALUES (?, 1, ?, ?)
               ON CONFLICT(component) DO UPDATE SET
                   failure_count = failure_count + 1,
                   last_failure_at = excluded.last_failure_at,
                   error_detail = excluded.error_detail""",
            (component, now, error),
        )
        row = self.conn.execute(
            "SELECT failure_count, failure_threshold FROM circuit_breakers WHERE component = ?",
            (component,),
        ).fetchone()
        if row and row[0] >= row[1]:
            self.conn.execute(
                "UPDATE circuit_breakers SET state = 'OPEN', opened_at = ? WHERE component = ?",
                (now, component),
            )
            self.conn.commit()
            self.emit_event("circuit_breaker_tripped", component, {
                "component": component,
                "failure_count": row[0],
                "error": error,
            })
            return "OPEN"
        self.conn.commit()
        return "CLOSED"

    # --- Export / carry-forward ---

    def export_table(self, table, format="json"):
        allowed = {
            "tasks", "sessions", "step_log", "bash_log", "bottlenecks",
            "notifications", "cron_jobs", "trajectories", "optimus_runs", "knowledge",
            "events", "circuit_breakers", "optimus_findings",
            "quality_grades", "quality_grade_history",
            "notebook_sources", "contracts", "contract_validations",
        }
        if table not in allowed:
            raise ValueError(f"Unknown table: {table}")
        rows = self.conn.execute(f"SELECT * FROM {table}").fetchall()
        data = [_row_to_dict(r, table) for r in rows]
        if format == "json":
            return json.dumps(data, indent=2, default=str)
        if format == "csv":
            if not data:
                return ""
            import csv
            import io
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return buf.getvalue()
        raise ValueError(f"Unknown format: {format}")

    def export_session_summary(self, date):
        row = self.conn.execute(
            """SELECT * FROM sessions
               WHERE date = ? ORDER BY started_at DESC LIMIT 1""",
            (date,),
        ).fetchone()
        if not row:
            return {}
        s = _row_to_dict(row, "sessions")
        steps = self.conn.execute(
            "SELECT * FROM step_log WHERE session_id = ?", (s["session_id"],)
        ).fetchall()
        s["steps"] = [_row_to_dict(r, "step_log") for r in steps]
        return s

    def generate_carry_forward(self):
        rows = self.conn.execute(
            """SELECT * FROM tasks
               WHERE status IN ('PENDING','IN_PROGRESS','BLOCKED','DEFERRED','IN_REVIEW')
               ORDER BY priority ASC"""
        ).fetchall()
        return [
            {
                "task_id": t["task_id"],
                "title": t["title"],
                "status": t["status"],
                "priority": t["priority"],
                "blocker": t["blocker"],
                "tags": json.loads(t["tags"]) if isinstance(t["tags"], str) else t["tags"],
            }
            for t in rows
        ]


def _harness_status(store):
    now_dt = datetime.now(timezone.utc)

    print("=" * 55)
    print(f" DISPATCH HARNESS STATUS — {now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print("=" * 55)

    print("\n Component Health")
    print(" " + "-" * 45)
    rows = store.conn.execute("SELECT * FROM circuit_breakers").fetchall()
    if not rows:
        print("  (no components tracked)")
    for r in rows:
        sym = "●" if r["state"] == "CLOSED" else ("▲" if r["state"] == "HALF_OPEN" else "✕")
        age = ""
        ts = r["last_success_at"] or r["last_failure_at"]
        if ts:
            try:
                elapsed = (now_dt - datetime.fromisoformat(ts)).total_seconds()
                if elapsed < 3600:
                    age = f"{int(elapsed/60)}m ago"
                else:
                    age = f"{int(elapsed/3600)}h ago"
            except Exception:
                age = ""
        print(f"  {r['component']:<20} {sym} {r['state']:<10} ({age})")

    print("\n Event Bus")
    print(" " + "-" * 45)
    stats = store.get_event_stats(hours=24)
    pending = stats.get("PENDING", 0)
    processed = stats.get("PROCESSED", 0)
    failed = stats.get("FAILED", 0)
    dead = stats.get("DEAD", 0)
    print(f"  Pending: {pending}  Processed(24h): {processed}  Failed: {failed}  Dead: {dead}")

    print("\n Quality Grades")
    print(" " + "-" * 45)
    grade_rows = store.conn.execute(
        "SELECT * FROM quality_grades_overall ORDER BY skill_slug"
    ).fetchall()
    if not grade_rows:
        print("  (no grades recorded)")
    for r in grade_rows:
        hist = store.conn.execute(
            "SELECT trend FROM quality_grade_history WHERE skill_slug = ? ORDER BY evaluated_at DESC LIMIT 1",
            (r["skill_slug"],),
        ).fetchone()
        trend_sym = ""
        if hist and hist[0]:
            trend_sym = " ▲" if hist[0] == "improvement" else (" ▼" if hist[0] == "regression" else "")
        print(f"  {r['skill_slug']:<22} {r['overall_grade']}{trend_sym}")

    print("\n Optimus Findings")
    print(" " + "-" * 45)
    finding_stats = store.conn.execute(
        "SELECT status, COUNT(*) FROM optimus_findings GROUP BY status"
    ).fetchall()
    if not finding_stats:
        print("  (no findings)")
    else:
        parts = [f"{r[0]}: {r[1]}" for r in finding_stats]
        print(f"  {' | '.join(parts)}")
    orphans = store.conn.execute(
        "SELECT COUNT(*) FROM optimus_findings WHERE beads_issue_id IS NULL AND status NOT IN ('IMPLEMENTED', 'DECLINED')"
    ).fetchone()[0]
    if orphans:
        print(f"  Orphaned (no beads issue): {orphans}")

    print("\n Notebook Sources")
    print(" " + "-" * 45)
    src_stats = store.conn.execute(
        "SELECT tier, COUNT(*) FROM notebook_sources GROUP BY tier"
    ).fetchall()
    total = sum(r[1] for r in src_stats)
    tier_str = "  ".join(f"{r[0]}: {r[1]}" for r in src_stats)
    print(f"  Total: {total}/49  {tier_str}")
    failed_src = store.conn.execute(
        "SELECT COUNT(*) FROM notebook_sources WHERE upload_status = 'FAILED'"
    ).fetchone()[0]
    if failed_src:
        print(f"  Failed uploads: {failed_src}")

    print("\n" + "=" * 55)


def main():
    parser = argparse.ArgumentParser(description="Dispatch state store")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize database schema")

    p_export = sub.add_parser("export", help="Export table data")
    p_export.add_argument("--table", required=True)
    p_export.add_argument("--format", choices=["json", "csv"], default="json")

    sub.add_parser("migrate", help="Run schema migrations")
    sub.add_parser("check", help="Run integrity check")
    sub.add_parser("status", help="Show unified harness health dashboard")

    p_backup = sub.add_parser("backup", help="Create database backup")
    p_backup.add_argument("--suffix", default=None)

    p_know = sub.add_parser("knowledge", help="Manage knowledge base")
    know_sub = p_know.add_subparsers(dest="kr_command", required=True)

    p_kr_record = know_sub.add_parser("record", help="Record a knowledge entry")
    p_kr_record.add_argument("--category", required=True)
    p_kr_record.add_argument("--key", required=True)
    p_kr_record.add_argument("--value", required=True)
    p_kr_record.add_argument("--detail", default="")
    p_kr_record.add_argument("--ticket", default=None)
    p_kr_record.add_argument("--session", default=None)
    p_kr_record.add_argument("--step", default=None)
    p_kr_record.add_argument("--confidence", default="observed",
                             choices=["observed", "inferred", "operator_confirmed"])

    p_kr_query = know_sub.add_parser("query", help="Query knowledge")
    p_kr_query.add_argument("--category", default=None)
    p_kr_query.add_argument("--key", default=None)
    p_kr_query.add_argument("--ticket", default=None)
    p_kr_query.add_argument("--all", action="store_true", help="Include superseded")
    p_kr_query.add_argument("--limit", type=int, default=50)

    know_sub.add_parser("stats", help="Knowledge base statistics")

    p_task = sub.add_parser("task", help="Manage tasks")
    task_sub = p_task.add_subparsers(dest="task_command", required=True)

    p_task_list = task_sub.add_parser("list", help="List tasks")
    p_task_list.add_argument("--status", default=None)
    p_task_list.add_argument("--date", default=None)

    p_task_create = task_sub.add_parser("create", help="Create a task")
    p_task_create.add_argument("task_id")
    p_task_create.add_argument("title")
    p_task_create.add_argument("--priority", type=int, default=3)
    p_task_create.add_argument("--description", default="")

    p_task_show = task_sub.add_parser("show", help="Show a task")
    p_task_show.add_argument("task_id")

    p_task_start = task_sub.add_parser("start", help="Start a task")
    p_task_start.add_argument("task_id")

    p_task_close = task_sub.add_parser("close", help="Close a task")
    p_task_close.add_argument("task_id")

    p_task_defer = task_sub.add_parser("defer", help="Defer a task")
    p_task_defer.add_argument("task_id")
    p_task_defer.add_argument("--to", default=None)

    p_task_block = task_sub.add_parser("block", help="Block a task")
    p_task_block.add_argument("task_id")
    p_task_block.add_argument("--reason", required=True)

    p_task_unblock = task_sub.add_parser("unblock", help="Unblock a task")
    p_task_unblock.add_argument("task_id")

    p_task_submit = task_sub.add_parser("submit", help="Submit task for review")
    p_task_submit.add_argument("task_id")

    p_task_git = task_sub.add_parser("git-allow", help="Allow git ops for task")
    p_task_git.add_argument("task_id")

    p_task_abandon = task_sub.add_parser("abandon", help="Abandon a task")
    p_task_abandon.add_argument("task_id")
    p_task_abandon.add_argument("--reason", required=True)

    args = parser.parse_args()
    store = StateStore()

    if args.command == "init":
        store.schema_init()
        print(f"Schema v{SCHEMA_VERSION} initialized at {store.db_path}")
    elif args.command == "export":
        store.schema_init()
        print(store.export_table(args.table, format=args.format))
    elif args.command == "migrate":
        store.schema_init()
        print(f"Schema migrated to v{SCHEMA_VERSION}")
    elif args.command == "check":
        ok = store.integrity_check()
        print("OK" if ok else "FAILED")
        sys.exit(0 if ok else 1)
    elif args.command == "status":
        store.schema_init()
        _harness_status(store)
    elif args.command == "backup":
        path = store.backup(args.suffix)
        print(f"Backup created: {path}")
    elif args.command == "knowledge":
        if args.kr_command == "record":
            kid = store.record_knowledge(
                category=args.category, key=args.key, value=args.value,
                detail=args.detail, source_session=args.session,
                source_ticket=args.ticket, source_step=args.step,
                confidence=args.confidence,
            )
            print(f"Recorded knowledge #{kid}: [{args.category}] {args.key}")
        elif args.kr_command == "query":
            entries = store.query_knowledge(
                category=args.category, key_pattern=args.key,
                ticket=args.ticket, active_only=not args.all,
                limit=args.limit,
            )
            print(json.dumps(entries, indent=2))
        elif args.kr_command == "stats":
            stats = store.get_knowledge_stats()
            total = sum(stats.values())
            print(f"Knowledge base: {total} active entries")
            for cat, count in stats.items():
                print(f"  {cat}: {count}")
    elif args.command == "task":
        store.schema_init()
        try:
            if args.task_command == "list":
                result = store.list_tasks(date=args.date, status=args.status)
                print(json.dumps(result, indent=2))
            elif args.task_command == "create":
                result = store.create_task(args.task_id, args.title, priority=args.priority, description=args.description)
                print(json.dumps(result, indent=2))
            elif args.task_command == "show":
                result = store.get_task(args.task_id)
                if not result:
                    print(f"Task {args.task_id} not found", file=sys.stderr)
                    sys.exit(1)
                print(json.dumps(result, indent=2))
            elif args.task_command == "start":
                result = store.transition_task(args.task_id, "IN_PROGRESS")
                print(json.dumps(result, indent=2))
            elif args.task_command == "close":
                result = store.transition_task(args.task_id, "COMPLETE")
                print(json.dumps(result, indent=2))
            elif args.task_command == "defer":
                result = store.transition_task(args.task_id, "DEFERRED")
                if args.to:
                    result = store.update_task(args.task_id, deferred_to=args.to)
                print(json.dumps(result, indent=2))
            elif args.task_command == "block":
                store.update_task(args.task_id, blocker=args.reason)
                result = store.transition_task(args.task_id, "BLOCKED")
                print(json.dumps(result, indent=2))
            elif args.task_command == "unblock":
                store.update_task(args.task_id, blocker=None)
                result = store.transition_task(args.task_id, "IN_PROGRESS")
                print(json.dumps(result, indent=2))
            elif args.task_command == "submit":
                result = store.transition_task(args.task_id, "IN_REVIEW")
                print(json.dumps(result, indent=2))
            elif args.task_command == "git-allow":
                store.set_git_permission(args.task_id, True)
                print(json.dumps({"task_id": args.task_id, "git_permission": True}, indent=2))
            elif args.task_command == "abandon":
                store.update_task(args.task_id, blocker=args.reason)
                result = store.transition_task(args.task_id, "ABANDONED")
                print(json.dumps(result, indent=2))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

    store.close()


if __name__ == "__main__":
    main()
