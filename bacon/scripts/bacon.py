#!/usr/bin/env python3

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from git_ops import (
    ensure_repo, fetch_all, reset_to_master, checkout_branch,
    extract_tickets_for_project, next_tag, branch_exists,
    create_branch_from, commit_and_push, cherry_pick as git_cherry_pick,
    repo_path, run, get_log_between, extract_ticket_ids, get_master_log,
    copy_branch,
)
from gitlab_client import GitLabClient, load_from_env as load_gitlab
from jira_client import (
    JiraClient, load_from_env as load_jira,
    build_cmd_description, build_adf_text, build_adf_link,
    build_adf_paragraph, build_adf_table, build_adf_bullet_list,
    browse_url, portal_url,
)
from merge_conflict_check import check_conflicts, format_report, ProjectConflictReport

RELEASE_BASE = os.path.expanduser("~/.release")
GIT_BASE = os.path.expanduser("~/.release/git")

MANIFEST_ANCHORS = {
    "ng-infrastructure": "ng-infrastructure-version",
    "ng-air-continuous-deployment": "ng-air-continuous-deployment-version",
    "ng-governance-infrastructure": "ng-governance-infrastructure-version",
    "onyx-infrastructure": "onyx-infrastructure-version",
    "onyx-helmsman": "onyx-helmsman-version",
    "mdp-gateway": "mdp-gateway-version",
    "ng-abacus-inbound-infra": "ng-abacus-inbound-infra-version",
    "ng-orchestration-service": "ng-orchestration-service-version",
    "ng-monitoring-utils": "ng-monitoring-utils-version",
    "ng-airbyte-services": "ng-airbyte-services-version",
    "ng-data-copier": "ng-data-copier-version",
    "ng-landing-decrypt": "ng-landing-decrypt-version",
    "ng-landing-decrypt-service": "ng-landing-decrypt-service-version",
    "ng-databricks-outbound-infra": "ng-databricks-outbound-infra-version",
    "ng-manifest-file-processor": "ng-manifest-file-processor-version",
    "ng-nasco-event-api": "ng-nasco-event-api-version",
    "ng-point-click-api": "ng-point-click-api-version",
    "ng-prime-api": "ng-prime-api-version",
    "asg-updater": "asg-updater-version",
    "ng-data-ingestion-api": "ng-data-ingestion-api-version",
    "auth0-idm": "auth0-idm-version",
    "auth0-infrastructure": "auth0-infrastructure-version",
}

AIR_PROJECTS = {"ng-abacus-insights-runtime"}
ONYX_PROJECTS = {"ng-onyx-runtime"}
RUNTIME_PROJECTS = AIR_PROJECTS | ONYX_PROJECTS

EXCLUDED_TENANTS = {"abacus-config.yaml", "abacusqa-config.yaml", "qawest-config.yaml", "alexwest-config.yaml"}


def dryrun_branch(branch: str, dry_run_level: Optional[int]) -> str:
    if dry_run_level == 1 and branch.startswith("release-"):
        return branch.replace("release-", "dryrun-", 1)
    return branch


