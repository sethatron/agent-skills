#!/usr/bin/env python3
"""
Subprocess wrapper for the jiratui CLI tool.

All jiratui invocations go through this module to ensure consistent
--output json usage, stderr capture, and error surfacing.

Usage (CLI):
    python scripts/jiratui_runner.py issues search --project-key PROJ
    python scripts/jiratui_runner.py comments list PROJ-123
    python scripts/jiratui_runner.py users search "john"

Usage (module):
    from jiratui_runner import run_jiratui
    result = run_jiratui(["issues", "search", "--project-key", "PROJ"])
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml


JSON_SUPPORTED_COMMANDS = {
    "issues search",
    "comments list",
    "users search",
}


class JiratuiError(Exception):
    """Raised when jiratui exits with non-zero code."""

    def __init__(self, returncode: int, stderr: str, command: List[str]):
        self.returncode = returncode
        self.stderr = stderr
        self.command = command
        super().__init__(
            f"jiratui exited with code {returncode}: {stderr}"
        )


def run_jiratui(
    args: List[str],
    timeout: int = 60,
    json_output: bool = True,
) -> Dict[str, Any] | str:
    """
    Run a jiratui CLI command and return parsed output.

    Args:
        args: Command arguments (e.g. ["issues", "search", "--project-key", "PROJ"]).
        timeout: Subprocess timeout in seconds.
        json_output: If True and command supports it, append --output json
                     and parse the result. If False, return raw stdout.

    Returns:
        Parsed JSON dict if json_output=True, else raw stdout string.

    Raises:
        JiratuiError: On non-zero exit code.
        FileNotFoundError: If jiratui binary not found.
        json.JSONDecodeError: If JSON parsing fails on expected JSON output.
    """
    cmd = ["jiratui"] + list(args)
    cmd_prefix = " ".join(args[:2]) if len(args) >= 2 else ""
    if json_output and cmd_prefix in JSON_SUPPORTED_COMMANDS:
        cmd.extend(["--output", "json"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise FileNotFoundError("jiratui not found. Install: https://github.com/whyisdifficult/jiratui")
    except subprocess.TimeoutExpired:
        raise JiratuiError(-1, f"Timed out after {timeout}s", cmd)
    if result.returncode != 0:
        raise JiratuiError(result.returncode, result.stderr.strip(), cmd)
    if json_output and cmd_prefix in JSON_SUPPORTED_COMMANDS:
        return json.loads(result.stdout)
    return result.stdout.strip()


def _load_jira_config() -> Dict[str, str]:
    config_path = Path.home() / ".config" / "jiratui" / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _jql_via_rest(jql: str, max_results: int = 50) -> List[Dict[str, Any]]:
    cfg = _load_jira_config()
    base = cfg["jira_api_base_url"].rstrip("/")
    auth = (cfg["jira_api_username"], cfg["jira_api_token"])
    resp = requests.get(
        f"{base}/rest/api/3/search/jql",
        params={
            "jql": jql,
            "maxResults": max_results,
            "fields": ",".join([
                "summary", "status", "assignee", "priority",
                "updated", "created", "issuetype", "project",
                "labels", "comment", "reporter",
            ]),
        },
        auth=auth,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("issues", [])


def run_issues_search(
    project_key: Optional[str] = None,
    jql: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if jql:
        return _jql_via_rest(jql)
    args = ["issues", "search"]
    if project_key:
        args.extend(["--project-key", project_key])
    return run_jiratui(args)


def run_issues_update(
    issue_key: str,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    summary: Optional[str] = None,
    labels: Optional[List[str]] = None,
) -> str:
    """
    Update an issue via jiratui issues update.

    Returns:
        Raw output from jiratui.
    """
    args = ["issues", "update", issue_key]
    if status:
        args.extend(["--status", status])
    if assignee:
        args.extend(["--assignee", assignee])
    if summary:
        args.extend(["--summary", summary])
    if labels:
        args.extend(["--labels", ",".join(labels) if isinstance(labels, list) else labels])
    return run_jiratui(args, json_output=False)


def run_comments_list(issue_key: str) -> List[Dict[str, Any]]:
    """Fetch comments for an issue via jiratui comments list."""
    return run_jiratui(["comments", "list", issue_key])


def run_comments_add(issue_key: str, body: str) -> str:
    """Add a comment via jiratui comments add."""
    return run_jiratui(["comments", "add", issue_key, "--body", body], json_output=False)


def run_comments_delete(issue_key: str, comment_id: str) -> str:
    """Delete a comment via jiratui comments delete."""
    return run_jiratui(["comments", "delete", issue_key, "--comment-id", comment_id], json_output=False)


def run_users_search(query: str) -> List[Dict[str, Any]]:
    """Search users via jiratui users search."""
    return run_jiratui(["users", "search", query])


def main():
    parser = argparse.ArgumentParser(
        description="jiratui CLI wrapper"
    )
    sub = parser.add_subparsers(dest="command")

    p_raw = sub.add_parser("raw", help="Pass arguments directly to jiratui")
    p_raw.add_argument("args", nargs="+")
    p_raw.add_argument("--no-json", action="store_true")
    p_raw.add_argument("--timeout", type=int, default=60)

    p_dispatch = sub.add_parser("dispatch", help="Dispatch-compatible JQL search with export")
    p_dispatch.add_argument("--jql", required=True)
    p_dispatch.add_argument("--format", choices=["md", "json", "csv"], default="md")
    p_dispatch.add_argument("--timeout", type=int, default=60)

    p_mentions = sub.add_parser("mentions", help="Find comments @mentioning the operator")
    p_mentions.add_argument("--days", type=int, default=7)
    p_mentions.add_argument("--format", choices=["md", "json"], default="md")
    p_mentions.add_argument("--output", help="Output file path")

    parsed = parser.parse_args()

    if parsed.command == "dispatch":
        issues = run_issues_search(jql=parsed.jql)
        if not isinstance(issues, list):
            issues = []
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from export_writer import write_export
        path = write_export(issues, format=parsed.format)
        print(f"Exported {len(issues)} issues to: {path}")
    elif parsed.command == "mentions":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from mentions import run_mentions
        path = run_mentions(days=parsed.days, format=parsed.format, output=parsed.output)
        print(json.dumps({"output": path, "format": parsed.format}))
    elif parsed.command == "raw":
        try:
            result = run_jiratui(
                parsed.args,
                timeout=parsed.timeout,
                json_output=not parsed.no_json,
            )
            if isinstance(result, (dict, list)):
                print(json.dumps(result, indent=2))
            else:
                print(result)
        except JiratuiError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            sys.exit(e.returncode)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
