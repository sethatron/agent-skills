#!/usr/bin/env python3
"""
Telemetry digest builder for the dispatch-harness skill.

Usage:
    python scripts/telemetry_builder.py [--days 7] [--date YYYY-MM-DD] [--json]
"""

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

DB_PATH = Path.home() / ".zsh" / "dispatch" / "dispatch.db"
DIGEST_DIR = Path.home() / ".zsh" / "dispatch" / "harness" / "telemetry"
SESSIONS_DIR = Path.home() / ".zsh" / "dispatch" / "sessions"
ARCH_VIOLATIONS_LOG = Path.home() / ".zsh" / "dispatch" / "harness" / "arch-violations.log"


@dataclass
class StepStats:
    step_id: str
    runs: int
    failures: int
    verify_failures: int
    avg_tool_calls: float
    avg_duration_seconds: float
    fragility_score: float


@dataclass
class DriftEvent:
    session_id: str
    date: str
    step_id: str
    description: str


@dataclass
class ContextStats:
    avg_tokens_start: int
    avg_tokens_end: int
    week_on_week_change_pct: float


class TelemetryBuilder:
    def __init__(self):
        self.db_available = DB_PATH.exists()

    def _db_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def load_sessions(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        if self.db_available:
            try:
                conn = self._db_connect()
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE date >= ? ORDER BY date DESC", (cutoff,)
                ).fetchall()
                conn.close()
                if rows:
                    return [dict(r) for r in rows]
            except Exception:
                pass

        return self._load_sessions_from_yaml(cutoff)

    def _load_sessions_from_yaml(self, cutoff: str) -> list[dict]:
        if not SESSIONS_DIR.is_dir() or yaml is None:
            return []

        sessions = []
        for path in sorted(SESSIONS_DIR.iterdir(), reverse=True):
            if not path.suffix in (".yaml", ".yml"):
                continue
            try:
                data = yaml.safe_load(path.read_text())
                if not isinstance(data, dict):
                    continue
                session_date = data.get("date", "")
                if isinstance(session_date, datetime):
                    session_date = session_date.strftime("%Y-%m-%d")
                elif hasattr(session_date, "isoformat"):
                    session_date = str(session_date)
                if session_date and session_date >= cutoff:
                    sessions.append({
                        "session_id": data.get("session_id", path.stem),
                        "date": session_date,
                        "status": data.get("status", "unknown"),
                        "steps_completed": data.get("steps_completed", 0),
                        "steps_failed": data.get("steps_failed", 0),
                        "tasks_started": data.get("tasks_started", 0),
                        "tasks_completed": data.get("tasks_completed", 0),
                        "bottleneck_count": data.get("bottleneck_count", 0),
                        "slack_messages_sent": data.get("slack_messages_sent", 0),
                        "bash_commands_executed": data.get("bash_commands_executed", 0),
                        "context_window_compactions": data.get("context_window_compactions", 0),
                        "started_at": data.get("started_at"),
                        "ended_at": data.get("ended_at"),
                    })
            except Exception:
                continue
        return sessions

    def load_step_logs(self, session_ids: list[str]) -> list[dict]:
        if not session_ids:
            return []

        if self.db_available:
            try:
                conn = self._db_connect()
                placeholders = ",".join("?" for _ in session_ids)
                rows = conn.execute(
                    f"SELECT * FROM step_log WHERE session_id IN ({placeholders})",
                    session_ids,
                ).fetchall()
                conn.close()
                if rows:
                    return [dict(r) for r in rows]
            except Exception:
                pass

        return self._load_step_logs_from_yaml(session_ids)

    def _load_step_logs_from_yaml(self, session_ids: list[str]) -> list[dict]:
        if not SESSIONS_DIR.is_dir() or yaml is None:
            return []

        id_set = set(session_ids)
        logs = []
        for path in SESSIONS_DIR.iterdir():
            if path.suffix not in (".yaml", ".yml"):
                continue
            try:
                data = yaml.safe_load(path.read_text())
                if not isinstance(data, dict):
                    continue
                sid = data.get("session_id", path.stem)
                if sid not in id_set:
                    continue
                for step in data.get("steps", []):
                    logs.append({
                        "session_id": sid,
                        "step_id": step.get("step_id", step.get("id", "unknown")),
                        "status": step.get("status", "unknown"),
                        "started_at": step.get("started_at"),
                        "ended_at": step.get("ended_at"),
                        "artifact_path": step.get("artifact_path"),
                        "error": step.get("error"),
                        "tool_calls_count": step.get("tool_calls_count", 0),
                    })
            except Exception:
                continue
        return logs

    def compute_step_stats(self, step_logs: list[dict]) -> dict[str, StepStats]:
        grouped: dict[str, list[dict]] = {}
        for log in step_logs:
            sid = log.get("step_id", "unknown")
            grouped.setdefault(sid, []).append(log)

        stats = {}
        for step_id, entries in grouped.items():
            runs = len(entries)
            failures = sum(1 for e in entries if e.get("status") in ("FAILED", "INTERRUPTED"))
            verify_failures = sum(
                1 for e in entries
                if e.get("status") == "FAILED" and "verify" in (e.get("step_id") or "").lower()
            )

            tool_calls = [e.get("tool_calls_count", 0) or 0 for e in entries]
            avg_tool_calls = sum(tool_calls) / max(len(tool_calls), 1)

            durations = []
            for e in entries:
                start = e.get("started_at")
                end = e.get("ended_at")
                if start and end:
                    try:
                        s = datetime.fromisoformat(str(start))
                        n = datetime.fromisoformat(str(end))
                        durations.append((n - s).total_seconds())
                    except (ValueError, TypeError):
                        pass
            avg_duration = sum(durations) / max(len(durations), 1) if durations else 0.0

            fragility = (failures + verify_failures) / max(runs, 1)

            stats[step_id] = StepStats(
                step_id=step_id,
                runs=runs,
                failures=failures,
                verify_failures=verify_failures,
                avg_tool_calls=round(avg_tool_calls, 1),
                avg_duration_seconds=round(avg_duration, 1),
                fragility_score=round(fragility, 3),
            )

        return stats

    def compute_drift_events(self, sessions: list[dict]) -> list[DriftEvent]:
        events = []
        for s in sessions:
            compactions = s.get("context_window_compactions") or 0
            failed_steps = s.get("steps_failed") or 0
            drift_score = compactions * 0.1 + failed_steps * 0.15

            if drift_score > 0.3:
                step_hint = "multiple_steps" if failed_steps > 1 else "session_level"
                events.append(DriftEvent(
                    session_id=s.get("session_id", "unknown"),
                    date=str(s.get("date", "unknown")),
                    step_id=step_hint,
                    description=f"drift {drift_score:.2f} (compactions={compactions}, failed_steps={failed_steps})",
                ))
        return events

    def compute_context_stats(self, sessions: list[dict]) -> ContextStats:
        if not sessions:
            return ContextStats(avg_tokens_start=0, avg_tokens_end=0, week_on_week_change_pct=0.0)

        bash_counts = [s.get("bash_commands_executed") or 0 for s in sessions]
        if not any(bash_counts):
            return ContextStats(avg_tokens_start=0, avg_tokens_end=0, week_on_week_change_pct=0.0)

        TOKEN_PER_COMMAND_ESTIMATE = 800
        avg_commands = sum(bash_counts) / len(bash_counts)
        est_start = int(avg_commands * TOKEN_PER_COMMAND_ESTIMATE * 0.3)
        est_end = int(avg_commands * TOKEN_PER_COMMAND_ESTIMATE)

        sorted_sessions = sorted(sessions, key=lambda x: str(x.get("date", "")))
        mid = len(sorted_sessions) // 2
        if mid > 0:
            first_half = sorted_sessions[:mid]
            second_half = sorted_sessions[mid:]
            avg_first = sum(s.get("bash_commands_executed") or 0 for s in first_half) / len(first_half)
            avg_second = sum(s.get("bash_commands_executed") or 0 for s in second_half) / len(second_half)
            if avg_first > 0:
                wow_change = ((avg_second - avg_first) / avg_first) * 100
            else:
                wow_change = 0.0
        else:
            wow_change = 0.0

        return ContextStats(
            avg_tokens_start=est_start,
            avg_tokens_end=est_end,
            week_on_week_change_pct=round(wow_change, 1),
        )

    def load_arch_violations(self) -> list[str]:
        if not ARCH_VIOLATIONS_LOG.is_file():
            return []
        try:
            lines = ARCH_VIOLATIONS_LOG.read_text().strip().splitlines()
            return lines[-50:]
        except Exception:
            return []

    def build_digest(self, date: str = None, days: int = 7) -> str:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        sessions = self.load_sessions(days=days)
        n = len(sessions)

        if n == 0:
            return (
                f"# Telemetry Digest -- {date}\n"
                f"Source: last 0 sessions\n\n"
                f"No session data available. This digest will populate after dispatch workflow sessions run.\n"
            )

        session_ids = [s.get("session_id") for s in sessions if s.get("session_id")]
        step_logs = self.load_step_logs(session_ids)
        step_stats = self.compute_step_stats(step_logs)
        drift_events = self.compute_drift_events(sessions)
        ctx_stats = self.compute_context_stats(sessions)
        violations = self.load_arch_violations()

        lines = [
            f"# Telemetry Digest -- {date}",
            f"Source: last {n} sessions",
            "",
        ]

        lines.append("## Step Performance")
        if step_stats:
            lines.append("| Step | Runs | Failures | Verify Fails | Avg Tool Calls | Avg Duration |")
            lines.append("|---|---|---|---|---|---|")
            for ss in sorted(step_stats.values(), key=lambda x: -x.fragility_score):
                dur = f"{ss.avg_duration_seconds:.0f}s" if ss.avg_duration_seconds else "n/a"
                lines.append(
                    f"| {ss.step_id} | {ss.runs} | {ss.failures} | {ss.verify_failures} "
                    f"| {ss.avg_tool_calls} | {dur} |"
                )
        else:
            lines.append("No step log data available.")
        lines.append("")

        lines.append("## Fragility Ranking")
        if step_stats:
            ranked = sorted(step_stats.values(), key=lambda x: -x.fragility_score)
            most_fragile = ranked[0]
            most_reliable = ranked[-1]
            lines.append(f"Most fragile: {most_fragile.step_id} ({most_fragile.failures} failures)")
            lines.append(f"Most reliable: {most_reliable.step_id} ({most_reliable.failures} failures)")
        else:
            lines.append("No step data to rank.")
        lines.append("")

        lines.append("## Drift Events")
        if drift_events:
            lines.append(f"{len(drift_events)} sessions with drift_score > 0.3:")
            for de in drift_events:
                lines.append(f"- {de.date}: {de.description} at step {de.step_id}")
        else:
            lines.append("No drift events detected.")
        lines.append("")

        lines.append("## Context Window")
        if ctx_stats.avg_tokens_end > 0:
            sign = "+" if ctx_stats.week_on_week_change_pct >= 0 else ""
            lines.append(
                f"Avg tokens at start: {ctx_stats.avg_tokens_start} "
                f"| Avg at end: {ctx_stats.avg_tokens_end} "
                f"| Week-on-week: {sign}{ctx_stats.week_on_week_change_pct}%"
            )
        else:
            lines.append("Insufficient data for context window estimates.")
        lines.append("")

        lines.append("## Architecture Violations")
        if violations:
            lines.append(f"{len(violations)} violations this period:")
            for v in violations:
                lines.append(f"- {v}")
        else:
            lines.append("None")
        lines.append("")

        return "\n".join(lines)

    def build_json(self, date: str = None, days: int = 7) -> dict:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        sessions = self.load_sessions(days=days)
        n = len(sessions)

        if n == 0:
            return {"date": date, "session_count": 0, "message": "no session data"}

        session_ids = [s.get("session_id") for s in sessions if s.get("session_id")]
        step_logs = self.load_step_logs(session_ids)
        step_stats = self.compute_step_stats(step_logs)
        drift_events = self.compute_drift_events(sessions)
        ctx_stats = self.compute_context_stats(sessions)
        violations = self.load_arch_violations()

        return {
            "date": date,
            "session_count": n,
            "days": days,
            "step_stats": {k: asdict(v) for k, v in step_stats.items()},
            "drift_events": [asdict(de) for de in drift_events],
            "context_stats": asdict(ctx_stats),
            "arch_violations": violations,
        }

    def write_digest(self, date: str = None, days: int = 7) -> Path:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        content = self.build_digest(date=date, days=days)
        path = DIGEST_DIR / f"{date}-digest.md"
        path.write_text(content)
        return path


def main():
    parser = argparse.ArgumentParser(description="Dispatch telemetry digest builder")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    builder = TelemetryBuilder()

    if args.json:
        result = builder.build_json(date=args.date, days=args.days)
        print(json.dumps(result, indent=2, default=str))
    else:
        path = builder.write_digest(date=args.date, days=args.days)
        content = path.read_text()
        print(content)
        print(f"---\nWritten to: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