def parse_input(text: str) -> Dict:
    dry_run_match = re.search(r'dry[\s-]?run(?:\s*\((\d+)\))?', text, re.IGNORECASE)
    dry_run_level = int(dry_run_match.group(1) or 0) if dry_run_match else None
    if dry_run_match:
        text = text[:dry_run_match.start()] + text[dry_run_match.end():]

    projects = []
    pattern = r'(\S+?)(?::)?\s*Branch:\s*(release-[\d.]+)\s*Tag:\s*(\S+)'
    for m in re.finditer(pattern, text):
        name = m.group(1).strip().rstrip(":")
        branch = m.group(2).strip()
        tag = m.group(3).strip()
        version_from_branch = branch.replace("release-", "")
        projects.append({
            "name": name,
            "branch": branch,
            "tag": tag,
            "branch_version": version_from_branch,
        })

    version_match = re.search(r'(?:^|\n)\s*Version:\s*([\d.]+)', text)
    version = version_match.group(1).strip() if version_match else ""

    ngqa_match = re.search(r'(NGQA-\d+)', text)
    ngqa_ticket = ngqa_match.group(1) if ngqa_match else ""

    adhoc_tickets = []
    adhoc_patterns = [
        r'(?:also include|include|add)\s+((?:[A-Z]{2,}-\d+[\s,and]*)+)',
        r'(?:Also include|Include|Add)\s+((?:[A-Z]{2,}-\d+[\s,and]*)+)',
    ]
    for pat in adhoc_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            adhoc_tickets.extend(re.findall(r'[A-Z]{2,}-\d+', m.group(1)))

    globals_files = []
    globals_pattern = r'(\S+/globals\.tf)'
    for m in re.finditer(globals_pattern, text):
        globals_files.append(m.group(1))

    build_directives = []
    build_pattern = r'Build\s+(AIR[:\s]*[\d.]+|.*?ng-onyx-runtime.*?)(?:\n|$)'
    for m in re.finditer(build_pattern, text, re.IGNORECASE):
        build_directives.append(m.group(1).strip())

    onyx_from_to = []
    onyx_pattern = r'from:\s*(.+?)\s*\n\s*to:\s*(.+?)(?:\n|$)'
    for m in re.finditer(onyx_pattern, text):
        onyx_from_to.append({"from": m.group(1).strip().strip('"'), "to": m.group(2).strip().strip('"')})

    result = {
        "projects": projects,
        "version": version,
        "ngqa_ticket": ngqa_ticket,
        "adhoc_tickets": list(set(adhoc_tickets)),
        "globals_files": globals_files,
        "build_directives": build_directives,
        "onyx_from_to": onyx_from_to,
        "raw": text,
    }
    if dry_run_level is not None:
        result["dry_run_level"] = dry_run_level
    return result


def classify(parsed: Dict) -> str:
    names = {p["name"] for p in parsed["projects"]}
    has_air = bool(names & AIR_PROJECTS)
    has_onyx = bool(names & ONYX_PROJECTS)
    has_platform = bool(names - RUNTIME_PROJECTS)

    if has_air and has_onyx and not has_platform:
        return "AIR_ONYX"
    if has_air and not has_onyx and not has_platform:
        return "AIR_ONLY"
    if has_onyx and not has_air and not has_platform:
        return "ONYX_ONLY"
    if not has_air and not has_onyx:
        return "PLATFORM"
    return "COMPOUND"


def cmd_summary(release_type: str, version: str, projects: List[Dict]) -> str:
    air_ver = None
    onyx_ver = None
    for p in projects:
        if p["name"] == "ng-abacus-insights-runtime":
            air_ver = p.get("next_tag", p.get("branch_version", version))
        elif p["name"] == "ng-onyx-runtime":
            onyx_ver = p.get("next_tag", p.get("branch_version", version))

    if release_type == "AIR_ONLY":
        return f"AIR {air_ver or version} Release"
    elif release_type == "ONYX_ONLY":
        return f"ONYX {onyx_ver or version} Release"
    elif release_type == "AIR_ONYX":
        parts = []
        if air_ver:
            parts.append(f"AIR {air_ver}")
        if onyx_ver:
            parts.append(f"ONYX {onyx_ver}")
        return f"{' / '.join(parts)} Release" if parts else f"AIR/ONYX {version} Release"
    else:
        return f"NextGen {version} Release"


def do_parse(args):
    text = sys.stdin.read() if args.input == "-" else args.input
    result = parse_input(text)
    result["release_type"] = classify(result)
    print(json.dumps(result, indent=2))


def do_classify(args):
    parsed = json.loads(sys.stdin.read())
    print(classify(parsed))


