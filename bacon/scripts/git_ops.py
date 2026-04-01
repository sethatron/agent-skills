#!/usr/bin/env python3

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

GIT_BASE = os.path.expanduser("~/.release/git")
GITLAB_PREFIX = "git@gitlab.com:abacusinsights/abacus-v2/next-gen-platform"


def run(cmd: str, cwd: Optional[str] = None, check: bool = True) -> str:
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )
    return result.stdout.strip()


def repo_path(project: str) -> str:
    base_project = project.split("/")[0] if "/" in project else project
    return os.path.join(GIT_BASE, base_project)


def ensure_repo(project: str) -> str:
    path = repo_path(project)
    base_project = project.split("/")[0] if "/" in project else project
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        clone_url = f"{GITLAB_PREFIX}/{base_project}.git"
        run(f"git clone {clone_url} {path}")
    return path


def fetch_all(project: str) -> str:
    path = ensure_repo(project)
    run("git fetch --all --tags --prune", cwd=path)
    return path


def reset_to_master(project: str) -> str:
    path = fetch_all(project)
    run("git checkout master", cwd=path)
    run("git reset --hard origin/master", cwd=path)
    return path


def checkout_branch(project: str, branch: str) -> str:
    path = fetch_all(project)
    run(f"git checkout {branch}", cwd=path)
    run(f"git pull", cwd=path, check=False)
    return path


def branch_exists(project: str, branch: str) -> bool:
    path = repo_path(project)
    result = subprocess.run(
        f"git rev-parse --verify origin/{branch}",
        shell=True, cwd=path, capture_output=True, text=True
    )
    return result.returncode == 0


def get_log_between(project: str, base: str, branch: str) -> str:
    path = repo_path(project)
    return run(f"git log {base}..origin/{branch} --oneline", cwd=path, check=False)


def extract_ticket_ids(log_text: str) -> Set[str]:
    return set(re.findall(r'(?<![A-Z-])([A-Z]{2,}-\d+)', log_text))


def get_master_log(project: str) -> str:
    path = repo_path(project)
    return run("git log master --oneline", cwd=path, check=False)


def extract_tickets_for_project(project: str, release_branch: str) -> Set[str]:
    reset_to_master(project)
    log = get_log_between(project, "master", release_branch)
    candidates = extract_ticket_ids(log)

    master_log = get_master_log(project)
    master_tickets = extract_ticket_ids(master_log)

    return candidates - master_tickets


def current_tag(project: str) -> Optional[str]:
    path = repo_path(project)
    try:
        tag = run("git describe --tags master", cwd=path)
        return tag if tag else None
    except subprocess.CalledProcessError:
        return None


def parse_version(tag: str) -> Tuple[int, int, int]:
    parts = tag.split(".")
    if len(parts) < 3:
        return (0, 0, 0)
    major = int(parts[0])
    minor = int(parts[1])
    patch_str = re.sub(r'[^0-9].*', '', parts[2])
    patch = int(patch_str) if patch_str else 0
    return (major, minor, patch)


def next_tag(project: str) -> str:
    path = reset_to_master(project)
    tag = current_tag(project)

    if not tag:
        now = datetime.now()
        return f"{now.strftime('%y')}.{now.month}.0"

    major, minor, patch = parse_version(tag)

    semver_path = os.path.join(path, "SEMVER")
    if os.path.exists(semver_path):
        try:
            run("git checkout qa", cwd=path)
            run("git pull", cwd=path, check=False)
            with open(semver_path) as f:
                sv_text = f.read().strip()
            sv_parts = sv_text.split(".")
            sv_major = int(sv_parts[0])
            sv_minor = int(sv_parts[1]) if len(sv_parts) > 1 else 0
            if sv_major > major or (sv_major == major and sv_minor > minor):
                run("git checkout master", cwd=path)
                return f"{sv_major}.{sv_minor}.0"
            run("git checkout master", cwd=path)
        except Exception:
            run("git checkout master", cwd=path, check=False)

    return f"{major}.{minor}.{patch + 1}"


def create_branch_from(project: str, base_branch: str, new_branch: str) -> str:
    path = fetch_all(project)
    run(f"git checkout {base_branch}", cwd=path)
    run(f"git pull", cwd=path, check=False)
    try:
        run(f"git branch -D {new_branch}", cwd=path, check=False)
    except Exception:
        pass
    run(f"git checkout -b {new_branch}", cwd=path)
    return path


def commit_and_push(project: str, branch: str, message: str, files: Optional[List[str]] = None) -> str:
    path = repo_path(project)
    if files:
        for f in files:
            run(f"git add {f}", cwd=path)
    else:
        run("git add -A", cwd=path)
    run(f'git commit -m "{message}"', cwd=path)
    run(f"git push -u origin {branch}", cwd=path)
    return path


def cherry_pick(project: str, branch: str, commit_sha: str) -> bool:
    path = fetch_all(project)
    run(f"git checkout {branch}", cwd=path)
    run("git pull", cwd=path, check=False)
    try:
        run(f"git cherry-pick -m 1 {commit_sha}", cwd=path)
        run("git push", cwd=path)
        return True
    except subprocess.CalledProcessError as e:
        run("git cherry-pick --abort", cwd=path, check=False)
        raise RuntimeError(f"Cherry-pick failed in {project}: {e.stderr}")


def copy_branch(project: str, src_branch: str, dst_branch: str) -> str:
    path = fetch_all(project)
    run(f"git checkout origin/{src_branch}", cwd=path)
    try:
        run(f"git branch -D {dst_branch}", cwd=path, check=False)
    except Exception:
        pass
    run(f"git checkout -b {dst_branch}", cwd=path)
    run(f"git push -u origin {dst_branch} --force", cwd=path)
    return path


def get_recent_commits_for_file(project: str, branch: str, filepath: str, limit: int = 5) -> str:
    path = repo_path(project)
    return run(
        f"git log origin/{branch} -- {filepath} --oneline -n {limit}",
        cwd=path, check=False
    )


def get_conflicting_files(project: str) -> List[str]:
    path = repo_path(project)
    output = run("git diff --name-only --diff-filter=U", cwd=path, check=False)
    return [f for f in output.splitlines() if f.strip()]
