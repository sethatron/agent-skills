#!/usr/bin/env python3
"""
Jira issue export writer — generates md, json, or csv export files.

Accumulates all pages of results before writing (no partial exports).

Usage (CLI):
    python scripts/export_writer.py --jql "project = PROJ" --format md
    python scripts/export_writer.py --jql "assignee = me" --format csv --output /tmp/export.csv

Usage (module):
    from export_writer import write_export
    path = write_export(issues, format="md")
"""

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent

try:
    import yaml
    with open(SKILL_DIR / "config" / "jira.yaml") as f:
        _config = yaml.safe_load(f) or {}
except Exception:
    _config = {}

DEFAULT_EXPORT_PATH = os.path.expanduser(
    _config.get("export_default_path", "~/.zsh/jira/exports/")
)


def _extract_fields(issue):
    f = issue.get("fields", issue)
    def _get(obj, key):
        v = obj.get(key, "")
        return v.get("name", v) if isinstance(v, dict) else (v or "")
    assignee = f.get("assignee")
    if isinstance(assignee, dict):
        assignee_name = assignee.get("displayName", assignee.get("name", ""))
    else:
        assignee_name = assignee or ""
    return {
        "key": issue.get("key", f.get("key", "")),
        "summary": f.get("summary", ""),
        "status": _get(f, "status"),
        "type": _get(f, "issuetype"),
        "priority": _get(f, "priority"),
        "assignee": assignee_name,
        "updated": f.get("updated", ""),
    }


def write_export(
    issues: List[Dict[str, Any]],
    format: str = "md",
    output_path: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """
    Write issue data to an export file.

    All pages of results must be accumulated before calling this function.
    No partial exports are written.

    Args:
        issues: List of Jira issue dicts (full API response format).
        format: Output format — "md", "json", or "csv".
        output_path: Optional explicit output path. If None, uses
                     config.export_default_path with auto-generated filename.
        base_url: Jira base URL for generating hyperlinks in md format.

    Returns:
        Absolute path to the written export file.

    Raises:
        ValueError: If format is not one of md, json, csv.
        OSError: If output directory is not writable.
    """
    if format not in ("md", "json", "csv"):
        raise ValueError(f"Unsupported format: {format}. Use md, json, or csv.")
    if output_path:
        path = Path(output_path)
    else:
        path = Path(DEFAULT_EXPORT_PATH) / _generate_filename(format)
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "md":
        _write_markdown(issues, path, base_url or "")
    elif format == "json":
        _write_json(issues, path)
    elif format == "csv":
        _write_csv(issues, path)
    return str(path.resolve())


def _generate_filename(format: str) -> str:
    """Generate timestamped filename: jira_export_YYYYMMDD_HHMMSS.{ext}"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = format if format != "md" else "md"
    return f"jira_export_{ts}.{ext}"


def _write_markdown(issues: List[Dict], path: Path, base_url: str) -> None:
    """Write issues as a Markdown table with hyperlinked keys."""
    lines = ["---"]
    lines.append(f"exported_at: {datetime.now().isoformat()}")
    lines.append(f"count: {len(issues)}")
    lines.append("format: markdown")
    lines.append("---\n")
    lines.append("| Key | Summary | Status | Type | Priority | Assignee | Updated |")
    lines.append("|-----|---------|--------|------|----------|----------|---------|")
    for issue in issues:
        f = _extract_fields(issue)
        key = f["key"]
        if base_url:
            key = f'[{key}]({base_url.rstrip("/")}/browse/{key})'
        summary = f["summary"].replace("|", "\\|")[:80]
        lines.append(f'| {key} | {summary} | {f["status"]} | {f["type"]} | {f["priority"]} | {f["assignee"]} | {f["updated"]} |')
    path.write_text("\n".join(lines) + "\n")


def _write_json(issues: List[Dict], path: Path) -> None:
    """Write issues as pretty-printed JSON."""
    with open(path, "w") as f:
        json.dump(issues, f, indent=2)
        f.write("\n")


def _write_csv(issues: List[Dict], path: Path) -> None:
    """Write issues as CSV with header row."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Key", "Summary", "Status", "Type", "Priority", "Assignee", "Updated"])
        for issue in issues:
            flds = _extract_fields(issue)
            writer.writerow([flds["key"], flds["summary"], flds["status"],
                             flds["type"], flds["priority"], flds["assignee"], flds["updated"]])


def main():
    parser = argparse.ArgumentParser(description="Jira issue export writer")
    parser.add_argument("--format", choices=["md", "json", "csv"], default="md",
                        help="Export format (default: md)")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--input", help="Path to JSON file with issue data (for testing)")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            issues = json.load(f)
    else:
        issues = json.load(sys.stdin)

    path = write_export(issues, format=args.format, output_path=args.output)
    print(f"Exported {len(issues)} issues to: {path}")


if __name__ == "__main__":
    main()
