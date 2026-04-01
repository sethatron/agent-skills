#!/usr/bin/env python3

import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from git_ops import run, repo_path, fetch_all, get_conflicting_files, get_recent_commits_for_file


@dataclass
class ConflictInfo:
    file: str
    simple: bool = True
    description: str = ""
    cause_commits: List[str] = field(default_factory=list)
    mr_refs: List[str] = field(default_factory=list)
    author_names: List[str] = field(default_factory=list)


@dataclass
class ProjectConflictReport:
    project: str
    release_branch: str
    clean: bool = True
    conflicts: List[ConflictInfo] = field(default_factory=list)
    has_complex: bool = False


def check_conflicts(project: str, release_branch: str) -> ProjectConflictReport:
    report = ProjectConflictReport(project=project, release_branch=release_branch)
    path = fetch_all(project)

    run(f"git checkout {release_branch}", cwd=path)
    run("git pull", cwd=path, check=False)

    result = subprocess.run(
        "git merge origin/master --no-commit --no-ff",
        shell=True, cwd=path, capture_output=True, text=True
    )

    if result.returncode == 0:
        run("git merge --abort", cwd=path, check=False)
        return report

    report.clean = False
    conflicting = get_conflicting_files(project)

    for filepath in conflicting:
        info = ConflictInfo(file=filepath)

        master_commits = get_recent_commits_for_file(project, "master", filepath)
        info.cause_commits = [l for l in master_commits.splitlines() if l.strip()]

        for commit_line in info.cause_commits:
            mr_match = re.search(r'See merge request.*!(\d+)', commit_line)
            if mr_match:
                info.mr_refs.append(mr_match.group(1))

        info.simple, info.description = classify_conflict(path, filepath)
        if not info.simple:
            report.has_complex = True

        report.conflicts.append(info)

    run("git merge --abort", cwd=path)
    return report


def classify_conflict(repo_dir: str, filepath: str) -> tuple:
    try:
        content = run(f"git diff {filepath}", cwd=repo_dir, check=False)
    except Exception:
        return (False, "Unable to read conflict diff")

    conflict_markers = content.count("<<<<<<<")

    version_patterns = [
        r'version', r'VERSION', r'\.tf$', r'globals',
        r'SEMVER', r'\.lock$', r'package\.json',
    ]
    is_version_file = any(re.search(p, filepath) for p in version_patterns)

    if conflict_markers <= 1 and is_version_file:
        return (True, f"Version/config value conflict in {filepath} — likely needs the newer value")

    if conflict_markers <= 1 and content.count("+++") <= 3:
        lines_changed = len([l for l in content.splitlines() if l.startswith("+") or l.startswith("-")])
        if lines_changed < 10:
            return (True, f"Minor conflict in {filepath} — adjacent-line additions")

    if conflict_markers > 2:
        return (False, f"Multiple conflict regions ({conflict_markers}) in {filepath} — requires developer review")

    return (False, f"Semantic conflict in {filepath} — both branches made meaningful changes")


def format_report(reports: List[ProjectConflictReport]) -> str:
    lines = ["=== Merge Conflict Report ==="]
    for r in reports:
        if r.clean:
            lines.append(f"* {r.project}: Clean")
        else:
            for c in r.conflicts:
                label = "simple, auto-resolvable" if c.simple else "COMPLEX, needs developer input"
                lines.append(f"* {r.project}: CONFLICT — {c.file} ({label})")
                if c.description:
                    lines.append(f"  {c.description}")
                for commit in c.cause_commits[:3]:
                    lines.append(f"  Cause: {commit}")
    return "\n".join(lines)


def format_conflict_slack(project: str, conflict: ConflictInfo,
                          conflict_mr_url: Optional[str] = None,
                          original_mr_url: Optional[str] = None,
                          author_name: str = "unknown") -> str:
    lines = [
        "There has been a merge conflict identified in the following project(s). "
        "A temporary branch has been created to visualize the conflict:",
    ]
    if conflict_mr_url:
        lines.append(f"* [{project}]({conflict_mr_url}) — conflict in: {conflict.file}")
    else:
        lines.append(f"* {project} — conflict in: {conflict.file}")

    if original_mr_url:
        lines.append(f"  * Caused by: [MR]({original_mr_url}) by {author_name}")

    lines.append(f"\nCould we clarify the correct path forward here? cc: {author_name}")
    return "\n".join(lines)
