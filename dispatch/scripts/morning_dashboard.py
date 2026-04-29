#!/usr/bin/env python3
"""Morning dispatch dashboard renderer.

Aggregates every morning artifact into a single structured Markdown dashboard
and writes it to ~/.zsh/dispatch/dashboards/YYYY-MM-DD.md.

Data sources:
  - dispatch.db                                     tasks, knowledge, events
  - ~/.zsh/review/YYYY/MM/DD/personal/mr_*/         personal MR reviews (frontmatter + findings.json)
  - ~/.zsh/review/YYYY/MM/DD/team/mr_*/             team MR reviews (frontmatter + findings.json)
  - ~/.zsh/jira/exports/mentions_latest.md          Jira @mentions scan (raw markdown embedded)
  - ~/.zsh/dispatch/briefings/YYYY-MM-DD.md         NotebookLM sequencing / cross-ticket briefing

Output:
  ~/.zsh/dispatch/dashboards/YYYY-MM-DD.md

Usage:
  python scripts/morning_dashboard.py render [--date YYYY-MM-DD] [--output PATH]
  python scripts/morning_dashboard.py render --stdout     # print to stdout only
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates" / "reports"
HOME = Path.home()
REVIEW_ROOT = HOME / ".zsh" / "review"
JIRA_EXPORT_DIR = HOME / ".zsh" / "jira" / "exports"
BRIEFING_DIR = HOME / ".zsh" / "dispatch" / "briefings"
DASHBOARD_DIR = HOME / ".zsh" / "dispatch" / "dashboards"
DB_PATH = HOME / ".zsh" / "dispatch" / "dispatch.db"

TZ_MST = timezone(timedelta(hours=-7))

SLA_TASK_IDLE_DAYS = 7
SLA_MENTION_STALE_HOURS = 48
SLA_MR_STALE_DAYS = 14
NOTEBOOK_STALE_HOURS = 72


def parse_frontmatter(path):
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


PIPELINE_BADGES = {
    "success": "🟢 success",
    "failed": "🔴 failed",
    "running": "🟡 running",
    "canceled": "⚫ canceled",
    "skipped": "⚪ skipped",
    "manual": "🟣 manual",
    "created": "🟡 created",
    "pending": "🟡 pending",
}


def pipeline_badge(status):
    if not status:
        return "⚪ none"
    return PIPELINE_BADGES.get(status, f"⚪ {status}")


def pipeline_badge_linked(status, url):
    label = pipeline_badge(status)
    if url and status and status != "none":
        emoji, word = label.split(" ", 1)
        return f"{emoji} [{word}]({url})"
    return label


def severity_abbrev(findings):
    counts = {"critical": 0, "major": 0, "minor": 0, "suggestion": 0}
    for f in findings:
        s = (f.get("severity") or "").lower()
        if s in counts:
            counts[s] += 1
    parts = []
    if counts["critical"]:
        parts.append(f"**{counts['critical']}C**")
    if counts["major"]:
        parts.append(f"{counts['major']}M")
    if counts["minor"]:
        parts.append(f"{counts['minor']}m")
    if counts["suggestion"]:
        parts.append(f"{counts['suggestion']}s")
    return " ".join(parts) or "—"


def mr_ref_linked(mr):
    iid = mr.get("mr_iid", "?")
    url = mr.get("mr_url", "")
    return f"[!{iid}]({url})" if url else f"!{iid}"


def repo_shortname(project):
    if not project:
        return ""
    return project.rsplit("/", 1)[-1]


def jira_linked(key, url):
    if not key:
        return "—"
    if url:
        return f"[{key}]({url})"
    return key


def parse_iso(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def days_since(ts):
    dt = parse_iso(ts)
    if not dt:
        return None
    return (datetime.now(tz=timezone.utc) - dt).days


def is_draft(mr):
    state = (mr.get("state") or "").lower()
    title = mr.get("title") or ""
    wip = bool(mr.get("work_in_progress"))
    return state == "draft" or title.startswith("Draft:") or wip


def project_web_url(mr_url):
    """Strip the `/-/merge_requests/<iid>` suffix from an MR URL."""
    if not mr_url:
        return ""
    m = re.match(r"(.*?)/-/merge_requests/\d+.*$", mr_url)
    return m.group(1) if m else ""


def _looks_like_path(value):
    """Return True only if the string looks like a real filesystem path.

    Rejects free-form finding notes like 'repo age / pipeline' or
    '.gitlab-ci.yml (implied) / pipeline' that some reviewers emit when a
    finding isn't pinned to a single file.
    """
    if not value:
        return False
    if " " in value or "(" in value or ")" in value:
        return False
    return True


def finding_file_url(mr, finding):
    """Build a deep link to the exact line of the offending file on the MR branch.

    Falls back to the MR diff page when branch or file is missing, or when
    the finding's `file` isn't a real path (e.g. a free-form note).
    GitLab serves `/-/blob/<branch>/<path>#L<line>` which takes you directly
    to the line as it exists on that branch.
    """
    mr_url = mr.get("mr_url") or ""
    branch = mr.get("source_branch") or ""
    file_path = (finding or {}).get("file") or ""
    line = (finding or {}).get("line") or ""
    web = project_web_url(mr_url)
    if not web or not branch or not _looks_like_path(file_path):
        return f"{mr_url}/diffs" if mr_url else ""
    line_frag = f"#L{line}" if str(line).strip() else ""
    return f"{web}/-/blob/{branch}/{file_path}{line_frag}"


def load_mr_reviews(scope_dir):
    if not scope_dir.exists():
        return []
    out = []
    for mr_dir in sorted(scope_dir.glob("mr_*")):
        review_md = mr_dir / "review.md"
        findings_json = mr_dir / "findings.json"
        if not review_md.exists():
            continue
        fm = parse_frontmatter(review_md)
        findings, verdict, verdict_summary = [], None, None
        if findings_json.exists():
            try:
                data = json.loads(findings_json.read_text())
                findings = data.get("findings", []) or []
                verdict = data.get("verdict")
                verdict_summary = data.get("verdict_summary")
            except (json.JSONDecodeError, OSError):
                pass
        for f in findings:
            f["file_url"] = finding_file_url(fm, f)
        fm["findings"] = findings
        fm["verdict"] = verdict
        fm["verdict_summary"] = verdict_summary
        fm["findings_abbrev"] = severity_abbrev(findings)
        fm["pipeline_cell"] = pipeline_badge_linked(fm.get("pipeline_status"), fm.get("pipeline_url"))
        fm["pipeline_status_badge"] = pipeline_badge(fm.get("pipeline_status"))
        fm["mr_ref"] = mr_ref_linked(fm)
        fm["repo"] = repo_shortname(fm.get("project"))
        fm["jira_cell"] = jira_linked(fm.get("jira_key"), fm.get("jira_url"))
        fm["is_draft"] = is_draft(fm)
        fm["conflicts_cell"] = "🟠 yes" if fm.get("has_conflicts") else "—"
        fm["review_dir"] = str(mr_dir)
        fm["project_web_url"] = project_web_url(fm.get("mr_url"))
        fm["review_age_days"] = days_since(fm.get("review_timestamp"))
        out.append(fm)
    return out


def load_tasks(db_path):
    if not db_path.exists():
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.execute(
        "SELECT * FROM tasks "
        "WHERE status IN ('IN_PROGRESS', 'PENDING', 'BLOCKED') "
        "ORDER BY priority ASC, started_at DESC, created_date DESC"
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    for t in rows:
        t["age_days"] = days_since(t.get("started_at") or t.get("created_date"))
        t["jira_url"] = f"https://abacusinsights.atlassian.net/browse/{t['task_id']}"
    return rows


def load_knowledge_recent(db_path, days=1):
    if not db_path.exists():
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            "SELECT * FROM knowledge WHERE created_at >= datetime('now', ? ) ORDER BY created_at DESC",
            (f"-{days} day",),
        )
        rows = [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        rows = []
    con.close()
    return rows


def load_mentions_markdown(export_dir):
    latest = export_dir / "mentions_latest.md"
    if latest.exists():
        return latest.read_text()
    candidates = sorted(export_dir.glob("mentions_*.md"), reverse=True)
    if candidates:
        return candidates[0].read_text()
    return ""


def load_mentions_json(export_dir):
    """Load structured mentions JSON (with comment_url deep-links)."""
    candidates = [
        export_dir / "mentions_latest.json",
    ]
    candidates += sorted(export_dir.glob("mentions_*.json"), reverse=True)
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
    return {}


def hours_since(ts):
    dt = parse_iso(ts)
    if not dt:
        return None
    return (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600


def build_ticket_rollup(tasks, all_mrs, mentions):
    """Aggregate every Jira ticket observed across tasks/MRs/mentions into a single row."""
    rollup = {}
    for t in tasks:
        key = t["task_id"]
        rollup.setdefault(key, _empty_rollup_row(key))
        rollup[key]["dispatch_status"] = t.get("status")
        rollup[key]["dispatch_priority"] = t.get("priority")
        rollup[key]["dispatch_age_days"] = t.get("age_days")
        rollup[key]["title"] = t.get("title") or rollup[key]["title"]
        rollup[key]["jira_url"] = t["jira_url"]
    for m in all_mrs:
        key = m.get("jira_key")
        if not key:
            continue
        rollup.setdefault(key, _empty_rollup_row(key))
        rollup[key]["jira_url"] = m.get("jira_url") or rollup[key]["jira_url"]
        rollup[key]["mrs"].append(m)
        for f in m.get("findings", []):
            sev = (f.get("severity") or "").lower()
            if sev in rollup[key]["finding_counts"]:
                rollup[key]["finding_counts"][sev] += 1
    for mention in mentions:
        key = mention.get("issue_key")
        if not key:
            continue
        rollup.setdefault(key, _empty_rollup_row(key))
        rollup[key]["jira_url"] = mention.get("issue_url") or rollup[key]["jira_url"]
        rollup[key]["mentions"].append(mention)
        rollup[key]["title"] = rollup[key]["title"] or mention.get("issue_summary", "")
    for key, row in rollup.items():
        if row["mentions"]:
            latest = max(row["mentions"], key=lambda x: x.get("comment_created", ""))
            row["latest_mention_url"] = latest.get("comment_url") or latest.get("issue_url")
            row["latest_mention_date"] = latest.get("comment_date")
            row["latest_mention_author"] = latest.get("comment_author")
        row["mr_count"] = len(row["mrs"])
        row["mention_count"] = len(row["mentions"])
        row["has_critical"] = row["finding_counts"]["critical"] > 0
        row["has_major"] = row["finding_counts"]["major"] > 0
    return sorted(
        rollup.values(),
        key=lambda r: (
            0 if r["has_critical"] else (1 if r["has_major"] else 2),
            r["dispatch_priority"] or 99,
            -(r["mention_count"]),
            r["jira_key"],
        ),
    )


def _empty_rollup_row(key):
    return {
        "jira_key": key,
        "jira_url": f"https://abacusinsights.atlassian.net/browse/{key}",
        "title": "",
        "dispatch_status": None,
        "dispatch_priority": None,
        "dispatch_age_days": None,
        "mrs": [],
        "mentions": [],
        "finding_counts": {"critical": 0, "major": 0, "minor": 0, "suggestion": 0},
        "latest_mention_url": None,
        "latest_mention_date": None,
        "latest_mention_author": None,
    }


def build_sla_watchlist(tasks, mentions):
    """Surface SLA breaches: idle tasks, stale @mentions."""
    idle_tasks = [
        t for t in tasks
        if t.get("status") == "IN_PROGRESS" and (t.get("age_days") or 0) >= SLA_TASK_IDLE_DAYS
    ]
    stale_pending = [
        t for t in tasks
        if t.get("status") == "PENDING" and (t.get("age_days") or 0) >= SLA_TASK_IDLE_DAYS
        and (t.get("priority") or 99) <= 2
    ]
    unreplied_mentions = []
    for m in mentions:
        hrs = hours_since(m.get("comment_created"))
        if hrs is not None and hrs >= SLA_MENTION_STALE_HOURS:
            entry = dict(m)
            entry["hours_old"] = round(hrs)
            unreplied_mentions.append(entry)
    return {
        "idle_tasks": idle_tasks,
        "stale_pending": stale_pending,
        "unreplied_mentions": unreplied_mentions,
        "thresholds": {
            "task_idle_days": SLA_TASK_IDLE_DAYS,
            "mention_stale_hours": SLA_MENTION_STALE_HOURS,
        },
    }


def assess_notebook_freshness(briefing_text):
    """Scan the briefing for cited date references; warn if oldest is >72h old."""
    if not briefing_text:
        return {"ok": False, "reason": "no_briefing", "oldest_days": None, "warnings": []}
    # Match YYYY-MM-DD dates cited in the briefing body
    dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", briefing_text)
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc))
        except ValueError:
            continue
    if not parsed:
        return {"ok": True, "reason": "no_dates_cited", "oldest_days": None, "warnings": []}
    oldest = min(parsed)
    age_hours = (datetime.now(tz=timezone.utc) - oldest).total_seconds() / 3600
    warnings = []
    if age_hours > NOTEBOOK_STALE_HOURS:
        warnings.append(
            f"Briefing cites source from {oldest.date().isoformat()} "
            f"({round(age_hours / 24, 1)}d old — exceeds {NOTEBOOK_STALE_HOURS}h threshold). "
            "Run `/dispatch-notebook update` to refresh sources."
        )
    return {
        "ok": len(warnings) == 0,
        "oldest_date": oldest.date().isoformat(),
        "oldest_days": round(age_hours / 24, 1),
        "warnings": warnings,
    }


def build_oneline_summary(counts, tasks_p1, sla, notebook_freshness):
    """Compress the dashboard into a single Slack-friendly summary line."""
    top = next((t for t in tasks_p1 if t.get("status") == "IN_PROGRESS"), None)
    top_str = f"🎯 {top['task_id']}" if top else "🎯 (no P1)"
    next_action = ""
    if sla["unreplied_mentions"]:
        m = sla["unreplied_mentions"][0]
        next_action = f"  ·  next: reply {m.get('comment_author')} on {m.get('issue_key')}"
    elif sla["idle_tasks"]:
        t = sla["idle_tasks"][0]
        next_action = f"  ·  next: advance {t['task_id']}"
    nb = "  ·  📚 stale" if not notebook_freshness.get("ok") and notebook_freshness.get("warnings") else ""
    return (
        f"{top_str}  ·  🔴{counts['critical']}  🟠{counts['major']}"
        f"  🔺{counts['failed_pipelines']}  ⏳{len(sla['idle_tasks'])}"
        f"  📨{counts.get('mention_count', 0)}{nb}{next_action}"
    )


def extract_sequencing_section(briefing_text):
    if not briefing_text:
        return ""
    match = re.search(
        r"(?:^|\n)(#{1,3}\s*(?:Sequencing|Cross-?[Tt]icket|Risks|Watch[- ]?list|Risk).*?)(?=\n#{1,3}\s|\Z)",
        briefing_text,
        flags=re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def split_team_by_verdict(team_mrs):
    non_draft = [m for m in team_mrs if not m["is_draft"]]
    return {
        "request_changes": [m for m in non_draft if m["verdict"] == "REQUEST_CHANGES"],
        "comment": [m for m in non_draft if m["verdict"] == "COMMENT"],
        "approve": [m for m in non_draft if m["verdict"] == "APPROVE"],
        "unreviewed": [m for m in non_draft if not m["verdict"]],
        "drafts": [m for m in team_mrs if m["is_draft"]],
    }


def collect_findings_by_severity(mrs, severity):
    out = []
    for m in mrs:
        for f in m.get("findings", []):
            if (f.get("severity") or "").lower() == severity:
                out.append({"mr": m, "finding": f})
    return out


def build_context(target_date):
    scope_root = REVIEW_ROOT / f"{target_date.year:04d}" / f"{target_date.month:02d}" / f"{target_date.day:02d}"
    personal_mrs = load_mr_reviews(scope_root / "personal")
    team_mrs = load_mr_reviews(scope_root / "team")
    by_verdict = split_team_by_verdict(team_mrs)

    tasks = load_tasks(DB_PATH)
    knowledge_recent = load_knowledge_recent(DB_PATH, days=1)

    mentions_md = load_mentions_markdown(JIRA_EXPORT_DIR)
    mentions_data = load_mentions_json(JIRA_EXPORT_DIR)
    mentions = mentions_data.get("mentions", []) if mentions_data else []

    briefing_path = BRIEFING_DIR / f"{target_date.isoformat()}.md"
    briefing_text = briefing_path.read_text() if briefing_path.exists() else ""
    sequencing_section = extract_sequencing_section(briefing_text)
    notebook_freshness = assess_notebook_freshness(briefing_text)

    all_mrs = personal_mrs + team_mrs
    all_non_draft = [m for m in all_mrs if not m["is_draft"]]
    failed_pipelines = [m for m in all_non_draft if m.get("pipeline_status") == "failed"]
    conflicts = [m for m in all_mrs if m.get("has_conflicts")]

    critical = collect_findings_by_severity(all_mrs, "critical")
    major = collect_findings_by_severity(all_mrs, "major")

    ticket_rollup = build_ticket_rollup(tasks, all_mrs, mentions)

    sla = build_sla_watchlist(tasks, mentions)

    counts = {
        "personal_non_draft": len([m for m in personal_mrs if not m["is_draft"]]),
        "personal_drafts": len([m for m in personal_mrs if m["is_draft"]]),
        "team_non_draft": len([m for m in team_mrs if not m["is_draft"]]),
        "team_drafts": len([m for m in team_mrs if m["is_draft"]]),
        "request_changes": len(by_verdict["request_changes"]),
        "comment": len(by_verdict["comment"]),
        "approve": len(by_verdict["approve"]),
        "unreviewed": len(by_verdict["unreviewed"]),
        "critical": len(critical),
        "major": len(major),
        "failed_pipelines": len(failed_pipelines),
        "conflicts": len(conflicts),
        "active_tasks": len(tasks),
        "mention_count": len(mentions),
        "unreplied_mentions": len(sla["unreplied_mentions"]),
        "idle_tasks": len(sla["idle_tasks"]),
    }

    tasks_p1 = [t for t in tasks if t.get("priority") == 1]

    oneline_summary = build_oneline_summary(counts, tasks_p1, sla, notebook_freshness)

    jira_export_files = sorted(JIRA_EXPORT_DIR.glob(f"jira_export_{target_date.strftime('%Y%m%d')}_*.md"), reverse=True)
    jira_export_path = str(jira_export_files[0]) if jira_export_files else ""

    latest_mentions_path = JIRA_EXPORT_DIR / "mentions_latest.md"

    context = {
        "date": target_date.isoformat(),
        "weekday": target_date.strftime("%a"),
        "now_local": datetime.now(tz=TZ_MST).strftime("%I:%M %p MST"),
        "oneline_summary": oneline_summary,
        "personal_mrs": personal_mrs,
        "personal_non_draft": [m for m in personal_mrs if not m["is_draft"]],
        "personal_drafts": [m for m in personal_mrs if m["is_draft"]],
        "team_mrs": team_mrs,
        "team_by_verdict": by_verdict,
        "tasks": tasks,
        "tasks_p1": tasks_p1,
        "tasks_p2": [t for t in tasks if t.get("priority") == 2],
        "tasks_p3_plus": [t for t in tasks if (t.get("priority") or 99) >= 3],
        "knowledge_recent": knowledge_recent,
        "mentions": mentions,
        "mentions_md": mentions_md,
        "mentions_data": mentions_data,
        "briefing_text": briefing_text,
        "sequencing_section": sequencing_section,
        "notebook_freshness": notebook_freshness,
        "failed_pipelines": failed_pipelines,
        "conflicts": conflicts,
        "critical_findings": critical,
        "major_findings": major,
        "ticket_rollup": ticket_rollup,
        "sla": sla,
        "counts": counts,
        "paths": {
            "personal_index": str(scope_root / "personal" / "README.md"),
            "team_index": str(scope_root / "team" / "README.md"),
            "briefing": str(briefing_path),
            "mentions": str(latest_mentions_path),
            "mentions_json": str(JIRA_EXPORT_DIR / "mentions_latest.json"),
            "jira_export": jira_export_path,
            "dashboard_self": str(DASHBOARD_DIR / f"{target_date.isoformat()}.md"),
            "oneline_txt": str(DASHBOARD_DIR / f"{target_date.isoformat()}.oneline.txt"),
        },
    }
    return context


def render(target_date, output_path=None, to_stdout=False):
    ctx = build_context(target_date)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("morning_dashboard.md.j2")
    rendered = tmpl.render(**ctx)
    if to_stdout:
        sys.stdout.write(rendered)
        return None
    out = Path(output_path) if output_path else (DASHBOARD_DIR / f"{target_date.isoformat()}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered)
    # Emit a one-line companion file for Slack cards / phone glances.
    oneline_path = out.with_suffix(".oneline.txt")
    oneline_path.write_text(ctx["oneline_summary"] + "\n")
    return out


def main():
    p = argparse.ArgumentParser(prog="morning_dashboard")
    p.add_argument("command", nargs="?", default="render", choices=["render"],
                   help="Action to perform (default: render)")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--output", help="Output path override")
    p.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing a file")
    args = p.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    out = Path(args.output) if args.output else None
    result = render(target, out, to_stdout=args.stdout)
    if result:
        print(result)


if __name__ == "__main__":
    main()
