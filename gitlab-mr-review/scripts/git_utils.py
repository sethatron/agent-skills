#!/usr/bin/env python3
"""
Git operations for MR review — clone, checkout, branch management.

All operations are READ-ONLY. No git add, commit, push, or any remote
mutation is permitted.

Usage (CLI):
    python scripts/git_utils.py clone --url <repo-url> --branch <branch> --target <dir>
    python scripts/git_utils.py checkout --repo <dir> --branch <branch>

Usage (module):
    from git_utils import clone_for_review, checkout_branch
    repo_path = clone_for_review(repo_url, branch, target_dir)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

try:
    import git as gitpython
except ImportError:
    gitpython = None


PROHIBITED_OPERATIONS = {"add", "commit", "push", "push --force"}


def clone_for_review(
    repo_url: str,
    branch: str,
    target_dir: str,
    sparse: bool = True,
    changed_files: Optional[list[str]] = None,
) -> str:
    """
    Clone a repository for review purposes.

    Uses sparse checkout with --filter=blob:none when sparse=True and
    changed_files is provided, to avoid downloading the full history.

    Args:
        repo_url: Git remote URL (HTTPS).
        branch: Branch to checkout (MR source branch).
        target_dir: Directory to clone into.
        sparse: Use sparse checkout for efficiency.
        changed_files: List of file paths changed in the MR (for sparse checkout).

    Returns:
        Absolute path to the cloned repo directory.

    Raises:
        RuntimeError: If clone fails.
        ValueError: If target_dir is inside an existing repository.
    """
    target = Path(target_dir).resolve()
    if (target / ".git").exists():
        raise ValueError(f"Target {target} is already a git repository")
    parent = target.parent
    while parent != parent.parent:
        if (parent / ".git").exists():
            raise ValueError(f"Target {target} is inside existing repository at {parent}")
        parent = parent.parent

    if sparse and changed_files:
        import subprocess
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", repo_url, str(target)],
                       capture_output=True, text=True, check=True)
        subprocess.run(["git", "sparse-checkout", "init", "--cone"], cwd=str(target),
                       capture_output=True, text=True, check=True)
        subprocess.run(["git", "sparse-checkout", "set"] + changed_files, cwd=str(target),
                       capture_output=True, text=True, check=True)
        subprocess.run(["git", "checkout", branch], cwd=str(target),
                       capture_output=True, text=True, check=True)
    else:
        gitpython.Repo.clone_from(repo_url, str(target), branch=branch, depth=1)
    return str(target)


def checkout_branch(repo_dir: str, branch: str) -> str:
    """
    Checkout a specific branch in an existing repo.

    Args:
        repo_dir: Path to the git repository.
        branch: Branch name to checkout.

    Returns:
        The checked-out branch name.

    Raises:
        RuntimeError: If checkout fails or branch doesn't exist.
    """
    repo = gitpython.Repo(repo_dir)
    if branch not in [b.name for b in repo.branches]:
        try:
            repo.git.checkout(branch, track=True)
        except gitpython.GitCommandError as e:
            raise RuntimeError(f"Checkout failed: {e}")
    else:
        repo.git.checkout(branch)
    return branch


def create_review_branch(repo_dir: str, source_branch: str) -> str:
    """
    Create a local review branch: <source-branch>-review.

    This branch is never pushed.

    Args:
        repo_dir: Path to the git repository.
        source_branch: MR source branch name.

    Returns:
        Name of the created review branch.
    """
    repo = gitpython.Repo(repo_dir)
    review_name = f"{source_branch}-review"
    repo.git.checkout("-b", review_name)
    return review_name


def validate_local_project(
    project_dir: str,
    expected_branch: Optional[str] = None,
) -> dict:
    """
    Validate an existing local project directory for investigation mode.

    Checks:
    - Directory exists and contains .git
    - If expected_branch provided, checks it exists locally

    Args:
        project_dir: Path to local project.
        expected_branch: Expected MR source branch.

    Returns:
        Dict with keys: valid (bool), current_branch (str), has_expected_branch (bool).
    """
    p = Path(project_dir)
    if not (p / ".git").exists():
        return {"valid": False, "current_branch": None, "has_expected_branch": False}
    repo = gitpython.Repo(str(p))
    try:
        current = repo.active_branch.name
    except TypeError:
        current = "HEAD (detached)"
    has_branch = False
    if expected_branch:
        has_branch = expected_branch in [b.name for b in repo.branches]
    return {"valid": True, "current_branch": current, "has_expected_branch": has_branch}


def get_changed_files_from_diff(repo_dir: str, target_branch: str, source_branch: str) -> list[str]:
    """
    Get list of files changed between two branches.

    Args:
        repo_dir: Path to git repository.
        target_branch: MR target branch (e.g. main).
        source_branch: MR source branch.

    Returns:
        List of changed file paths.
    """
    repo = gitpython.Repo(repo_dir)
    diff_output = repo.git.diff("--name-only", f"{target_branch}...{source_branch}")
    return [f for f in diff_output.strip().split("\n") if f]


def main():
    parser = argparse.ArgumentParser(description="Git utilities for MR review")
    sub = parser.add_subparsers(dest="command", required=True)

    p_clone = sub.add_parser("clone", help="Clone repo for review")
    p_clone.add_argument("--url", required=True, help="Repository URL")
    p_clone.add_argument("--branch", required=True, help="Branch to checkout")
    p_clone.add_argument("--target", required=True, help="Target directory")
    p_clone.add_argument("--no-sparse", action="store_true")

    p_checkout = sub.add_parser("checkout", help="Checkout branch")
    p_checkout.add_argument("--repo", required=True, help="Repository path")
    p_checkout.add_argument("--branch", required=True, help="Branch name")

    p_validate = sub.add_parser("validate", help="Validate local project")
    p_validate.add_argument("--path", required=True)
    p_validate.add_argument("--branch")

    args = parser.parse_args()

    if args.command == "clone":
        path = clone_for_review(args.url, args.branch, args.target, sparse=not args.no_sparse)
        print(f"Cloned to: {path}")
    elif args.command == "checkout":
        branch = checkout_branch(args.repo, args.branch)
        print(f"Checked out: {branch}")
    elif args.command == "validate":
        import json
        result = validate_local_project(args.path, expected_branch=args.branch)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
