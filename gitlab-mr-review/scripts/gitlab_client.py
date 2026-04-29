#!/usr/bin/env python3
"""
Paginated GitLab REST API client for MR review operations.

Handles all pagination transparently via X-Next-Page headers.
Token sourced from GITLAB_TOKEN env var. Base URL from GITLAB_URL
(default: https://gitlab.com).

Usage (CLI):
    python scripts/gitlab_client.py mrs-by-authors @user1 @user2 --state opened
    python scripts/gitlab_client.py mr-by-url "https://gitlab.com/.../merge_requests/42"
    python scripts/gitlab_client.py validate-scopes
    python scripts/gitlab_client.py --dry-run mrs-by-authors @user1

Usage (module):
    from gitlab_client import GitLabClient
    client = GitLabClient()
    mrs = client.fetch_mrs_by_authors(["@user1", "@user2"])
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("Error: requests library required. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

TOKEN_ENV_PATH = Path(os.path.expanduser("~/.config/git/token.env"))


def _load_token_env():
    if os.environ.get("GITLAB_TOKEN"):
        return
    if TOKEN_ENV_PATH.exists():
        for line in TOKEN_ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("export GITLAB_TOKEN="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["GITLAB_TOKEN"] = value
                return


class GitLabClient:
    """GitLab REST API v4 client with pagination and retry."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        dry_run: bool = False,
    ):
        """
        Args:
            token: GitLab PAT. Defaults to GITLAB_TOKEN env var.
            base_url: GitLab instance URL. Defaults to GITLAB_URL env or https://gitlab.com.
            dry_run: If True, log requests but don't execute.
        """
        if not token:
            _load_token_env()
        self.token = token or os.environ.get("GITLAB_TOKEN", "")
        self.base_url = (base_url or os.environ.get("GITLAB_URL", "https://gitlab.com")).rstrip("/")
        self.dry_run = dry_run
        if not self.token:
            raise ValueError("GITLAB_TOKEN not set")
        self.session = requests.Session()
        self.session.headers.update({
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        })
        self._scopes_validated = False
        self._cached_scopes = []

    def _request(self, method: str, endpoint: str, retries: int = 2, **kwargs) -> requests.Response:
        """Make API request with retry on 429/5xx."""
        url = f"{self.base_url}/api/v4{endpoint}"
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

    def _get_paginated(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        GET with automatic pagination. Follows X-Next-Page headers.

        Returns:
            Accumulated list of all result objects across all pages.
        """
        params = dict(params or {})
        params.setdefault("per_page", 100)
        all_results = []
        page = 1
        while True:
            params["page"] = page
            if self.dry_run:
                print(f"[DRY RUN] GET {endpoint} page={page}", file=sys.stderr)
                break
            resp = self._request("GET", endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return data
            all_results.extend(data)
            next_page = resp.headers.get("X-Next-Page", "")
            if not next_page:
                break
            page = int(next_page)
        return all_results

    def validate_token_scopes(self) -> List[str]:
        """
        GET /personal_access_tokens/self — validate token scopes.

        Returns:
            List of scope strings.

        Raises:
            PermissionError: If required scopes missing.
        """
        if self._scopes_validated:
            return self._cached_scopes
        resp = self._request("GET", "/personal_access_tokens/self")
        resp.raise_for_status()
        data = resp.json()
        scopes = data.get("scopes", [])
        required = {"read_api", "read_repository"}
        missing = required - set(scopes)
        if missing:
            raise PermissionError(f"Token missing required scopes: {missing}. Has: {scopes}")
        self._scopes_validated = True
        self._cached_scopes = scopes
        return scopes

    def fetch_mrs_by_authors(
        self,
        usernames: List[str],
        state: str = "opened",
        exclude_drafts: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetch merge requests authored by specified users.

        Args:
            usernames: List of GitLab usernames (with or without @).
            state: MR state filter (opened, merged, closed, all).
            exclude_drafts: If True, filter out draft MRs.

        Returns:
            List of MR dicts with full metadata.
        """
        all_mrs = []
        for user in usernames:
            user = user.lstrip("@")
            mrs = self._get_paginated("/merge_requests",
                                      params={"author_username": user, "state": state, "scope": "all", "per_page": 100})
            all_mrs.extend(mrs)
        if exclude_drafts:
            all_mrs = [mr for mr in all_mrs if not mr.get("draft") and not mr.get("work_in_progress")]
        return all_mrs

    def fetch_mr_by_url(self, url: str) -> Dict[str, Any]:
        """
        Fetch a single MR from its full GitLab URL.

        Parses the URL to extract namespace/project and MR IID,
        then fetches the MR with diff, comments, pipeline, and approvals.

        Args:
            url: Full GitLab MR URL.

        Returns:
            Enriched MR dict with metadata, diff, discussions, pipeline, approvals.

        Raises:
            ValueError: If URL format is invalid.
            requests.HTTPError: If MR not accessible.
        """
        project_path, iid = self.parse_mr_url(url)
        encoded = self.encode_project_path(project_path)
        resp = self._request("GET", f"/projects/{encoded}/merge_requests/{iid}")
        resp.raise_for_status()
        mr = resp.json()
        mr["diffs"] = self.fetch_mr_diffs(project_path, iid)
        mr["discussions"] = self.fetch_mr_comments(project_path, iid)
        mr["approvals"] = self.fetch_approvals(project_path, iid)
        return mr

    def fetch_mr_diffs(self, project_path: str, mr_iid: int) -> List[Dict[str, Any]]:
        """
        GET /projects/:id/merge_requests/:iid/diffs — paginated.

        Returns:
            List of diff file dicts.
        """
        encoded = self.encode_project_path(project_path)
        return self._get_paginated(f"/projects/{encoded}/merge_requests/{mr_iid}/diffs")

    def fetch_mr_comments(self, project_path: str, mr_iid: int) -> List[Dict[str, Any]]:
        """
        GET /projects/:id/merge_requests/:iid/discussions — paginated.

        Returns:
            List of discussion thread dicts.
        """
        encoded = self.encode_project_path(project_path)
        return self._get_paginated(f"/projects/{encoded}/merge_requests/{mr_iid}/discussions")

    def fetch_approvals(self, project_path: str, mr_iid: int) -> Dict[str, Any]:
        """
        GET /projects/:id/merge_requests/:iid/approvals.

        Returns:
            Approval data: required, left, approved_by, rules_left.
        """
        encoded = self.encode_project_path(project_path)
        resp = self._request("GET", f"/projects/{encoded}/merge_requests/{mr_iid}/approvals")
        resp.raise_for_status()
        return resp.json()

    def fetch_issue(self, project_path: str, issue_iid: int) -> Dict[str, Any]:
        """
        GET /projects/:id/issues/:iid — for linked/closing issues.

        Returns:
            Issue dict with title, description, labels, state.
        """
        encoded = self.encode_project_path(project_path)
        resp = self._request("GET", f"/projects/{encoded}/issues/{issue_iid}")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def parse_mr_url(url: str) -> Tuple[str, int]:
        """
        Parse a GitLab MR URL into (project_path, mr_iid).

        Supports:
            https://gitlab.com/namespace/project/-/merge_requests/42
            https://gitlab.com/group/subgroup/project/-/merge_requests/42

        Returns:
            Tuple of (project_path, mr_iid).

        Raises:
            ValueError: If URL format doesn't match expected pattern.
        """
        m = re.match(r'https?://[^/]+/(.+?)/-/merge_requests/(\d+)', url)
        if not m:
            raise ValueError(f"Invalid GitLab MR URL: {url}")
        return (m.group(1), int(m.group(2)))

    @staticmethod
    def encode_project_path(path: str) -> str:
        """URL-encode a project path for GitLab API."""
        return urllib.parse.quote(str(path), safe="")


def main():
    parser = argparse.ArgumentParser(description="GitLab API client for MR reviews")
    parser.add_argument("--dry-run", action="store_true", help="Log requests without executing")
    sub = parser.add_subparsers(dest="command", required=True)

    p_authors = sub.add_parser("mrs-by-authors", help="Fetch MRs by author list")
    p_authors.add_argument("usernames", nargs="+", help="GitLab usernames")
    p_authors.add_argument("--state", default="opened")
    p_authors.add_argument("--exclude-drafts", action="store_true")

    p_url = sub.add_parser("mr-by-url", help="Fetch single MR by URL")
    p_url.add_argument("url", help="Full GitLab MR URL")

    sub.add_parser("validate-scopes", help="Validate token scopes")

    args = parser.parse_args()
    client = GitLabClient(dry_run=args.dry_run)

    if args.command == "mrs-by-authors":
        result = client.fetch_mrs_by_authors(args.usernames, state=args.state, exclude_drafts=args.exclude_drafts)
    elif args.command == "mr-by-url":
        result = client.fetch_mr_by_url(args.url)
    elif args.command == "validate-scopes":
        result = client.validate_token_scopes()
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
