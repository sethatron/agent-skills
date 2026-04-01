#!/usr/bin/env python3

import os
import re
import sys
import time
import urllib.parse
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("Error: requests library required. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


class GitLabClient:
    API_BASE = "https://gitlab.com/api/v4"
    GROUP_ID = 13931987
    PROJECT_PREFIX = "abacusinsights/abacus-v2/next-gen-platform"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITLAB_TOKEN", "")
        if not self.token:
            raise ValueError("GITLAB_TOKEN not set")
        self.session = requests.Session()
        self.session.headers.update({
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _encode_project(self, project_path: str) -> str:
        return urllib.parse.quote(project_path, safe="")

    def _full_project_path(self, project_name: str) -> str:
        return f"{self.PROJECT_PREFIX}/{project_name}"

    def _encoded_full_path(self, project_name: str) -> str:
        return self._encode_project(self._full_project_path(project_name))

    def _request(self, method: str, endpoint: str, retries: int = 2, **kwargs) -> requests.Response:
        url = f"{self.API_BASE}{endpoint}"
        for attempt in range(retries + 1):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"Rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if resp.status_code >= 500 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        resp = self._request("GET", endpoint, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, json_data: Dict) -> Any:
        resp = self._request("POST", endpoint, json=json_data)
        resp.raise_for_status()
        return resp.json()

    def _put(self, endpoint: str, json_data: Dict) -> Any:
        resp = self._request("PUT", endpoint, json=json_data)
        resp.raise_for_status()
        return resp.json()

    def get_mr(self, project_name: str, mr_iid: int) -> Dict:
        encoded = self._encoded_full_path(project_name)
        return self._get(f"/projects/{encoded}/merge_requests/{mr_iid}")

    def find_mr_by_branch(self, project_name: str, source_branch: str, state: str = "opened") -> Optional[Dict]:
        encoded = self._encoded_full_path(project_name)
        results = self._get(
            f"/projects/{encoded}/merge_requests",
            params={"source_branch": source_branch, "state": state},
        )
        if isinstance(results, list) and len(results) > 0:
            return results[0]
        return None

    def create_mr(self, project_name: str, source_branch: str, target_branch: str,
                  title: str, description: str, merge_when_pipeline_succeeds: bool = False,
                  draft: bool = False) -> Dict:
        existing = self.find_mr_by_branch(project_name, source_branch)
        if existing:
            return self.update_mr(
                project_name, existing["iid"], title=title, description=description
            )

        encoded = self._encoded_full_path(project_name)
        payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
        }
        if merge_when_pipeline_succeeds:
            payload["merge_when_pipeline_succeeds"] = True
        if draft:
            payload["title"] = f"Draft: {title}" if not title.startswith("Draft:") else title
        return self._post(f"/projects/{encoded}/merge_requests", payload)

    def update_mr(self, project_name: str, mr_iid: int, **fields) -> Dict:
        encoded = self._encoded_full_path(project_name)
        return self._put(f"/projects/{encoded}/merge_requests/{mr_iid}", fields)

    def search_breaking_mrs(self, ticket_id: str) -> bool:
        try:
            results = self._get(
                f"/groups/{self.GROUP_ID}/merge_requests",
                params={"scope": "all", "labels": "breaking", "search": ticket_id, "in": "title"},
            )
            return isinstance(results, list) and len(results) > 0
        except Exception:
            return False

    def get_merge_commit_sha(self, project_name: str, mr_iid: int) -> Optional[str]:
        mr = self.get_mr(project_name, mr_iid)
        return mr.get("merge_commit_sha")

    def is_mr_merged(self, project_name: str, mr_iid: int) -> bool:
        mr = self.get_mr(project_name, mr_iid)
        return mr.get("state") == "merged"

    def mr_web_url(self, project_name: str, mr_iid: int) -> str:
        return f"https://gitlab.com/{self._full_project_path(project_name)}/-/merge_requests/{mr_iid}"

    def project_web_url(self, project_name: str) -> str:
        return f"https://gitlab.com/{self._full_project_path(project_name)}"


def load_from_env():
    creds_path = os.path.expanduser("~/.jira_creds.env")
    if os.path.exists(creds_path):
        with open(creds_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))
    return GitLabClient()
