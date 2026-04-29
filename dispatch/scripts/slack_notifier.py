#!/usr/bin/env python3
"""
Slack notification layer for dispatch.

Wraps the Slack MCP with content-hash deduplication and offline queuing.
Messages are always queued to dispatch.db; actual MCP delivery is handled
by dispatch_runner running inside a Claude session.

Usage (CLI):
    python scripts/slack_notifier.py send --message "text"
    python scripts/slack_notifier.py send-template --template-id task_started --data '{"task_id":"T-1"}'
    python scripts/slack_notifier.py flush
    python scripts/slack_notifier.py status

Usage (module):
    from slack_notifier import SlackNotifier
    notifier = SlackNotifier(store)
    notifier.send_template('task_started', {'task_id': 'T-1', 'title': 'Fix bug'})
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates" / "slack"

CHANNEL = "C0AQC48GL1G"

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    Environment = None
    FileSystemLoader = None


JIRA_BASE_URL = "https://abacusinsights.atlassian.net"
_JIRA_TICKET_RE = re.compile(r'(?<![A-Z])([A-Z]{2,}-\d+)')


def _jira_slack_link(text, base_url=JIRA_BASE_URL):
    def replacer(m):
        key = m.group(1)
        return f"<{base_url}/browse/{key}|{key}>"
    return _JIRA_TICKET_RE.sub(replacer, str(text))


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


class SlackNotifier:
    def __init__(self, store, channel=CHANNEL, dedup_window_hours=24):
        self.store = store
        self.channel = channel
        self.dedup_window_hours = dedup_window_hours
        self.jinja_env = None
        if Environment and TEMPLATE_DIR.is_dir():
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(TEMPLATE_DIR)),
                keep_trailing_newline=False,
            )
            self.jinja_env.filters["jira_link"] = _jira_slack_link

    def send(self, message, channel=None, template_id=None):
        ch = channel or self.channel
        if self._check_dedup(ch, message, template_id):
            return True
        self.store.queue_notification(ch, message, template_id)
        return True

    def send_template(self, template_id, context):
        message = self._render_template(template_id, context)
        return self.send(message, self.channel, template_id)

    def flush_queue(self):
        pending = self.store.get_pending_notifications()
        if not pending:
            return 0
        return len(pending)

    def is_available(self):
        return False

    def _compute_hash(self, channel, message, template_id=None):
        return hashlib.sha256(
            f"{channel}{template_id or ''}{message}".encode()
        ).hexdigest()

    def _check_dedup(self, channel, message, template_id=None):
        content_hash = self._compute_hash(channel, message, template_id)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=self.dedup_window_hours)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        row = self.store.conn.execute(
            """SELECT id FROM notifications
               WHERE content_hash = ?
                 AND status IN ('PENDING', 'SENT')
                 AND COALESCE(sent_at, queued_at, '1970-01-01') >= ?
               ORDER BY id DESC LIMIT 1""",
            (content_hash, cutoff),
        ).fetchone()
        return row is not None

    def _render_template(self, template_id, context):
        if self.jinja_env:
            try:
                tpl = self.jinja_env.get_template(f"{template_id}.md.j2")
                return tpl.render(**context).strip()
            except Exception:
                pass
        return f"[{template_id}] {json.dumps(context, default=str)}"


def main():
    parser = argparse.ArgumentParser(description="Dispatch Slack notifier")
    sub = parser.add_subparsers(dest="command", required=True)

    p_send = sub.add_parser("send", help="Send a message")
    p_send.add_argument("--message", required=True)
    p_send.add_argument("--channel", default=CHANNEL)
    p_send.add_argument("--template-id", default=None)

    p_tpl = sub.add_parser("send-template", help="Send from template")
    p_tpl.add_argument("--template-id", required=True)
    p_tpl.add_argument("--data", required=True, help="JSON context")

    sub.add_parser("flush", help="Flush pending queue")
    sub.add_parser("status", help="Show queue status")

    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state_store import StateStore

    with StateStore() as store:
        store.schema_init()
        notifier = SlackNotifier(store)

        if args.command == "send":
            notifier.send(args.message, args.channel, args.template_id)
            print("Queued")
        elif args.command == "send-template":
            ctx = json.loads(args.data)
            notifier.send_template(args.template_id, ctx)
            print("Queued")
        elif args.command == "flush":
            count = notifier.flush_queue()
            print(f"Pending: {count}")
        elif args.command == "status":
            pending = store.get_pending_notifications()
            print(f"Pending: {len(pending)}")
            for n in pending:
                print(f"  [{n['id']}] {n['channel']}: {n['message'][:60]}")


if __name__ == "__main__":
    main()
