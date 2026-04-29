#!/usr/bin/env python3
"""
Direct Jira REST API v3 client — fallback when jiratui CLI lacks a capability.

Credentials are sourced from the jiratui config file at runtime (never cached).
Used for: full issue detail with linked issues, sprint data, issue creation,
transition validation, and bulk operations.

Usage (CLI):
    python scripts/jira_client.py issue PROJ-123
    python scripts/jira_client.py search "project = PROJ AND status = Open"
    python scripts/jira_client.py transitions PROJ-123
    python scripts/jira_client.py sprint --board-id 42
    python scripts/jira_client.py myself

Usage (module):
    from jira_client import JiraClient
    client = JiraClient()
    issue = client.get_issue("PROJ-123")
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("Error: requests library required. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("Error: pyyaml library required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def _load_jiratui_config() -> dict:
    """Load credentials from jiratui config file."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    candidates = []
    if xdg:
        candidates.append(Path(xdg) / "jiratui" / "config.yaml")
    candidates.append(Path.home() / ".config" / "jiratui" / "config.yaml")
    for c in candidates:
        if c.is_file():
            with open(c) as f:
                return yaml.safe_load(f) or {}
    raise FileNotFoundError("jiratui config not found")


class JiraClient:
    """Jira Cloud REST API v3 client with retry and pagination."""

    DEFAULT_SEARCH_FIELDS = [
        "summary", "status", "assignee", "priority",
        "updated", "created", "issuetype", "project",
        "labels", "reporter",
    ]

    def __init__(self, config: Optional[dict] = None):
        """
        Args:
            config: Optional dict with jira_api_username, jira_api_token,
                    jira_api_base_url. If None, loaded from jiratui config.
        """
        cfg = config or _load_jiratui_config()
        self.base_url = cfg["jira_api_base_url"].rstrip("/")
        self.session = requests.Session()
        self.session.auth = (cfg["jira_api_username"], cfg["jira_api_token"])
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _request(self, method: str, endpoint: str, retries: int = 2, **kwargs) -> requests.Response:
        """Make an API request with retry on 429 and 5xx."""
        url = f"{self.base_url}{endpoint}"
        for attempt in range(retries + 1):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                time.sleep(wait)
                continue
            if resp.status_code >= 500 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp

    def _text_to_adf(self, text):
        return {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
        }

    def get_myself(self) -> Dict[str, Any]:
        """GET /rest/api/3/myself — validate credentials and get current user."""
        resp = self._request("GET", "/rest/api/3/myself")
        resp.raise_for_status()
        return resp.json()

    def get_issue(self, issue_key: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch full issue detail including linked issues, subtasks, comments.

        Args:
            issue_key: e.g. "PROJ-123"
            fields: Optional list of field names to retrieve. None = all.

        Returns:
            Full Jira issue JSON response.
        """
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        resp = self._request("GET", f"/rest/api/3/issue/{issue_key}", params=params)
        resp.raise_for_status()
        return resp.json()

    def search_jql(self, jql: str, max_results: int = 100,
                   fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search issues via JQL with automatic pagination.

        Args:
            jql: JQL query string.
            max_results: Maximum total results to return.
            fields: Fields to include in results.

        Returns:
            List of issue dicts (all pages accumulated).
        """
        all_issues = []
        start_at = 0
        page_size = min(max_results, 50)
        if not fields:
            fields = self.DEFAULT_SEARCH_FIELDS
        while start_at < max_results:
            params = {"jql": jql, "startAt": start_at, "maxResults": page_size}
            if fields:
                params["fields"] = ",".join(fields)
            resp = self._request("GET", "/rest/api/3/search/jql", params=params)
            resp.raise_for_status()
            data = resp.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)
            if start_at + len(issues) >= data.get("total", 0) or not issues:
                break
            start_at += len(issues)
        return all_issues[:max_results]

    def get_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        GET /rest/api/3/issue/{key}/transitions — available status transitions.

        Returns:
            List of transition dicts with id, name, to status.
        """
        resp = self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        resp.raise_for_status()
        return resp.json()["transitions"]

    def create_issue(self, project_key: str, issue_type: str, summary: str,
                     **optional_fields) -> Dict[str, Any]:
        """
        POST /rest/api/3/issue — create a new issue.

        Args:
            project_key: e.g. "PROJ"
            issue_type: e.g. "Story", "Bug", "Task"
            summary: Issue summary text.
            **optional_fields: description, priority, assignee, labels, epic,
                               story_points, due_date.

        Returns:
            Created issue response with key and URL.
        """
        fields = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }
        if "description" in optional_fields:
            fields["description"] = self._text_to_adf(optional_fields["description"])
        if "priority" in optional_fields:
            fields["priority"] = {"name": optional_fields["priority"]}
        if "assignee" in optional_fields:
            fields["assignee"] = {"accountId": optional_fields["assignee"]}
        if "labels" in optional_fields:
            fields["labels"] = optional_fields["labels"]
        if "epic" in optional_fields:
            fields["customfield_10014"] = optional_fields["epic"]
        if "story_points" in optional_fields:
            fields["customfield_10028"] = optional_fields["story_points"]
        if "due_date" in optional_fields:
            fields["duedate"] = optional_fields["due_date"]
        resp = self._request("POST", "/rest/api/3/issue", json={"fields": fields})
        resp.raise_for_status()
        return resp.json()

    def update_issue(self, issue_key: str, **fields) -> Dict[str, Any]:
        """
        PUT /rest/api/3/issue/{key} — update issue fields.

        Args:
            issue_key: e.g. "PROJ-123"
            **fields: status, assignee, summary, labels, priority.
                      Status changes use transition API internally.

        Returns:
            Updated issue response.
        """
        status = fields.pop("status", None)
        if fields:
            update_fields = {}
            for key, value in fields.items():
                if key == "summary":
                    update_fields["summary"] = value
                elif key == "assignee":
                    update_fields["assignee"] = {"accountId": value}
                elif key == "priority":
                    update_fields["priority"] = {"name": value}
                elif key == "labels":
                    update_fields["labels"] = value
            if update_fields:
                resp = self._request("PUT", f"/rest/api/3/issue/{issue_key}",
                                     json={"fields": update_fields})
                resp.raise_for_status()
        if status:
            transitions = self.get_transitions(issue_key)
            match = next((t for t in transitions if t["name"].lower() == status.lower()), None)
            if not match:
                available = [t["name"] for t in transitions]
                raise ValueError(f"Status '{status}' not available. Available: {available}")
            self.transition_issue(issue_key, match["id"])
        return self.get_issue(issue_key)

    def transition_issue(self, issue_key: str, transition_id: str) -> bool:
        """
        POST /rest/api/3/issue/{key}/transitions — apply a status transition.

        Returns:
            True on success.
        """
        resp = self._request("POST", f"/rest/api/3/issue/{issue_key}/transitions",
                             json={"transition": {"id": str(transition_id)}})
        return resp.status_code == 204

    def get_sprint(self, board_id: int) -> Dict[str, Any]:
        """
        Fetch active sprint for a board via Agile REST API.

        Args:
            board_id: Jira board ID.

        Returns:
            Sprint data including issues grouped by status.
        """
        resp = self._request("GET", f"/rest/agile/1.0/board/{board_id}/sprint",
                             params={"state": "active"})
        resp.raise_for_status()
        sprints = resp.json().get("values", [])
        if not sprints:
            return {"error": "No active sprint found", "board_id": board_id}
        sprint = sprints[0]
        issue_resp = self._request("GET", f"/rest/agile/1.0/sprint/{sprint['id']}/issue",
                                   params={"maxResults": 100})
        issue_resp.raise_for_status()
        sprint["issues"] = issue_resp.json().get("issues", [])
        return sprint

    def get_issue_types(self, project_key: str) -> List[Dict[str, Any]]:
        """Fetch available issue types for a project."""
        resp = self._request("GET", f"/rest/api/3/issue/createmeta/{project_key}/issuetypes")
        resp.raise_for_status()
        data = resp.json()
        return data.get("issueTypes", data.get("values", []))

    def get_priorities(self) -> List[Dict[str, Any]]:
        """Fetch available priority levels."""
        resp = self._request("GET", "/rest/api/3/priority")
        resp.raise_for_status()
        return resp.json()

    def add_comment(self, issue_key: str, body: str) -> Dict[str, Any]:
        """
        POST /rest/api/3/issue/{key}/comment — add a comment.

        Returns:
            Created comment with ID.
        """
        adf_body = self._text_to_adf(body)
        resp = self._request("POST", f"/rest/api/3/issue/{issue_key}/comment",
                             json={"body": adf_body})
        resp.raise_for_status()
        return resp.json()

    def delete_comment(self, issue_key: str, comment_id: str) -> bool:
        """
        DELETE /rest/api/3/issue/{key}/comment/{id}.

        Returns:
            True on success.
        """
        resp = self._request("DELETE", f"/rest/api/3/issue/{issue_key}/comment/{comment_id}")
        return resp.status_code == 204

    def search_users(self, query: str) -> List[Dict[str, Any]]:
        """Search Jira users by name or email."""
        resp = self._request("GET", "/rest/api/3/user/search", params={"query": query})
        resp.raise_for_status()
        return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Jira REST API client")
    sub = parser.add_subparsers(dest="command", required=True)

    p_issue = sub.add_parser("issue", help="Fetch issue detail")
    p_issue.add_argument("key", help="Issue key (e.g. PROJ-123)")

    p_search = sub.add_parser("search", help="Search via JQL")
    p_search.add_argument("jql", help="JQL query string")
    p_search.add_argument("--max-results", type=int, default=100)

    p_trans = sub.add_parser("transitions", help="Get available transitions")
    p_trans.add_argument("key", help="Issue key")

    p_sprint = sub.add_parser("sprint", help="Fetch active sprint")
    p_sprint.add_argument("--board-id", type=int, required=True)

    sub.add_parser("myself", help="Validate credentials")

    args = parser.parse_args()
    client = JiraClient()

    if args.command == "issue":
        result = client.get_issue(args.key)
    elif args.command == "search":
        result = client.search_jql(args.jql, max_results=args.max_results)
    elif args.command == "transitions":
        result = client.get_transitions(args.key)
    elif args.command == "sprint":
        result = client.get_sprint(args.board_id)
    elif args.command == "myself":
        result = client.get_myself()
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