def do_fetch_repos(args):
    parsed = json.loads(sys.stdin.read())
    results = {}
    for p in parsed["projects"]:
        name = p["name"]
        try:
            path = reset_to_master(name)
            if not branch_exists(name, p["branch"]):
                results[name] = {"ok": False, "error": f"Branch {p['branch']} not found"}
            else:
                results[name] = {"ok": True, "path": path}
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    try:
        reset_to_master("ng-deployment-config-files")
        results["ng-deployment-config-files"] = {"ok": True}
    except Exception as e:
        results["ng-deployment-config-files"] = {"ok": False, "error": str(e)}

    print(json.dumps(results, indent=2))


def do_extract_tickets(args):
    project = args.project
    branch = args.branch
    try:
        tickets = extract_tickets_for_project(project, branch)
        print(json.dumps({"project": project, "tickets": sorted(tickets)}))
    except Exception as e:
        print(json.dumps({"project": project, "tickets": [], "error": str(e)}), file=sys.stderr)
        sys.exit(1)


def do_next_tag(args):
    tag = next_tag(args.project)
    print(json.dumps({"project": args.project, "next_tag": tag}))


def do_check_conflicts(args):
    parsed = json.loads(sys.stdin.read())
    reports = []
    for p in parsed["projects"]:
        report = check_conflicts(p["name"], p["branch"])
        reports.append({
            "project": report.project,
            "branch": report.release_branch,
            "clean": report.clean,
            "has_complex": report.has_complex,
            "conflicts": [
                {
                    "file": c.file,
                    "simple": c.simple,
                    "description": c.description,
                    "cause_commits": c.cause_commits,
                    "mr_refs": c.mr_refs,
                }
                for c in report.conflicts
            ],
        })
    print(json.dumps(reports, indent=2))


def do_create_cmd(args):
    data = json.loads(sys.stdin.read())

    projects = data.get("projects", [])
    tickets = data.get("tickets", [])
    version = data.get("version", "")
    release_type = data.get("release_type", "PLATFORM")
    ngqa_ticket = data.get("ngqa_ticket", "")

    summary = cmd_summary(release_type, version, projects)
    ticket_refs = ", ".join(t["id"] for t in tickets)
    test_plan = f"Regression testing captured in {ngqa_ticket}" if ngqa_ticket else "Regression testing completed."

    if args.dry_run_level is not None:
        issue_key = "CMD-0000"
        print(json.dumps({
            "key": issue_key,
            "browse_url": browse_url(issue_key),
            "portal_url": portal_url(issue_key),
            "summary": summary,
            "dry_run": True,
        }))
        return

    description_adf = build_cmd_description(version, release_type, projects, tickets)
    jira = load_jira()
    result = jira.create_cmd_ticket(
        summary=summary,
        description_adf=description_adf,
        ticket_refs=ticket_refs,
        test_plan=test_plan,
    )
    issue_key = result.get("issueKey", "")
    print(json.dumps({
        "key": issue_key,
        "browse_url": jira.browse_url(issue_key),
        "portal_url": jira.portal_url(issue_key),
        "summary": summary,
    }))


def do_create_mr(args):
    gl = load_gitlab()
    data = json.loads(sys.stdin.read())

    project = data["project"]
    source = data["source_branch"]
    target = data.get("target_branch", "master")
    title = data["title"]
    description = data.get("description", "")
    merge_on_success = data.get("merge_when_pipeline_succeeds", False)
    draft = data.get("draft", False)

    if args.dry_run_level == 1:
        draft = True
        title = f"[DRY-RUN] {title}"
        description = f"> This is a dry-run MR for testing purposes. Do not merge.\n\n{description}"

    result = gl.create_mr(
        project_name=project,
        source_branch=source,
        target_branch=target,
        title=title,
        description=description,
        merge_when_pipeline_succeeds=merge_on_success,
        draft=draft,
    )
    iid = result.get("iid", "")
    print(json.dumps({
        "project": project,
        "iid": iid,
        "web_url": result.get("web_url", gl.mr_web_url(project, iid)),
        "state": result.get("state", ""),
    }))


