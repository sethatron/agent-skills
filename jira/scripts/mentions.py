#!/usr/bin/env python3
"""
Jira mentions scanner — finds comments @mentioning the operator.

Searches for Jira comments containing ADF mention nodes matching the
operator's account ID, or plain-text references to their display name.

Usage (CLI):
    python scripts/mentions.py --days 7 --format md
    python scripts/mentions.py --days 14 --format json --output /tmp/mentions.json

Usage (module):
    from mentions import run_mentions
    path = run_mentions(days=7, format="md")
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent

try:
    import yaml
    with open(SKILL_DIR / "config" / "jira.yaml") as f:
        _config = yaml.safe_load(f) or {}
except Exception:
    _config = {}

CACHE_PATH = Path(os.path.expanduser(
    _config.get("mentions_cache_path", "~/.cache/jira/account_id.json")
))
CACHE_TTL_HOURS = _config.get("mentions_cache_ttl_hours", 24)
DEFAULT_DAYS = _config.get("mentions_default_days", 7)
DEFAULT_OUTPUT = os.path.expanduser(
    _config.get("mentions_output_path", "~/.zsh/jira/exports/mentions_latest.md")
)
JIRA_BASE_URL = (
    _config.get("jira_api_base_url")
    or os.environ.get("JIRA_BASE_URL")
    or "https://abacusinsights.atlassian.net"
).rstrip("/")


def build_comment_url(issue_key: str, comment_id: str) -> str:
    return f"{JIRA_BASE_URL}/browse/{issue_key}?focusedCommentId={comment_id}"


def build_issue_url(issue_key: str) -> str:
    return f"{JIRA_BASE_URL}/browse/{issue_key}"


def _get_client():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from jira_client import JiraClient
    return JiraClient()


def get_my_account(client) -> dict:
    if CACHE_PATH.exists():
        try:
            cached = json.loads(CACHE_PATH.read_text())
            age_hours = (time.time() - cached.get("cached_at", 0)) / 3600
            if age_hours < CACHE_TTL_HOURS:
                return cached
        except (json.JSONDecodeError, KeyError):
            pass

    me = client.get_myself()
    account = {
        "account_id": me["accountId"],
        "display_name": me["displayName"],
        "cached_at": time.time(),
    }
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(account, indent=2))
    return account


def find_candidate_issues(client, display_name: str, days: int) -> list:
    first_name = display_name.split()[0] if display_name else ""
    queries = [
        f'comment ~ "{display_name}" AND updated >= -{days}d ORDER BY updated DESC',
        (
            f"(assignee = currentUser() OR watcher = currentUser()) "
            f"AND updated >= -{days}d "
            f"ORDER BY updated DESC"
        ),
    ]
    if first_name and first_name != display_name:
        queries.append(
            f'comment ~ "@{first_name}" AND updated >= -{days}d ORDER BY updated DESC'
        )

    seen = set()
    candidates = []
    for jql in queries:
        try:
            issues = client.search_jql(
                jql, max_results=50,
                fields=["summary", "status", "comment"]
            )
            for issue in issues:
                key = issue["key"]
                if key not in seen:
                    seen.add(key)
                    candidates.append(issue)
        except Exception as e:
            print(f"[WARN] JQL query failed: {e}", file=sys.stderr)
    return candidates


def extract_text_from_adf(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    parts = []
    ntype = node.get("type", "")
    if ntype == "text":
        parts.append(node.get("text", ""))
    elif ntype == "mention":
        parts.append("@" + node.get("attrs", {}).get("text", ""))
    elif ntype == "hardBreak":
        parts.append("\n")
    for child in node.get("content", []):
        parts.append(extract_text_from_adf(child))
    return "".join(parts)


def has_mention_node(node: Any, account_id: str) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("type") == "mention":
        if node.get("attrs", {}).get("id") == account_id:
            return True
    for child in node.get("content", []):
        if has_mention_node(child, account_id):
            return True
    return False


def scan_issue_for_mentions(
    issue: dict, account_id: str, display_name: str, cutoff: str
) -> list:
    fields = issue.get("fields", {})
    comments = fields.get("comment", {}).get("comments", [])
    key = issue.get("key", "?")
    summary = fields.get("summary", "")
    status = fields.get("status", {}).get("name", "?")
    matches = []

    for comment in comments:
        created = comment.get("created", "")
        if created[:10] < cutoff:
            continue

        author = comment.get("author", {})
        author_id = author.get("accountId", "")
        if author_id == account_id:
            continue

        body = comment.get("body", {})
        is_direct = has_mention_node(body, account_id)
        body_text = extract_text_from_adf(body)
        is_text_match = display_name.lower() in body_text.lower() if not is_direct else False

        if is_direct or is_text_match:
            comment_id = str(comment.get("id", ""))
            matches.append({
                "issue_key": key,
                "issue_summary": summary,
                "issue_status": status,
                "issue_url": build_issue_url(key),
                "comment_id": comment_id,
                "comment_url": build_comment_url(key, comment_id) if comment_id else build_issue_url(key),
                "comment_author": author.get("displayName", "?"),
                "comment_author_id": author_id,
                "comment_created": created,
                "comment_date": created[:10],
                "comment_excerpt": body_text[:300].replace("\n", " ").strip(),
                "mention_type": "direct" if is_direct else "text_reference",
            })

    return matches


def format_markdown(mentions: list, days: int, account_id: str) -> str:
    lines = [
        "---",
        f'generated_at: "{datetime.now(timezone.utc).isoformat()}"',
        f'account_id: "{account_id}"',
        f"days: {days}",
        f"mention_count: {len(mentions)}",
        "---",
        "",
        f"# Jira Mentions -- Past {days} Days",
        "",
    ]

    if not mentions:
        lines.append("No comments mentioning you in this period.")
        return "\n".join(lines) + "\n"

    lines.append("| Date | Issue | From | Comment |")
    lines.append("|------|-------|------|---------|")
    for m in sorted(mentions, key=lambda x: x["comment_date"], reverse=True):
        excerpt = m["comment_excerpt"][:120].replace("|", "\\|")
        summary = m["issue_summary"][:50].replace("|", "\\|")
        issue_cell = f'[{m["issue_key"]}]({m.get("comment_url") or m.get("issue_url", "")}) -- {summary}'
        lines.append(
            f'| {m["comment_date"]} '
            f'| {issue_cell} '
            f'| {m["comment_author"]} '
            f"| {excerpt} |"
        )

    return "\n".join(lines) + "\n"


def format_json(mentions: list, days: int, account_id: str) -> str:
    return json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id,
        "jira_base_url": JIRA_BASE_URL,
        "days": days,
        "mention_count": len(mentions),
        "mentions": sorted(mentions, key=lambda x: x["comment_date"], reverse=True),
    }, indent=2) + "\n"


def run_mentions(
    days: int = DEFAULT_DAYS,
    format: str = "md",
    output: Optional[str] = None,
) -> str:
    client = _get_client()
    account = get_my_account(client)
    account_id = account["account_id"]
    display_name = account["display_name"]

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    print(f"Scanning for mentions of {display_name} (past {days} days)...", file=sys.stderr)
    candidates = find_candidate_issues(client, display_name, days)
    print(f"  Found {len(candidates)} candidate issues", file=sys.stderr)

    all_mentions = []
    for issue in candidates:
        matches = scan_issue_for_mentions(issue, account_id, display_name, cutoff)
        all_mentions.extend(matches)

    print(f"  Found {len(all_mentions)} mentions", file=sys.stderr)

    if format == "json":
        content = format_json(all_mentions, days, account_id)
    else:
        content = format_markdown(all_mentions, days, account_id)

    out_path = Path(os.path.expanduser(output or DEFAULT_OUTPUT))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)

    # Always emit a JSON sibling alongside MD so downstream tools (e.g. the
    # dispatch morning dashboard) can consume structured data with comment URLs.
    if format != "json":
        json_sibling = out_path.with_suffix(".json")
        json_sibling.write_text(format_json(all_mentions, days, account_id))

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Find Jira comments mentioning you")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help=f"Look back N days (default: {DEFAULT_DAYS})")
    parser.add_argument("--format", choices=["md", "json"], default="md",
                        help="Output format (default: md)")
    parser.add_argument("--output", help="Output file path")
    args = parser.parse_args()

    path = run_mentions(days=args.days, format=args.format, output=args.output)
    result = {"output": path, "format": args.format}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
