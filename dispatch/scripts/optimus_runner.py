#!/usr/bin/env python3
"""
Optimus agent runner -- spawns the optimization agent as a claude -p subprocess.

Generates optimus_brief.md with task logs, session data, and workflow config,
then invokes Optimus in an isolated context window. Captures the report.

Usage (CLI):
    python scripts/optimus_runner.py --period=day
    python scripts/optimus_runner.py --period=week --date 2026-04-01
    python scripts/optimus_runner.py --dry-run
    python scripts/optimus_runner.py test

Usage (module):
    from optimus_runner import OptimusRunner
    runner = OptimusRunner(store, writer)
    report_path = runner.run()
"""

import argparse
import calendar
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.path.expanduser("~/.zsh/dispatch"))
WORKFLOW_PATH = STATE_ROOT / "workflow.yaml"
TELEMETRY_DIR = STATE_ROOT / "harness" / "telemetry"
OPTIMUS_AGENT = Path("~/.claude/agents/optimus.md").expanduser()

try:
    import yaml
except ImportError:
    yaml = None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _atomic_write(path, content):
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


def _compute_date_range(date_str, period="day"):
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    if period == "day":
        return date_str, date_str
    elif period == "week":
        monday = d - timedelta(days=d.weekday())
        friday = monday + timedelta(days=4)
        end = min(friday, d)
        return monday.isoformat(), end.isoformat()
    elif period == "month":
        first = d.replace(day=1)
        last_day = calendar.monthrange(d.year, d.month)[1]
        last = d.replace(day=last_day)
        end = min(last, d)
        return first.isoformat(), end.isoformat()
    return date_str, date_str