def do_update_manifest(args):
    data = json.loads(sys.stdin.read())
    version = data["version"]
    cmd_key = data["cmd_key"]
    updates = data["updates"]

    config_project = "ng-deployment-config-files"
    path = reset_to_master(config_project)

    branch = dryrun_branch(f"release-{version}", args.dry_run_level)
    create_branch_from(config_project, "master", branch)

    manifest_path = os.path.join(path, "manifests", "default-manifest.yaml")
    with open(manifest_path) as f:
        content = f.read()

    for project_name, new_version in updates.items():
        anchor = MANIFEST_ANCHORS.get(project_name)
        if not anchor:
            print(f"WARNING: No manifest anchor for {project_name}", file=sys.stderr)
            continue
        pattern = rf'({re.escape(anchor)}:\s*&{re.escape(anchor)}\s*")([^"]*?)(")'
        new_content = re.sub(pattern, rf'\g<1>{new_version}\3', content)
        if new_content == content:
            print(f"WARNING: Anchor {anchor} not found or already set to {new_version}", file=sys.stderr)
        content = new_content

    with open(manifest_path, "w") as f:
        f.write(content)

    commit_and_push(
        config_project, branch,
        f"[{cmd_key}] NextGen {version} Release",
        files=["manifests/default-manifest.yaml"],
    )
    print(json.dumps({"branch": branch, "path": manifest_path, "updates": updates}))


def do_detect_variance(args):
    config_project = "ng-deployment-config-files"
    path = fetch_all(config_project)

    diff_output = run(
        "git diff origin/master..origin/qa -- tenant-specific-overrides/",
        cwd=path, check=False,
    )

    changed_files = []
    for line in diff_output.splitlines():
        if line.startswith("diff --git"):
            match = re.search(r'b/(tenant-specific-overrides/\S+)', line)
            if match:
                filepath = match.group(1)
                filename = os.path.basename(filepath)
                if filename not in EXCLUDED_TENANTS:
                    changed_files.append(filepath)

    if not changed_files:
        print(json.dumps({"variance": False, "message": "No config variance detected."}))
        return

    variances = []
    for fp in changed_files:
        merge_log = run(
            f"git log origin/master..origin/qa -- {fp} --merges --oneline",
            cwd=path, check=False,
        )
        mr_refs = re.findall(r'See merge request.*!(\d+)', merge_log)
        ticket_refs = re.findall(r'([A-Z]{2,}-\d+)', merge_log)
        variances.append({
            "file": fp,
            "mr_refs": mr_refs,
            "ticket_refs": ticket_refs,
            "merge_log": merge_log,
        })

    print(json.dumps({"variance": True, "files": variances}, indent=2))


def do_verify_mr_merged(args):
    if args.dry_run_level == 1:
        print(json.dumps({
            "project": args.project, "iid": args.iid,
            "merged": True, "merge_commit_sha": "dryrun-simulated",
        }))
        return

    gl = load_gitlab()
    merged = gl.is_mr_merged(args.project, args.iid)
    sha = None
    if merged:
        sha = gl.get_merge_commit_sha(args.project, args.iid)
    print(json.dumps({"project": args.project, "iid": args.iid, "merged": merged, "merge_commit_sha": sha}))


