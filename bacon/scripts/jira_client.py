#!/usr/bin/env python3

import base64
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("Error: requests library required. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


JIRA_BASE = "https://abacusinsights.atlassian.net"


def browse_url(key: str) -> str:
    return f"{JIRA_BASE}/browse/{key}"


def portal_url(key: str) -> str:
    return f"{JIRA_BASE}/servicedesk/customer/portal/7/{key}"


class JiraClient:
    BASE_URL = JIRA_BASE
    SERVICE_DESK_ID = "7"
    REQUEST_TYPE_ID = "59"

    def __init__(self, username: Optional[str] = None, api_key: Optional[str] = None):
        self.username = username or os.environ.get("ATLASSIAN_USERNAME", "")
        self.api_key = api_key or os.environ.get("ATLASSIAN_API_KEY", "")
        if not self.username or not self.api_key:
            raise ValueError("ATLASSIAN_USERNAME and ATLASSIAN_API_KEY must be set")
        auth_str = base64.b64encode(f"{self.username}:{self.api_key}".encode()).decode()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _request(self, method: str, url: str, retries: int = 2, **kwargs) -> requests.Response:
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

    def get_issue_summary(self, ticket_id: str) -> str:
        url = f"{self.BASE_URL}/rest/api/3/issue/{ticket_id}?fields=summary"
        resp = self._request("GET", url)
        if resp.status_code == 200:
            return resp.json().get("fields", {}).get("summary", ticket_id)
        return ticket_id

    def create_cmd_ticket(self, summary: str, description_adf: Dict,
                          ticket_refs: str, test_plan: str,
                          rollback_plan: str = "Revert the release branch merge to master for each affected project.") -> Dict:
        url = f"{self.BASE_URL}/rest/servicedeskapi/request"
        payload = {
            "serviceDeskId": self.SERVICE_DESK_ID,
            "requestTypeId": self.REQUEST_TYPE_ID,
            "requestFieldValues": {
                "summary": summary,
                "description": description_adf,
                "customfield_10461": ticket_refs,
                "customfield_10229": rollback_plan,
                "customfield_10007": {"id": "10014"},
                "customfield_10416": test_plan,
                "customfield_10005": {"id": "10004"},
                "customfield_10006": {"id": "10010"},
            },
        }
        resp = self._request("POST", url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def browse_url(self, key: str) -> str:
        return f"{self.BASE_URL}/browse/{key}"

    def portal_url(self, key: str) -> str:
        return f"{self.BASE_URL}/servicedesk/customer/portal/7/{key}"


def build_adf_text(text: str) -> Dict:
    return {"type": "text", "text": text}


def build_adf_link(text: str, href: str) -> Dict:
    return {"type": "text", "text": text, "marks": [{"type": "link", "attrs": {"href": href}}]}


def build_adf_paragraph(content: List[Dict]) -> Dict:
    return {"type": "paragraph", "content": content}


def build_adf_bullet_list(items: List[str]) -> Dict:
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [build_adf_paragraph([build_adf_text(item)])]}
            for item in items
        ],
    }


def build_adf_table(headers: List[str], rows: List[List[Any]]) -> Dict:
    header_row = {
        "type": "tableRow",
        "content": [
            {"type": "tableHeader", "content": [build_adf_paragraph([build_adf_text(h)])]}
            for h in headers
        ],
    }
    data_rows = []
    for row in rows:
        cells = []
        for cell in row:
            if isinstance(cell, dict):
                cells.append({"type": "tableCell", "content": [build_adf_paragraph([cell])]})
            else:
                cells.append({"type": "tableCell", "content": [build_adf_paragraph([build_adf_text(str(cell))])]})
        data_rows.append({"type": "tableRow", "content": cells})

    return {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
        "content": [header_row] + data_rows,
    }


def build_cmd_description(version: str, release_type: str, projects: List[Dict],
                          tickets: List[Dict]) -> Dict:
    if release_type in ("AIR_ONLY", "ONYX_ONLY", "AIR_ONYX"):
        intro_text = f"This change releases {_release_label(release_type, version, projects)} to customers, including:"
    else:
        intro_text = f"This change releases NextGen {version} to customers, including:"

    project_items = []
    for p in projects:
        project_items.append(f"{p['name']} @ {p['next_tag']}")

    ticket_rows = []
    for t in tickets:
        link = build_adf_link(t["id"], f"https://abacusinsights.atlassian.net/browse/{t['id']}")
        ticket_rows.append([link, t.get("summary", t["id"]), "Yes" if t.get("breaking") else "No"])

    content = [build_adf_paragraph([build_adf_text(intro_text)])]
    if project_items:
        content.append(build_adf_bullet_list(project_items))
    if ticket_rows:
        content.append(build_adf_table(["Ticket", "Summary Notes", "Breaking?"], ticket_rows))

    return {"type": "doc", "version": 1, "content": content}


def _release_label(release_type: str, version: str, projects: List[Dict]) -> str:
    air_ver = None
    onyx_ver = None
    for p in projects:
        if p["name"] == "ng-abacus-insights-runtime":
            air_ver = p.get("next_tag", version)
        elif p["name"] == "ng-onyx-runtime":
            onyx_ver = p.get("next_tag", version)

    if release_type == "AIR_ONLY":
        return f"AIR {air_ver or version}"
    elif release_type == "ONYX_ONLY":
        return f"ONYX {onyx_ver or version}"
    elif release_type == "AIR_ONYX":
        parts = []
        if air_ver:
            parts.append(f"AIR {air_ver}")
        if onyx_ver:
            parts.append(f"ONYX {onyx_ver}")
        return " / ".join(parts) if parts else f"AIR/ONYX {version}"
    return f"NextGen {version}"


def load_from_env():
    creds_path = os.path.expanduser("~/.jira_creds.env")
    if os.path.exists(creds_path):
        with open(creds_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))
    return JiraClient()