class OptimusRunner:
    """Manages Optimus agent invocation."""

    def __init__(self, store, writer=None, model: str = "claude-opus-4-6"):
        self.store = store
        self.writer = writer
        self.model = model

    def generate_brief(self, date: str, period: str = "day") -> Path:
        start, end = _compute_date_range(date, period)

        tasks = self._query_tasks_in_range(start, end)
        total = len(tasks)
        completed = sum(1 for t in tasks if t["status"] == "COMPLETE")
        deferred = sum(1 for t in tasks if t["status"] == "DEFERRED")
        abandoned = sum(1 for t in tasks if t["status"] == "ABANDONED")

        sections = []
        sections.append(f"# Optimus Brief -- {date}\n")

        sections.append("## Review Period")
        sections.append(
            f"Date range: {start} to {end}\n"
            f"Total: {total} tasks | Completed: {completed} | "
            f"Deferred: {deferred} | Abandoned: {abandoned}\n"
        )

        sections.append("## Telemetry Digest")
        digest_path = TELEMETRY_DIR / f"{date}-digest.md"
        if digest_path.exists():
            sections.append(digest_path.read_text().strip() + "\n")
        else:
            sections.append("Telemetry digest not available for this date.\n")

        sections.append("## Task Log Paths")
        log_paths = self._collect_task_log_paths(tasks, date)
        if log_paths:
            sections.append("\n".join(f"- {p}" for p in log_paths) + "\n")
        else:
            sections.append("No task logs found for this period.\n")

        sections.append("## Session Data")
        session_data = self.store.export_session_summary(date)
        sections.append(
            "```json\n" + json.dumps(session_data, indent=2, default=str) + "\n```\n"
        )

        sections.append("## Bottleneck Records")
        bottlenecks = self.store.get_open_bottlenecks()
        sections.append(
            "```json\n" + json.dumps(bottlenecks, indent=2, default=str) + "\n```\n"
        )

        sections.append("## Bash Command History")
        bash_lines = self._format_bash_history()
        sections.append(bash_lines + "\n")

        sections.append("## Workflow Configuration")
        if WORKFLOW_PATH.exists():
            sections.append(
                "```yaml\n" + WORKFLOW_PATH.read_text().strip() + "\n```\n"
            )
        else:
            sections.append("workflow.yaml not found.\n")

        sections.append("## Optimus Instructions")
        sections.append(
            "You are Optimus, the workflow optimization agent for @zettatron.\n"
            "You have no access to the operator's current session.\n"
            "Perform a critical, data-driven analysis of the task logs,\n"
            "bash command history, bottleneck records, and session metadata.\n"
            "Produce the optimization report in the format defined in your agent definition.\n"
            "Ground every recommendation in specific evidence. Label inferences as\n"
            "[INFERENCE] and observations as [OBSERVED].\n"
        )

        brief_content = "\n".join(sections)
        day_dir = self._day_dir(date)
        brief_path = day_dir / "optimus_brief.md"
        _atomic_write(brief_path, brief_content)

        self.store.conn.execute(
            """INSERT INTO optimus_runs
               (session_id, period_start, period_end, tasks_reviewed,
                brief_path, started_at, status)
               VALUES (?, ?, ?, ?, ?, ?, 'RUNNING')""",
            (None, start, end, total, str(brief_path), _now()),
        )
        self.store.conn.commit()

        return brief_path

    def invoke_agent(self, brief_path: Path, timeout: int = 600) -> str:
        brief_content = Path(brief_path).read_text()

        cmd = ["claude", "-p", brief_content, "--model", self.model, "--print"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(STATE_ROOT),
            )
            if result.returncode == 0:
                return result.stdout
            return self._synthetic_report("ERROR", result.stderr or "Non-zero exit")
        except subprocess.TimeoutExpired:
            return self._synthetic_report(
                "TIMEOUT", f"Optimus timed out after {timeout}s"
            )
        except FileNotFoundError:
            return self._synthetic_report(
                "ERROR", "claude binary not found on PATH"
            )

    def write_report(self, content: str, date: str) -> Path:
        day_dir = self._day_dir(date)
        report_path = day_dir / "optimus_report.md"
        _atomic_write(report_path, content)
        return report_path

    def parse_report(self, report_path) -> dict:
        try:
            text = Path(report_path).read_text()
        except (OSError, IOError):
            return {"parse_error": True, "total_findings": 0}

        if not text.startswith("---"):
            return {"parse_error": True, "total_findings": 0}

        end_idx = text.find("---", 3)
        if end_idx == -1:
            return {"parse_error": True, "total_findings": 0}

        frontmatter_str = text[3:end_idx].strip()
        if yaml:
            try:
                meta = yaml.safe_load(frontmatter_str)
                if isinstance(meta, dict):
                    return meta
            except Exception:
                pass

        try:
            meta = {}
            for line in frontmatter_str.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    if val.isdigit():
                        val = int(val)
                    meta[key] = val
            return meta if meta else {"parse_error": True, "total_findings": 0}
        except Exception:
            return {"parse_error": True, "total_findings": 0}

    def run(self, date: str = None, period: str = "day",
            timeout_seconds: int = 600) -> Path:
        date = date or _today()

        if self.check_already_reviewed(date, period):
            row = self.store.conn.execute(
                """SELECT report_path FROM optimus_runs
                   WHERE period_start = ? AND status = 'COMPLETED'
                   ORDER BY id DESC LIMIT 1""",
                (_compute_date_range(date, period)[0],),
            ).fetchone()
            if row and row[0]:
                return Path(row[0])

        brief_path = self.generate_brief(date, period)

        run_id = self.store.conn.execute(
            "SELECT id FROM optimus_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

        try:
            content = self.invoke_agent(brief_path, timeout_seconds)
            report_path = self.write_report(content, date)
            meta = self.parse_report(report_path)

            status = "FAILED" if meta.get("parse_error") and "TIMEOUT" in content[:200] else "COMPLETED"
            self.store.conn.execute(
                """UPDATE optimus_runs
                   SET ended_at = ?, status = ?, report_path = ?,
                       total_findings = ?
                   WHERE id = ?""",
                (_now(), status, str(report_path),
                 meta.get("total_findings", 0), run_id),
            )
            self.store.conn.commit()

            if status == "COMPLETED":
                try:
                    mgr_path = str(Path(__file__).resolve().parents[2] / "dispatch-manager" / "scripts")
                    if mgr_path not in sys.path:
                        sys.path.insert(0, mgr_path)
                    from optimus_manager import OptimusManager
                    om = OptimusManager()
                    om.ingest_findings(str(report_path))
                except Exception:
                    pass

            return report_path
        except Exception as e:
            self.store.conn.execute(
                "UPDATE optimus_runs SET ended_at = ?, status = 'FAILED' WHERE id = ?",
                (_now(), run_id),
            )
            self.store.conn.commit()
            raise

    def check_already_reviewed(self, date: str, period: str = "day") -> bool:
        start, end = _compute_date_range(date, period)
        row = self.store.conn.execute(
            """SELECT id FROM optimus_runs
               WHERE period_start = ? AND period_end = ? AND status = 'COMPLETED'
               LIMIT 1""",
            (start, end),
        ).fetchone()
        return row is not None

    def _day_dir(self, date: str) -> Path:
        if self.writer:
            return self.writer.day_dir(date)
        parts = date.split("-")
        return STATE_ROOT / parts[0] / parts[1] / parts[2]

    def _query_tasks_in_range(self, start, end):
        if start == end:
            return self.store.list_tasks(date=start)
        rows = self.store.conn.execute(
            """SELECT * FROM tasks
               WHERE created_date >= ? AND created_date <= ?
               ORDER BY priority ASC, created_date DESC""",
            (start, end + "T23:59:59"),
        ).fetchall()
        from state_store import _row_to_dict
        return [_row_to_dict(r, "tasks") for r in rows]

    def _collect_task_log_paths(self, tasks, date):
        paths = []
        for t in tasks:
            day_dir = self._day_dir(date)
            log_path = day_dir / "tasks" / t["task_id"] / "task_log.md"
            if log_path.exists():
                paths.append(str(log_path))
        return paths

    def _format_bash_history(self):
        rows = self.store.conn.execute(
            "SELECT timestamp, command FROM bash_log ORDER BY id DESC LIMIT 200"
        ).fetchall()
        if not rows:
            return "No bash command history available."
        lines = []
        for r in rows:
            ts = r["timestamp"] or ""
            if "T" in ts:
                ts = ts.split("T")[1][:8]
            lines.append(f"{ts} | {r['command']}")
        return "\n".join(reversed(lines))

    def _synthetic_report(self, marker, detail):
        return (
            f"---\nperiod_start: unknown\nperiod_end: unknown\n"
            f"tasks_reviewed: 0\ntotal_findings: 0\n"
            f"status: {marker}\n---\n\n"
            f"# Optimus Report ({marker})\n\n{detail}\n"
        )


def _run_tests():
    import tempfile
    import sqlite3

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore
    from log_writer import LogWriter

    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name}")

    tmpdir = tempfile.mkdtemp(prefix="optimus_test_")
    db_path = os.path.join(tmpdir, "test.db")

    with StateStore(db_path=db_path) as store:
        store.schema_init()
        writer = LogWriter(store, date="2026-04-02")
        writer_state_root = Path(tmpdir)

        original_state_root = globals().get("STATE_ROOT")

        import optimus_runner as mod
        old_sr = mod.STATE_ROOT
        old_wp = mod.WORKFLOW_PATH
        old_td = mod.TELEMETRY_DIR
        mod.STATE_ROOT = Path(tmpdir)
        mod.WORKFLOW_PATH = Path(tmpdir) / "workflow.yaml"
        mod.TELEMETRY_DIR = Path(tmpdir) / "telemetry"

        old_day_dir = LogWriter.day_dir
        def patched_day_dir(self_lw, date=None):
            d = date or self_lw._date
            parts = d.split("-")
            return Path(tmpdir) / parts[0] / parts[1] / parts[2]
        LogWriter.day_dir = patched_day_dir

        try:
            # Test 1: date range - day
            s, e = _compute_date_range("2026-04-02", "day")
            check("date_range_day", s == "2026-04-02" and e == "2026-04-02")

            # Test 2: date range - week
            s, e = _compute_date_range("2026-04-02", "week")
            check("date_range_week", s == "2026-03-30" and e == "2026-04-02")

            # Test 3: date range - month
            s, e = _compute_date_range("2026-04-02", "month")
            check("date_range_month", s == "2026-04-01" and e == "2026-04-02")

            # Test 4: generate_brief with data
            store.create_task("T-1", "Test task", priority=1)
            (Path(tmpdir) / "workflow.yaml").write_text("version: '1.0'\nsteps: []\n")

            runner = OptimusRunner(store, writer)
            brief_path = runner.generate_brief("2026-04-02")
            check("generate_brief_creates_file", brief_path.exists())
            content = brief_path.read_text()
            check("generate_brief_has_sections",
                  "## Review Period" in content and "## Bash Command History" in content)

            # Test 5: generate_brief with empty data
            store2_path = os.path.join(tmpdir, "test2.db")
            with StateStore(db_path=store2_path) as store2:
                store2.schema_init()
                writer2 = LogWriter(store2, date="2026-04-03")
                runner2 = OptimusRunner(store2, writer2)
                brief2 = runner2.generate_brief("2026-04-03")
                content2 = brief2.read_text()
                check("generate_brief_empty_data",
                      "Total: 0 tasks" in content2 and "Telemetry digest not available" in content2)

            # Test 6: parse_report with valid frontmatter
            report_content = (
                "---\nperiod_start: 2026-04-02\nperiod_end: 2026-04-02\n"
                "tasks_reviewed: 5\ntotal_findings: 3\n---\n\n# Report\n"
            )
            report_path = Path(tmpdir) / "test_report.md"
            report_path.write_text(report_content)
            meta = runner.parse_report(report_path)
            check("parse_report_valid",
                  meta.get("total_findings") == 3 or meta.get("total_findings") == "3")

            # Test 7: parse_report with malformed
            bad_path = Path(tmpdir) / "bad_report.md"
            bad_path.write_text("no frontmatter here")
            meta_bad = runner.parse_report(bad_path)
            check("parse_report_malformed", meta_bad.get("parse_error") is True)

            # Test 8: check_already_reviewed - no runs
            check("not_reviewed_yet", not runner.check_already_reviewed("2026-04-02"))

            # Test 9: check_already_reviewed - after completed run
            store.conn.execute(
                """INSERT INTO optimus_runs
                   (period_start, period_end, tasks_reviewed, started_at, status)
                   VALUES ('2026-04-05', '2026-04-05', 1, ?, 'COMPLETED')""",
                (_now(),),
            )
            store.conn.commit()
            check("reviewed_after_complete", runner.check_already_reviewed("2026-04-05"))

            # Test 10: write_report creates file
            wr_path = runner.write_report("# Test Report\n", "2026-04-02")
            check("write_report_creates_file", wr_path.exists() and wr_path.read_text() == "# Test Report\n")

            # Test 11: run() logs to optimus_runs
            # We need to mock invoke_agent for this test
            original_invoke = runner.invoke_agent
            runner.invoke_agent = lambda bp, t: (
                "---\ntasks_reviewed: 1\ntotal_findings: 0\n---\n\n# Mocked\n"
            )
            result_path = runner.run("2026-04-04")
            check("run_creates_report", result_path.exists())
            run_row = store.conn.execute(
                "SELECT status FROM optimus_runs WHERE period_start = '2026-04-04'"
            ).fetchone()
            check("run_logs_completed", run_row and run_row[0] == "COMPLETED")
            runner.invoke_agent = original_invoke

        finally:
            mod.STATE_ROOT = old_sr
            mod.WORKFLOW_PATH = old_wp
            mod.TELEMETRY_DIR = old_td
            LogWriter.day_dir = old_day_dir

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
    return failed == 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        success = _run_tests()
        sys.exit(0 if success else 1)

    parser = argparse.ArgumentParser(description="Optimus agent runner")
    parser.add_argument("--period", choices=["day", "week", "month"], default="day")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Generate brief only")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore
    from log_writer import LogWriter

    with StateStore() as store:
        store.schema_init()
        writer = LogWriter(store)
        runner = OptimusRunner(store, writer)

        if args.dry_run:
            path = runner.generate_brief(args.date or _today(), args.period)
            print(f"Brief generated at: {path}")
        else:
            report = runner.run(args.date, args.period)
            print(f"Report generated at: {report}")


if __name__ == "__main__":
    main()