def do_update_globals(args):
    data = json.loads(sys.stdin.read())
    project = data["project"]
    branch = data["branch"]
    files = data["files"]
    air_version = data.get("air_version")
    onyx_version = data.get("onyx_version")
    from_to = data.get("from_to", [])

    path = repo_path(project)

    for filepath in files:
        full_path = os.path.join(path, filepath)
        if not os.path.exists(full_path):
            print(f"WARNING: {full_path} not found", file=sys.stderr)
            continue

        with open(full_path) as f:
            content = f.read()

        original = content

        if from_to:
            for ft in from_to:
                content = content.replace(ft["from"], ft["to"])
        else:
            if air_version:
                content = re.sub(r'AIR:[\d.]+', f'AIR:{air_version}', content)
            if onyx_version:
                content = re.sub(r'ONYX:[\d.]+', f'ONYX:{onyx_version}', content)

        if content != original:
            with open(full_path, "w") as f:
                f.write(content)
            run(f"git add {filepath}", cwd=path)

    run(f'git commit -m "[{branch}] Update AIR/ONYX policy version"', cwd=path)
    run(f"git push -u origin {branch}", cwd=path)
    print(json.dumps({"project": project, "branch": branch, "files": files, "ok": True}))


def do_cherry_pick(args):
    data = json.loads(sys.stdin.read())
    project = data["project"]
    branch = data["branch"]
    sha = data["merge_commit_sha"]

    try:
        git_cherry_pick(project, branch, sha)
        print(json.dumps({"project": project, "branch": branch, "ok": True}))
    except RuntimeError as e:
        print(json.dumps({"project": project, "branch": branch, "ok": False, "error": str(e)}))
        sys.exit(1)


def do_save_artifacts(args):
    data = json.loads(sys.stdin.read())
    version = data["version"]
    suffix = "-dryrun" if args.dry_run_level is not None else ""
    release_dir = os.path.join(RELEASE_BASE, f"{version}{suffix}")
    os.makedirs(release_dir, exist_ok=True)

    for filename, content in data.get("files", {}).items():
        filepath = os.path.join(release_dir, filename)
        with open(filepath, "w") as f:
            if isinstance(content, (dict, list)):
                json.dump(content, f, indent=2)
            else:
                f.write(str(content))

    print(json.dumps({"release_dir": release_dir, "saved": list(data.get("files", {}).keys())}))


def do_search_breaking(args):
    gl = load_gitlab()
    result = gl.search_breaking_mrs(args.ticket)
    print(json.dumps({"ticket": args.ticket, "breaking": result}))


def do_get_summary(args):
    jira = load_jira()
    summary = jira.get_issue_summary(args.ticket)
    print(json.dumps({"ticket": args.ticket, "summary": summary}))


def do_enrich_tickets(args):
    jira = load_jira()
    gl = load_gitlab()
    data = json.loads(sys.stdin.read())
    tickets = data.get("tickets", [])
    project = data.get("project", "unknown")

    enriched = []
    for tid in tickets:
        summary = jira.get_issue_summary(tid)
        breaking = gl.search_breaking_mrs(tid)
        enriched.append({
            "id": tid,
            "summary": summary,
            "breaking": breaking,
            "project": project,
        })
    print(json.dumps(enriched, indent=2))


