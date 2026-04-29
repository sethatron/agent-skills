#!/usr/bin/env python3
"""
MR review orchestration runner.

Wires gitlab_client, cache_manager, and review_writer into an automated
pipeline that fetches MR data and generates summary artifacts for dispatch.

This script handles data fetching and summary generation. Deep code review
(finding analysis) remains Claude-driven via the /mr-review skill.

Usage:
    python scripts/mr_review_runner.py personal
    python scripts/mr_review_runner.py team
    python scripts/mr_review_runner.py url <gitlab-mr-url>
"""

import argparse
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

from scripts.gitlab_client import GitLabClient
from scripts.cache_manager import CacheManager
from scripts.review_writer import ReviewWriter, extract_jira_key

try:
    import yaml
except ImportError:
    yaml = None


def load_team_config() -> dict:
    config_path = SKILL_DIR / "config" / "team.yaml"
    if not config_path.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)
    if not yaml:
        import json as _json
        with open(config_path) as f:
            text = f.read()
        lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        roster = []
        in_roster = False
        for line in lines:
            if "team_roster:" in line:
                in_roster = True
                continue
            if in_roster and line.strip().startswith("- "):
                roster.append(line.strip().lstrip("- ").strip('"').strip("'"))
            elif in_roster and not line.startswith(" "):
                in_roster = False
        operator = ""
        for line in lines:
            if "username:" in line and "operator" not in line:
                operator = line.split(":", 1)[1].strip().strip('"').strip("'")
                break
        return {"operator": {"username": operator}, "team_roster": roster,
                "defaults": {"review_output_base": "~/.zsh/review", "skill_version": "2.0.0"}}
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_output_dir(config: dict, scope: str) -> Path:
    base = os.path.expanduser(config.get("defaults", {}).get("review_output_base", "~/.zsh/review"))
    today = datetime.now().strftime("%Y/%m/%d")
    out = Path(base) / today / scope
    out.mkdir(parents=True, exist_ok=True)
    return out


FINDINGS_FILENAME = "findings.json"


def _load_findings(mr_dir: Path) -> dict:
    fpath = mr_dir / FINDINGS_FILENAME
    if not fpath.exists():
        return {}
    try:
        with open(fpath) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _format_findings(findings_data: dict) -> list:
    lines = []
    findings = findings_data.get("findings", [])
    verdict = findings_data.get("verdict", "")
    verdict_summary = findings_data.get("verdict_summary", "")
    if not findings and not verdict:
        return lines

    lines.append("")
    lines.append("#### Review Findings")
    lines.append("")

    if findings:
        lines.append("| Severity | File | Finding |")
        lines.append("|----------|------|---------|")
        for f in findings:
            sev = f.get("severity", "info").upper()
            file_ref = f"`{f['file']}"
            if f.get("line"):
                file_ref += f":{f['line']}"
            file_ref += "`"
            desc = f.get("description", "")
            lines.append(f"| **{sev}** | {file_ref} | {desc} |")
        lines.append("")

    if verdict:
        lines.append(f"**Verdict:** {verdict}" + (f" — {verdict_summary}" if verdict_summary else ""))
        lines.append("")

    suggested = [f for f in findings if f.get("suggestion")]
    if suggested:
        lines.append("#### Suggested Changes")
        lines.append("")
        for f in suggested:
            file_ref = f['file']
            if f.get("line"):
                file_ref += f":{f['line']}"
            lines.append(f"##### `{file_ref}`")
            lines.append("```diff")
            lines.append(f["suggestion"].rstrip())
            lines.append("```")
            lines.append("")

    return lines


def _count_diff_lines(diff_text: str) -> tuple:
    added = sum(1 for l in diff_text.split('\n') if l.startswith('+') and not l.startswith('+++'))
    removed = sum(1 for l in diff_text.split('\n') if l.startswith('-') and not l.startswith('---'))
    return added, removed


