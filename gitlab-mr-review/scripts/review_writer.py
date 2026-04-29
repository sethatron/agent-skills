#!/usr/bin/env python3
"""
review.md generation and formatting.

Generates YAML frontmatter (stable API contract with dispatch skill)
and the full human-readable review body using Jinja2 templates.

FRONTMATTER STABILITY CONTRACT: The frontmatter schema is a versioned
API between gitlab-mr-review and dispatch. Field names, types, and
allowed values are immutable. Do not rename, retype, or remove fields.
New fields may only be appended at the end.

Usage (CLI):
    python scripts/review_writer.py --mr-data mr_data.json --output review.md

Usage (module):
    from review_writer import ReviewWriter
    writer = ReviewWriter()
    writer.write_review_md(mr_data, findings, output_path)
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates"

try:
    import yaml
except ImportError:
    yaml = None

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    Environment = None


FRONTMATTER_FIELDS = [
    "mr_id",
    "mr_iid",
    "mr_url",
    "project",
    "title",
    "author",
    "source_branch",
    "target_branch",
    "state",
    "pipeline_status",
    "pipeline_url",
    "has_conflicts",
    "approvals_required",
    "approvals_given",
    "approved_by",
    "verdict_critical",
    "verdict_major",
    "verdict_minor",
    "verdict_suggestion",
    "linked_issues",
    "review_timestamp",
    "review_path",
    "previous_review_path",
    "skill_version",
    "jira_key",
    "jira_url",
]


JIRA_TICKET_RE = re.compile(r'(?<![A-Z])([A-Z]{2,}-\d+)')


def extract_jira_key(title: str, source_branch: str) -> Optional[str]:
    m = JIRA_TICKET_RE.search(title)
    if m:
        return m.group(1)
    m = JIRA_TICKET_RE.search(source_branch)
    if m:
        return m.group(1)
    return None


class ReviewWriter:
    """Generates review.md with frontmatter and body."""

    def __init__(self, template_dir: Optional[Path] = None, skill_version: str = "2.0.0",
                 jira_base_url: Optional[str] = None):
        self.template_dir = template_dir or TEMPLATE_DIR
        self.skill_version = skill_version
        self.jira_base_url = jira_base_url

    def generate_frontmatter(self, mr_data: Dict[str, Any], findings: Dict[str, int],
                              review_path: str, previous_review_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Build the YAML frontmatter dict from MR data and findings.

        Args:
            mr_data: Enriched MR data from GitLab API.
            findings: Dict with keys: critical, major, minor, suggestion (counts).
            review_path: Absolute path where this review.md will be written.
            previous_review_path: Path to prior review.md for this branch, or None.

        Returns:
            OrderedDict matching the FRONTMATTER_FIELDS schema exactly.
        """
        project = mr_data.get("references", {}).get("full", "")
        if project and "!" in project:
            project = project.split("!")[0]
        if not project:
            m = re.search(r'https?://[^/]+/(.+?)/-/merge_requests/', mr_data.get("web_url", ""))
            project = m.group(1) if m else ""

        pipeline = mr_data.get("head_pipeline") or {}
        approvals = mr_data.get("approvals") or {}

        severity_counts = {"critical": 0, "major": 0, "minor": 0, "suggestion": 0}
        if isinstance(findings, dict):
            severity_counts.update(findings)
        elif isinstance(findings, list):
            for f in findings:
                sev = f.get("severity", "minor").lower()
                if sev in severity_counts:
                    severity_counts[sev] += 1

        linked = []
        desc = mr_data.get("description", "") or ""
        for m in re.finditer(r'(?:Closes|Fixes|Resolves)\s+#(\d+)', desc, re.IGNORECASE):
            linked.append(int(m.group(1)))

        state = "draft" if mr_data.get("draft") else mr_data.get("state", "opened")

        fm = OrderedDict()
        fm["mr_id"] = mr_data.get("id", 0)
        fm["mr_iid"] = mr_data.get("iid", 0)
        fm["mr_url"] = mr_data.get("web_url", "")
        fm["project"] = project
        fm["title"] = mr_data.get("title", "")
        fm["author"] = mr_data.get("author", {}).get("username", "")
        fm["source_branch"] = mr_data.get("source_branch", "")
        fm["target_branch"] = mr_data.get("target_branch", "")
        fm["state"] = state
        fm["pipeline_status"] = pipeline.get("status", "none")
        fm["pipeline_url"] = pipeline.get("web_url")
        fm["has_conflicts"] = mr_data.get("has_conflicts", False)
        fm["approvals_required"] = approvals.get("approvals_required", 0)
        fm["approvals_given"] = approvals.get("approvals_required", 0) - approvals.get("approvals_left", 0)
        fm["approved_by"] = [a.get("user", {}).get("username", "") for a in approvals.get("approved_by", [])]
        fm["verdict_critical"] = severity_counts["critical"]
        fm["verdict_major"] = severity_counts["major"]
        fm["verdict_minor"] = severity_counts["minor"]
        fm["verdict_suggestion"] = severity_counts["suggestion"]
        fm["linked_issues"] = linked
        fm["review_timestamp"] = datetime.now(timezone.utc).isoformat()
        fm["review_path"] = review_path
        fm["previous_review_path"] = previous_review_path
        fm["skill_version"] = self.skill_version
        jira_key = extract_jira_key(
            mr_data.get("title", ""),
            mr_data.get("source_branch", ""),
        )
        fm["jira_key"] = jira_key
        fm["jira_url"] = f"{self.jira_base_url}/browse/{jira_key}" if jira_key and self.jira_base_url else None
        return fm

    def generate_review_body(self, mr_data: Dict[str, Any], findings: List[Dict],
                              existing_comments: List[Dict],
                              previous_review: Optional[Dict] = None) -> str:
        """
        Render the human-readable review body via Jinja2 template.

        Sections: MR Summary, Pipeline Status, Merge Conflicts, Approval Status,
        Linked Issues, Diff Analysis, Existing Review Comments, Cross-Project Context,
        Summary of Recommended Changes, External References, Resolution Paths,
        Review Metadata, Review Delta.

        Args:
            mr_data: Enriched MR data.
            findings: List of finding dicts with severity, file, description, etc.
            existing_comments: Existing MR thread comments with skill assessment.
            previous_review: Parsed previous review.md for delta computation, or None.

        Returns:
            Rendered Markdown string.
        """
        if not Environment:
            raise ImportError("jinja2 required for review generation")
        env = Environment(loader=FileSystemLoader(str(self.template_dir)))
        template = env.get_template("review.md.j2")

        fm = self.generate_frontmatter(
            mr_data, findings, "",
            previous_review.get("previous_review_path") if previous_review else None,
        )

        pipeline = mr_data.get("head_pipeline") or {}
        approvals = mr_data.get("approvals") or {}

        ctx = {
            "frontmatter": fm,
            "mr": mr_data,
            "is_draft": mr_data.get("draft", False),
            "pipeline": {
                "exists": bool(pipeline),
                "status": pipeline.get("status", "none"),
                "web_url": pipeline.get("web_url", ""),
                "duration": pipeline.get("duration", ""),
                "finished_at": pipeline.get("finished_at", ""),
            },
            "has_conflicts": mr_data.get("has_conflicts", False),
            "approvals": {
                "required": approvals.get("approvals_required", 0),
                "given": approvals.get("approvals_required", 0) - approvals.get("approvals_left", 0),
                "approved_by_str": ", ".join(
                    a.get("user", {}).get("username", "")
                    for a in approvals.get("approved_by", [])),
                "pending_rules_str": ", ".join(
                    r.get("name", "")
                    for r in approvals.get("approval_rules_left", [])),
            },
            "linked_issues": [],
            "excluded_files": None,
            "diff_files": [],
            "existing_comments": existing_comments or [],
            "cross_project_refs": [],
            "all_findings": findings if isinstance(findings, list) else [],
            "external_references": [],
            "resolution_paths": [],
            "review_timestamp": fm["review_timestamp"],
            "cache_file_path": "",
            "cache_age": "",
            "jira_key": fm.get("jira_key"),
            "jira_url": fm.get("jira_url"),
            "skill_version": self.skill_version,
            "review_delta": previous_review,
            "cloned_repos": [],
        }
        return template.render(**ctx)

    def write_review_md(self, mr_data: Dict[str, Any], findings: List[Dict],
                         existing_comments: List[Dict], output_dir: str,
                         previous_review_path: Optional[str] = None) -> str:
        """
        Write complete review.md with frontmatter + body.

        Args:
            mr_data: Enriched MR data.
            findings: List of findings.
            existing_comments: Existing MR comments.
            output_dir: Directory to write review.md into.
            previous_review_path: Path to prior review for delta, or None.

        Returns:
            Absolute path to the written review.md.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        review_file = output_path / "review.md"

        previous_review = None
        if previous_review_path and Path(previous_review_path).exists():
            previous_review = {
                "previous_path": previous_review_path,
                "previous_timestamp": "",
                "new_count": 0,
                "resolved_count": 0,
                "remaining_count": len(findings) if isinstance(findings, list) else 0,
                "net_changes": {},
            }

        body = self.generate_review_body(mr_data, findings, existing_comments, previous_review)
        review_file.write_text(body)
        return str(review_file.resolve())

    def find_previous_review(self, branch_name: str, review_base: str) -> Optional[str]:
        """
        Search for the most recent prior review.md for this branch.

        Args:
            branch_name: Sanitized branch name.
            review_base: Base review output directory.

        Returns:
            Path to previous review.md, or None.
        """
        sanitized = self.sanitize_branch_name(branch_name)
        base = Path(os.path.expanduser(review_base))
        if not base.exists():
            return None
        for year_dir in sorted(base.iterdir(), reverse=True):
            if not year_dir.is_dir():
                continue
            for month_dir in sorted(year_dir.iterdir(), reverse=True):
                if not month_dir.is_dir():
                    continue
                for day_dir in sorted(month_dir.iterdir(), reverse=True):
                    review_path = day_dir / sanitized / "review.md"
                    if review_path.exists():
                        return str(review_path)
        return None

    @staticmethod
    def sanitize_branch_name(branch: str) -> str:
        """Sanitize branch name for filesystem: replace / with -, strip specials."""
        sanitized = branch.replace("/", "-")
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', sanitized)
        return sanitized.lower()


def main():
    parser = argparse.ArgumentParser(description="review.md generator")
    parser.add_argument("--mr-data", required=True, help="Path to enriched MR data JSON")
    parser.add_argument("--findings", help="Path to findings JSON")
    parser.add_argument("--output", required=True, help="Output directory for review.md")
    args = parser.parse_args()

    with open(args.mr_data) as f:
        mr_data = json.load(f)

    findings = []
    if args.findings:
        with open(args.findings) as f:
            findings = json.load(f)

    writer = ReviewWriter()
    path = writer.write_review_md(mr_data, findings, [], args.output)
    print(f"Review written to: {path}")


if __name__ == "__main__":
    main()