def do_preview(args):
    parsed = json.loads(sys.stdin.read())
    projects = parsed.get("projects", [])
    version = parsed.get("version", "")
    ngqa_ticket = parsed.get("ngqa_ticket", "")
    release_type = parsed.get("release_type", classify(parsed))

    jira = load_jira()
    gl = load_gitlab()

    output = {
        "dry_run_level": 0,
        "release": {
            "version": version,
            "type": release_type,
            "ngqa_ticket": ngqa_ticket,
        },
        "stages": {},
    }
    stages = output["stages"]

    fetch_results = {}
    for p in projects:
        name = p["name"]
        try:
            reset_to_master(name)
            if branch_exists(name, p["branch"]):
                fetch_results[name] = "ok"
            else:
                fetch_results[name] = f"branch {p['branch']} not found"
        except Exception as e:
            fetch_results[name] = f"error: {e}"
    try:
        reset_to_master("ng-deployment-config-files")
        fetch_results["ng-deployment-config-files"] = "ok"
    except Exception as e:
        fetch_results["ng-deployment-config-files"] = f"error: {e}"
    stages["fetch_repos"] = fetch_results

    all_tickets = []
    ticket_map = {}
    for p in projects:
        name = p["name"]
        try:
            tix = sorted(extract_tickets_for_project(name, p["branch"]))
            ticket_map[name] = []
            for tid in tix:
                try:
                    summary = jira.get_issue_summary(tid)
                except Exception:
                    summary = tid
                try:
                    breaking = gl.search_breaking_mrs(tid)
                except Exception:
                    breaking = False
                entry = {"id": tid, "summary": summary, "breaking": breaking}
                ticket_map[name].append(entry)
                all_tickets.append(entry)
        except Exception as e:
            ticket_map[name] = {"error": str(e)}
    stages["extract_tickets"] = ticket_map

    conflict_results = {}
    for p in projects:
        name = p["name"]
        try:
            report = check_conflicts(name, p["branch"])
            if report.clean:
                conflict_results[name] = "clean"
            else:
                conflict_results[name] = {
                    "conflicts": [
                        {"file": c.file, "simple": c.simple, "description": c.description}
                        for c in report.conflicts
                    ]
                }
        except Exception as e:
            conflict_results[name] = f"error: {e}"
    stages["merge_conflicts"] = conflict_results

    version_results = {}
    for p in projects:
        name = p["name"]
        try:
            nt = next_tag(name)
            p["next_tag"] = nt
            version_results[name] = {
                "current": nt.rsplit(".", 1)[0] + "." + str(max(0, int(nt.rsplit(".", 1)[1]) - 1)) if "." in nt else nt,
                "next": nt,
                "branch": p["branch_version"],
                "match": nt == p["branch_version"],
            }
        except Exception as e:
            version_results[name] = {"error": str(e)}
    stages["versions"] = version_results

    summary_text = cmd_summary(release_type, version, projects)
    ticket_refs = ", ".join(t["id"] for t in all_tickets)
    test_plan = f"Regression testing captured in {ngqa_ticket}" if ngqa_ticket else "Regression testing completed."
    stages["cmd_ticket"] = {
        "summary": summary_text,
        "ticket_refs": ticket_refs,
        "test_plan": test_plan,
    }

    mr_list = []
    for p in projects:
        name = p["name"]
        mr_list.append({
            "project": name,
            "source": p["branch"],
            "target": "master",
            "title": f"[CMD-XXXX] {summary_text}",
        })
    stages["merge_requests"] = mr_list

    if release_type in ("PLATFORM", "COMPOUND"):
        manifest_updates = []
        for p in projects:
            name = p["name"]
            if name in RUNTIME_PROJECTS:
                continue
            anchor = MANIFEST_ANCHORS.get(name)
            if anchor:
                nt = p.get("next_tag", p["branch_version"])
                try:
                    config_path = repo_path("ng-deployment-config-files")
                    manifest_file = os.path.join(config_path, "manifests", "default-manifest.yaml")
                    current_val = ""
                    if os.path.exists(manifest_file):
                        with open(manifest_file) as f:
                            content = f.read()
                        m = re.search(rf'{re.escape(anchor)}:\s*&{re.escape(anchor)}\s*"([^"]*?)"', content)
                        if m:
                            current_val = m.group(1)
                    manifest_updates.append({"anchor": anchor, "from": current_val, "to": nt})
                except Exception:
                    manifest_updates.append({"anchor": anchor, "from": "unknown", "to": nt})
        stages["manifest_updates"] = manifest_updates

    try:
        config_project = "ng-deployment-config-files"
        config_path = fetch_all(config_project)
        diff_output = run(
            "git diff origin/master..origin/qa -- tenant-specific-overrides/",
            cwd=config_path, check=False,
        )
        has_variance = False
        for line in diff_output.splitlines():
            if line.startswith("diff --git"):
                match = re.search(r'b/(tenant-specific-overrides/\S+)', line)
                if match and os.path.basename(match.group(1)) not in EXCLUDED_TENANTS:
                    has_variance = True
                    break
        stages["config_variance"] = {"detected": has_variance}
    except Exception as e:
        stages["config_variance"] = {"error": str(e)}

    stages["slack_notification"] = f"I have created a [change ticket](https://abacusinsights.atlassian.net/browse/CMD-XXXX) ..."

    if release_type == "COMPOUND":
        runtime_projects = [p for p in projects if p["name"] in RUNTIME_PROJECTS]
        platform_projects = [p for p in projects if p["name"] not in RUNTIME_PROJECTS]
        output["phases"] = {
            "phase_1_air_onyx": {
                "projects": [p["name"] for p in runtime_projects],
                "cmd_ticket": stages["cmd_ticket"],
                "merge_requests": [mr for mr in mr_list if mr["project"] in {p["name"] for p in runtime_projects}],
            },
            "phase_2_prerelease": {
                "branches": [f"CMD-XXXX from qa for globals update"],
                "globals_updates": parsed.get("globals_files", []),
                "merge_requests": [f"CMD-XXXX → qa for each globals project"],
                "cherry_picks": [
                    {"project": p["name"], "note": "would cherry-pick merge commit into release branch"}
                    for p in runtime_projects
                ],
            },
            "phase_3_platform": {
                "projects": [p["name"] for p in platform_projects],
                "cmd_ticket": {"summary": f"NextGen {version} Release"},
                "merge_requests": [mr for mr in mr_list if mr["project"] in {p["name"] for p in platform_projects}],
                "manifest_updates": stages.get("manifest_updates", []),
            },
        }

    print(json.dumps(output, indent=2))


