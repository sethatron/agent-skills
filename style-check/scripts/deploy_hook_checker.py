#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "standards.yaml"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def check_deploy_hooks(repo_path: str) -> list[dict]:
    repo = Path(repo_path).resolve()
    packaging_file = repo / "seiji-packaging.yaml"
    findings = []

    if not packaging_file.exists():
        findings.append({
            "dimension": "packaging",
            "severity": "CRITICAL",
            "file": str(packaging_file),
            "message": "seiji-packaging.yaml not found",
            "recommendation": "Create seiji-packaging.yaml in repository root.",
        })
        return findings

    with open(packaging_file) as f:
        packaging = yaml.safe_load(f)

    config = load_config()
    components = packaging.get("components", [])
    if not components and "component" in packaging:
        components = [packaging]

    for comp in components:
        coordinate = comp.get("coordinate", "unknown")
        is_helmsman = coordinate.endswith(".deploy")

        hooks = comp.get("hooks", {})
        create_path = hooks.get("create", config["packaging"]["default_create_path"])
        destroy_path = hooks.get("destroy", config["packaging"]["default_destroy_path"])

        create_file = repo / create_path
        destroy_file = repo / destroy_path

        if not create_file.exists():
            findings.append({
                "dimension": "packaging",
                "severity": "CRITICAL",
                "file": str(create_file),
                "message": f"create.sh missing for {coordinate}",
                "recommendation": f"Create {create_path} with deployment logic.",
            })
        if not destroy_file.exists():
            findings.append({
                "dimension": "packaging",
                "severity": "CRITICAL",
                "file": str(destroy_file),
                "message": f"destroy.sh missing for {coordinate}",
                "recommendation": f"Create {destroy_path} with teardown logic.",
            })

        if create_file.exists() and not is_helmsman:
            content = create_file.read_text()
            if not re.search(r"source.*deploy_functions\.sh", content):
                findings.append({
                    "dimension": "packaging",
                    "severity": "MAJOR",
                    "file": str(create_file),
                    "message": "create.sh does not source deploy_functions.sh",
                    "recommendation": "Add 'source ./deploy_functions.sh' to create.sh.",
                })
            deploy_funcs = create_file.parent / "deploy_functions.sh"
            if not deploy_funcs.exists():
                findings.append({
                    "dimension": "packaging",
                    "severity": "MAJOR",
                    "file": str(deploy_funcs),
                    "message": "deploy_functions.sh missing alongside create.sh",
                    "recommendation": "Create deploy_functions.sh with standard terraform helpers.",
                })
            elif deploy_funcs.exists():
                df_content = deploy_funcs.read_text()
                if "seiji config generate tfvars" not in df_content:
                    findings.append({
                        "dimension": "packaging",
                        "severity": "MAJOR",
                        "file": str(deploy_funcs),
                        "message": "deploy_functions.sh missing 'seiji config generate tfvars'",
                        "recommendation": "Add tfvars generation via seiji config.",
                    })
                if "init_terraform" not in df_content:
                    findings.append({
                        "dimension": "packaging",
                        "severity": "MAJOR",
                        "file": str(deploy_funcs),
                        "message": "deploy_functions.sh missing init_terraform function",
                        "recommendation": "Add init_terraform function for backend setup.",
                    })

        if create_file.exists() and is_helmsman:
            dsy = repo / "desired-state.yaml"
            dsy_deploy = repo / "deploy" / "desired-state.yaml"
            if not dsy.exists() and not dsy_deploy.exists():
                findings.append({
                    "dimension": "packaging",
                    "severity": "MAJOR",
                    "file": str(repo),
                    "message": f"desired-state.yaml not found for helmsman component {coordinate}",
                    "recommendation": "Add desired-state.yaml in repo root or deploy/ directory.",
                })
            content = create_file.read_text()
            if "helmsman" not in content and "run_helmsman_isolated" not in content:
                findings.append({
                    "dimension": "packaging",
                    "severity": "MAJOR",
                    "file": str(create_file),
                    "message": "create.sh does not reference helmsman or run_helmsman_isolated",
                    "recommendation": "Add helmsman invocation to create.sh.",
                })

        migrate_dir = hooks.get("migrate")
        if migrate_dir:
            mpath = repo / migrate_dir
            if mpath.exists():
                numbered = [f for f in mpath.iterdir() if re.match(r"\d+", f.name)]
                if not numbered:
                    findings.append({
                        "dimension": "packaging",
                        "severity": "MINOR",
                        "file": str(mpath),
                        "message": "Migration directory exists but contains no numbered files",
                        "recommendation": "Add numbered migration files (e.g., 001_initial.sql).",
                    })

    return findings


def main():
    parser = argparse.ArgumentParser(description="Check deploy hooks in a seiji repo")
    parser.add_argument("path", help="Repository root path")
    args = parser.parse_args()
    findings = check_deploy_hooks(args.path)
    for f in findings:
        print(f"[{f['severity']}] {f['file']}: {f['message']}")
    sys.exit(1 if any(f["severity"] in ("CRITICAL", "MAJOR") for f in findings) else 0)


if __name__ == "__main__":
    main()