def _format_mr_metadata(mr_data: dict, fm: dict) -> list:
    lines = []
    pipeline = mr_data.get("head_pipeline") or {}
    approvals = mr_data.get("approvals") or {}
    discussions = mr_data.get("discussions") or []
    diffs = mr_data.get("diffs") or []

    human_threads = [d for d in discussions
                     if any(not n.get("system", False) for n in d.get("notes", []))]
    unresolved = [d for d in human_threads
                  if d.get("notes", [{}])[0].get("resolvable", False)
                  and not d.get("notes", [{}])[0].get("resolved", False)]

    iid = mr_data.get("iid", 0)
    title = mr_data.get('title', '')
    jira_key = fm.get('jira_key')
    jira_url = fm.get('jira_url')
    if jira_key and jira_url:
        display_title = title.replace(jira_key, f"[{jira_key}]({jira_url})")
    else:
        display_title = title

    lines.append(f"**MR:** [{fm.get('project', '')}!{iid}]({mr_data.get('web_url', '')})")
    if jira_key and jira_url:
        lines.append(f"**Jira:** [{jira_key}]({jira_url})")
    lines.append(f"**Author:** {fm.get('author', '')} | "
                 f"**Branch:** `{mr_data.get('source_branch', '')}` → `{mr_data.get('target_branch', '')}` | "
                 f"**Pipeline:** {pipeline.get('status', 'none')}")

    approvals_req = approvals.get("approvals_required", 0)
    approvals_left = approvals.get("approvals_left", 0)
    approvals_given = approvals_req - approvals_left
    approved_by = [a.get("user", {}).get("username", "") for a in approvals.get("approved_by", [])]
    appr_str = f"{approvals_given}/{approvals_req}"
    if approved_by:
        appr_str += f" ({', '.join(approved_by)})"
    conflict_str = "Yes" if mr_data.get("has_conflicts") else "No"
    lines.append(f"**Approvals:** {appr_str} | **Conflicts:** {conflict_str} | "
                 f"**Discussions:** {len(human_threads)} ({len(unresolved)} unresolved)")
    return lines, display_title, diffs


def _format_diff_sections(diffs: list) -> list:
    lines = []
    if not diffs:
        return lines
    lines.append("")
    lines.append("#### Changed Files")
    lines.append("")
    lines.append("| File | Changes |")
    lines.append("|------|---------|")
    for d in diffs:
        path = d.get("new_path") or d.get("old_path", "")
        diff_text = d.get("diff", "")
        added, removed = _count_diff_lines(diff_text)
        tag = ""
        if d.get("new_file"):
            tag = " (new)"
        elif d.get("deleted_file"):
            tag = " (deleted)"
        elif d.get("renamed_file"):
            tag = f" (renamed from `{d.get('old_path', '')}`)"
        lines.append(f"| `{path}`{tag} | +{added}/-{removed} |")

    lines.append("")
    lines.append("#### Diff")
    for d in diffs:
        path = d.get("new_path") or d.get("old_path", "")
        diff_text = d.get("diff", "")
        if not diff_text:
            continue
        lines.append("")
        lines.append(f"##### `{path}`")
        lines.append("```diff")
        lines.append(diff_text.rstrip())
        lines.append("```")
    return lines


def write_mr_review(writer: ReviewWriter, mr_data: dict, output_dir: Path) -> Path:
    iid = mr_data.get("iid", 0)
    mr_dir = output_dir / f"mr_{iid}"
    mr_dir.mkdir(parents=True, exist_ok=True)
    review_path = str(mr_dir / "review.md")

    fm = writer.generate_frontmatter(
        mr_data,
        {"critical": None, "major": None, "minor": None, "suggestion": None},
        review_path,
    )

    lines = ["---"]
    for k, v in fm.items():
        if v is None:
            lines.append(f"{k}: null")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
        elif isinstance(v, int):
            lines.append(f"{k}: {v}")
        else:
            val = str(v).replace('"', '\\"')
            lines.append(f'{k}: "{val}"')
    lines.append("---")
    lines.append("")

    meta_lines, display_title, diffs = _format_mr_metadata(mr_data, fm)

    lines.append(f"# MR Summary: {display_title}")
    lines.append("")
    lines.extend(meta_lines)
    lines.extend(_format_findings(_load_findings(mr_dir)))
    lines.extend(_format_diff_sections(diffs))

    review_file = mr_dir / "review.md"
    review_file.write_text("\n".join(lines) + "\n")
    return review_file


def _linkify_title(title_raw: str, branch: str, jira_base_url: str) -> str:
    jk = extract_jira_key(title_raw, branch)
    if jk and jira_base_url:
        return title_raw.replace(jk, f"[{jk}]({jira_base_url}/browse/{jk})")
    return title_raw