def do_setup_dryrun_branches(args):
    parsed = json.loads(sys.stdin.read())
    projects = parsed.get("projects", [])
    version = parsed.get("version", "")

    branch_manifest = {}
    results = {}

    for p in projects:
        name = p["name"]
        src = p["branch"]
        dst = src.replace("release-", "dryrun-", 1)
        try:
            copy_branch(name, src, dst)
            results[name] = dst
            branch_manifest[name] = {"src": src, "dst": dst}
        except Exception as e:
            results[name] = f"error: {e}"
            branch_manifest[name] = {"src": src, "dst": dst, "error": str(e)}

    config_project = "ng-deployment-config-files"
    config_dst = f"dryrun-{version}"
    try:
        copy_branch(config_project, "master", config_dst)
        results[config_project] = config_dst
        branch_manifest[config_project] = {"src": "master", "dst": config_dst}
    except Exception as e:
        results[config_project] = f"error: {e}"
        branch_manifest[config_project] = {"src": "master", "dst": config_dst, "error": str(e)}

    dryrun_dir = os.path.join(RELEASE_BASE, f"{version}-dryrun")
    os.makedirs(dryrun_dir, exist_ok=True)
    manifest_path = os.path.join(dryrun_dir, "dryrun_branches.json")
    with open(manifest_path, "w") as f:
        json.dump(branch_manifest, f, indent=2)

    print(json.dumps(results, indent=2))


def do_cleanup_dryrun(args):
    version = args.version
    delete_artifacts = args.delete_artifacts
    dryrun_dir = os.path.join(RELEASE_BASE, f"{version}-dryrun")
    manifest_path = os.path.join(dryrun_dir, "dryrun_branches.json")

    if not os.path.exists(manifest_path):
        print(json.dumps({"error": f"No dryrun manifest found at {manifest_path}"}))
        sys.exit(1)

    with open(manifest_path) as f:
        branch_manifest = json.load(f)

    gl = load_gitlab()
    results = {}

    for project_name, info in branch_manifest.items():
        dst = info["dst"]
        project_results = {"branch": dst, "actions": []}
        try:
            path = repo_path(project_name)
            run(f"git push origin --delete {dst}", cwd=path, check=False)
            project_results["actions"].append("remote branch deleted")
        except Exception as e:
            project_results["actions"].append(f"remote delete failed: {e}")

        try:
            path = repo_path(project_name)
            run(f"git branch -D {dst}", cwd=path, check=False)
            project_results["actions"].append("local branch deleted")
        except Exception:
            pass

        try:
            encoded_path = f"{gl.PROJECT_PREFIX}/{project_name}"
            encoded = gl._encode_project(encoded_path)
            mrs = gl._get(
                f"/projects/{encoded}/merge_requests",
                params={"source_branch": dst, "state": "opened"},
            )
            for mr in mrs:
                if "[DRY-RUN]" in mr.get("title", ""):
                    gl._put(f"/projects/{encoded}/merge_requests/{mr['iid']}", {"state_event": "close"})
                    project_results["actions"].append(f"closed MR !{mr['iid']}")
        except Exception as e:
            project_results["actions"].append(f"MR cleanup failed: {e}")

        results[project_name] = project_results

    if delete_artifacts:
        import shutil
        shutil.rmtree(dryrun_dir, ignore_errors=True)
        results["artifacts"] = "deleted"
    else:
        results["artifacts"] = f"kept at {dryrun_dir}"

    print(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Bacon Release Agent")
    parser.add_argument("--dry-run-level", type=int, default=None,
                        dest="dry_run_level",
                        help="0=preview only, 1=sandboxed branches")
    sub = parser.add_subparsers(dest="command")

    p_parse = sub.add_parser("parse")
    p_parse.add_argument("--input", default="-")

    sub.add_parser("classify")
    sub.add_parser("fetch-repos")

    p_extract = sub.add_parser("extract-tickets")
    p_extract.add_argument("--project", required=True)
    p_extract.add_argument("--branch", required=True)

    p_tag = sub.add_parser("next-tag")
    p_tag.add_argument("--project", required=True)

    sub.add_parser("check-conflicts")
    sub.add_parser("create-cmd")
    sub.add_parser("create-mr")
    sub.add_parser("update-manifest")
    sub.add_parser("detect-variance")

    p_verify = sub.add_parser("verify-mr-merged")
    p_verify.add_argument("--project", required=True)
    p_verify.add_argument("--iid", type=int, required=True)

    sub.add_parser("update-globals")
    sub.add_parser("cherry-pick")
    sub.add_parser("save-artifacts")

    p_breaking = sub.add_parser("search-breaking")
    p_breaking.add_argument("--ticket", required=True)

    p_summary = sub.add_parser("get-summary")
    p_summary.add_argument("--ticket", required=True)

    sub.add_parser("enrich-tickets")
    sub.add_parser("preview")
    sub.add_parser("setup-dryrun-branches")

    p_cleanup = sub.add_parser("cleanup-dryrun")
    p_cleanup.add_argument("--version", required=True)
    p_cleanup.add_argument("--delete-artifacts", action="store_true", dest="delete_artifacts")

    args = parser.parse_args()

    if args.dry_run_level is not None and args.dry_run_level > 1:
        print(f"WARNING: Unknown dry-run level {args.dry_run_level}, treating as level 1", file=sys.stderr)
        args.dry_run_level = 1

    dispatch = {
        "parse": do_parse,
        "classify": do_classify,
        "fetch-repos": do_fetch_repos,
        "extract-tickets": do_extract_tickets,
        "next-tag": do_next_tag,
        "check-conflicts": do_check_conflicts,
        "create-cmd": do_create_cmd,
        "create-mr": do_create_mr,
        "update-manifest": do_update_manifest,
        "detect-variance": do_detect_variance,
        "verify-mr-merged": do_verify_mr_merged,
        "update-globals": do_update_globals,
        "cherry-pick": do_cherry_pick,
        "save-artifacts": do_save_artifacts,
        "search-breaking": do_search_breaking,
        "get-summary": do_get_summary,
        "enrich-tickets": do_enrich_tickets,
        "preview": do_preview,
        "setup-dryrun-branches": do_setup_dryrun_branches,
        "cleanup-dryrun": do_cleanup_dryrun,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