def write_index(mrs: list, output_dir: Path, scope: str, jira_base_url: str = "") -> Path:
    lines = [f"# MR Queue: {scope} — {datetime.now().strftime('%Y-%m-%d')}"]
    lines.append("")

    ready = sorted(
        [m for m in mrs if not m.get("draft")],
        key=lambda x: x.get("updated_at", ""), reverse=True,
    )
    drafts = sorted(
        [m for m in mrs if m.get("draft")],
        key=lambda x: x.get("updated_at", ""), reverse=True,
    )

    lines.append(f"**Total:** {len(mrs)} MRs ({len(ready)} ready, {len(drafts)} drafts)")
    lines.append("")

    if ready:
        lines.append("## Summary")
        lines.append("")
        lines.append("| MR | Repo | Author | Title | Target | Pipeline | Approvals | Findings |")
        lines.append("|----|------|--------|-------|--------|----------|-----------|----------|")
        for mr in ready:
            iid = mr.get("iid", 0)
            web_url = mr.get("web_url", "")
            author = mr.get("author", {}).get("username", "")
            project = mr.get("references", {}).get("full", "").split("!")[0]
            repo_short = project.rsplit("/", 1)[-1] if project else ""
            title_raw = mr.get("title", "")
            title = _linkify_title(title_raw[:50], mr.get("source_branch", ""), jira_base_url)
            target = mr.get("target_branch", "")
            pipeline = (mr.get("head_pipeline") or {}).get("status", "none")
            approvals = mr.get("approvals") or {}
            req = approvals.get("approvals_required", 0)
            left = approvals.get("approvals_left", 0)
            appr = f"{req - left}/{req}"
            mr_dir = output_dir / f"mr_{iid}"
            fd = _load_findings(mr_dir)
            findings_summary = ""
            if fd.get("findings"):
                by_sev = {}
                for f in fd["findings"]:
                    s = f.get("severity", "info").upper()
                    by_sev[s] = by_sev.get(s, 0) + 1
                parts = []
                for s in ["CRITICAL", "MAJOR", "MINOR", "SUGGESTION"]:
                    if by_sev.get(s):
                        parts.append(f"{by_sev[s]}{s[0]}")
                findings_summary = " ".join(parts)
                if fd.get("verdict"):
                    findings_summary += f" · {fd['verdict']}"
            elif fd.get("verdict"):
                findings_summary = fd["verdict"]
            lines.append(f"| [!{iid}]({web_url}) | {repo_short} | {author} | {title} | {target} | {pipeline} | {appr} | {findings_summary} |")
        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## Detailed Reviews")

        for mr in ready:
            iid = mr.get("iid", 0)
            web_url = mr.get("web_url", "")
            title_raw = mr.get("title", "")
            branch = mr.get("source_branch", "")
            display_title = _linkify_title(title_raw, branch, jira_base_url)

            fm_stub = {
                "project": mr.get("references", {}).get("full", "").split("!")[0],
                "author": mr.get("author", {}).get("username", ""),
                "jira_key": extract_jira_key(title_raw, branch),
            }
            jk = fm_stub["jira_key"]
            jira_url = f"{jira_base_url}/browse/{jk}" if jk and jira_base_url else ""
            fm_stub["jira_url"] = jira_url

            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append(f"### [{fm_stub['project']}!{iid}]({web_url}): {display_title}")
            lines.append("")

            meta_lines, _, diffs = _format_mr_metadata(mr, fm_stub)
            lines.extend(meta_lines)
            mr_dir = output_dir / f"mr_{iid}"
            lines.extend(_format_findings(_load_findings(mr_dir)))
            lines.extend(_format_diff_sections(diffs))
            lines.append("")

    if drafts:
        lines.append("---")
        lines.append("")
        lines.append("## Drafts")
        lines.append("")
        for mr in drafts:
            iid = mr.get("iid", 0)
            web_url = mr.get("web_url", "")
            author = mr.get("author", {}).get("username", "")
            title = _linkify_title(mr.get("title", "")[:60], mr.get("source_branch", ""), jira_base_url)
            conflicts = " **CONFLICTS**" if mr.get("has_conflicts") else ""
            lines.append(f"- [!{iid}]({web_url}) ({author}) {title}{conflicts}")
        lines.append("")

    lines.append(f"*Generated at {datetime.now(timezone.utc).isoformat()} by mr_review_runner.py*")

    index_path = output_dir / "README.md"
    index_path.write_text("\n".join(lines) + "\n")
    return index_path


def enrich_mr(client: GitLabClient, mr: dict) -> dict:
    project_path = mr.get("references", {}).get("full", "").split("!")[0]
    if not project_path:
        return mr
    iid = mr.get("iid")
    try:
        encoded = client.encode_project_path(project_path)
        resp = client._request("GET", f"/projects/{encoded}/merge_requests/{iid}")
        if resp.ok:
            detail = resp.json()
            mr["head_pipeline"] = detail.get("head_pipeline")
            mr["detailed_merge_status"] = detail.get("detailed_merge_status")
    except Exception:
        pass
    try:
        mr["diffs"] = client.fetch_mr_diffs(project_path, iid)
    except Exception:
        mr["diffs"] = []
    try:
        mr["discussions"] = client.fetch_mr_comments(project_path, iid)
    except Exception:
        mr["discussions"] = []
    try:
        mr["approvals"] = client.fetch_approvals(project_path, iid)
    except Exception:
        mr["approvals"] = {}
    return mr


def run_scope(scope: str, usernames: list, output_dir_override: str = None):
    config = load_team_config()
    client = GitLabClient()
    cache = CacheManager(
        stale_hours=config.get("defaults", {}).get("cache_stale_hours", 6),
        retain_days=config.get("defaults", {}).get("cache_retain_days", 30),
    )
    jira_base_url = config.get("defaults", {}).get("jira_base_url", "")
    writer = ReviewWriter(
        skill_version=config.get("defaults", {}).get("skill_version", "2.0.0"),
        jira_base_url=jira_base_url,
    )

    if output_dir_override:
        output_dir = Path(output_dir_override)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = get_output_dir(config, scope)

    print(f"Fetching {scope} MRs for: {', '.join(usernames)}", file=sys.stderr)
    mrs = client.fetch_mrs_by_authors(usernames)
    print(f"Found {len(mrs)} MRs", file=sys.stderr)

    cache.write_cache(scope, mrs)

    enriched = []
    for i, mr in enumerate(mrs):
        iid = mr.get("iid", "?")
        print(f"  Enriching !{iid} ({i+1}/{len(mrs)})...", file=sys.stderr)
        enriched.append(enrich_mr(client, mr))

    for mr in enriched:
        write_mr_review(writer, mr, output_dir)

    index_path = write_index(enriched, output_dir, scope, jira_base_url=jira_base_url)

    print(f"\nOutput: {output_dir}", file=sys.stderr)
    print(f"Index:  {index_path}", file=sys.stderr)
    print(f"MRs:    {len(enriched)} review.md files", file=sys.stderr)

    print(json.dumps({
        "scope": scope,
        "output_dir": str(output_dir),
        "index": str(index_path),
        "mr_count": len(enriched),
        "ready": len([m for m in enriched if not m.get("draft")]),
        "drafts": len([m for m in enriched if m.get("draft")]),
    }))


def run_url(url: str, output_dir_override: str = None):
    config = load_team_config()
    client = GitLabClient()
    writer = ReviewWriter(
        skill_version=config.get("defaults", {}).get("skill_version", "2.0.0"),
        jira_base_url=config.get("defaults", {}).get("jira_base_url", ""),
    )

    if output_dir_override:
        output_dir = Path(output_dir_override)
    else:
        output_dir = get_output_dir(config, "direct")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching MR: {url}", file=sys.stderr)
    mr = client.fetch_mr_by_url(url)
    review_path = write_mr_review(writer, mr, output_dir)
    print(f"Output: {review_path}", file=sys.stderr)
    print(json.dumps({"url": url, "review_path": str(review_path)}))


def run_rebuild_index(review_dir: str):
    review_path = Path(review_dir)
    if not review_path.exists():
        print(f"Error: {review_path} does not exist", file=sys.stderr)
        sys.exit(1)

    config = load_team_config()
    jira_base_url = config.get("defaults", {}).get("jira_base_url", "")
    cache = CacheManager(
        stale_hours=config.get("defaults", {}).get("cache_stale_hours", 6),
        retain_days=config.get("defaults", {}).get("cache_retain_days", 30),
    )

    scope = review_path.name
    cache_data = cache.read_cache(scope)
    if not cache_data:
        print(f"Error: no cached MR data for scope '{scope}'", file=sys.stderr)
        sys.exit(1)

    if not isinstance(cache_data, list):
        cache_data = cache_data.get("mrs", cache_data)

    index_path = write_index(cache_data, review_path, scope, jira_base_url=jira_base_url)
    print(f"Rebuilt: {index_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="MR review orchestration runner")
    parser.add_argument("--output-dir", help="Override output directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("personal", help="Fetch and summarize operator's open MRs")
    sub.add_parser("team", help="Fetch and summarize team's open MRs")

    p_url = sub.add_parser("url", help="Fetch and summarize a single MR by URL")
    p_url.add_argument("mr_url", help="GitLab MR URL")

    p_rebuild = sub.add_parser("rebuild-index", help="Rebuild README.md from cached data + findings")
    p_rebuild.add_argument("review_dir", help="Path to review output directory")

    args = parser.parse_args()

    config = load_team_config()

    if args.command == "personal":
        operator = config.get("operator", {}).get("username", "").lstrip("@")
        if not operator:
            print("Error: No operator username in team.yaml", file=sys.stderr)
            sys.exit(1)
        run_scope("personal", [operator], args.output_dir)

    elif args.command == "team":
        roster = config.get("team_roster", [])
        if not roster:
            print("Error: Empty team_roster in team.yaml", file=sys.stderr)
            sys.exit(1)
        run_scope("team", roster, args.output_dir)

    elif args.command == "url":
        run_url(args.mr_url, args.output_dir)

    elif args.command == "rebuild-index":
        run_rebuild_index(args.review_dir)


if __name__ == "__main__":
    main()
