#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "standards.yaml"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def check_helmsman(dsy_path: str) -> list[dict]:
    dsy_file = Path(dsy_path).resolve()
    findings = []
    config = load_config()["helmsman"]
    known_repos = set(config["helm_repos"].keys())

    if not dsy_file.exists():
        findings.append({
            "dimension": "helmsman",
            "severity": "CRITICAL",
            "file": str(dsy_file),
            "message": "desired-state.yaml not found",
            "recommendation": "Create desired-state.yaml for helmsman deployment.",
        })
        return findings

    with open(dsy_file) as f:
        dsy = yaml.safe_load(f) or {}

    if "context" not in dsy:
        findings.append({
            "dimension": "helmsman",
            "severity": "MAJOR",
            "file": str(dsy_file),
            "message": "Missing 'context' field",
            "recommendation": "Add context field specifying the target k8s context.",
        })

    repos = dsy.get("helmRepos", {})
    if not repos:
        findings.append({
            "dimension": "helmsman",
            "severity": "MAJOR",
            "file": str(dsy_file),
            "message": "Missing or empty 'helmRepos'",
            "recommendation": "Define at least one helm repo.",
        })

    apps = dsy.get("apps", {})
    if not apps:
        findings.append({
            "dimension": "helmsman",
            "severity": "MAJOR",
            "file": str(dsy_file),
            "message": "Missing or empty 'apps'",
            "recommendation": "Define at least one app in the desired state.",
        })

    for app_key, app in (apps or {}).items():
        if not isinstance(app, dict):
            continue

        for field in ("name", "chart", "version"):
            if field not in app:
                findings.append({
                    "dimension": "helmsman",
                    "severity": "CRITICAL",
                    "file": str(dsy_file),
                    "message": f"App '{app_key}' missing required field '{field}'",
                    "recommendation": f"Add '{field}' to app '{app_key}'.",
                })

        if "namespace" not in app:
            findings.append({
                "dimension": "helmsman",
                "severity": "MAJOR",
                "file": str(dsy_file),
                "message": f"App '{app_key}' missing 'namespace'",
                "recommendation": f"Add namespace to app '{app_key}'.",
            })

        chart = app.get("chart", "")
        if chart:
            repo_name = chart.split("/")[0] if "/" in chart else chart
            if repo_name not in known_repos and not chart.startswith("local-charts/"):
                findings.append({
                    "dimension": "helmsman",
                    "severity": "SUGGESTION",
                    "file": str(dsy_file),
                    "message": f"App '{app_key}' chart repo '{repo_name}' not in known repos",
                    "recommendation": f"Known repos: {', '.join(sorted(known_repos))}. Verify this is intentional.",
                })

        for vf in app.get("valuesFiles", []):
            vf_path = dsy_file.parent / vf
            if not vf_path.exists():
                findings.append({
                    "dimension": "helmsman",
                    "severity": "MINOR",
                    "file": str(vf_path),
                    "message": f"Values file '{vf}' referenced by app '{app_key}' not found",
                    "recommendation": f"Create {vf} or fix the path in valuesFiles.",
                })

    return findings


def main():
    parser = argparse.ArgumentParser(description="Check desired-state.yaml for helmsman compliance")
    parser.add_argument("path", help="Path to desired-state.yaml")
    args = parser.parse_args()
    findings = check_helmsman(args.path)
    for f in findings:
        print(f"[{f['severity']}] {f['file']}: {f['message']}")
    sys.exit(1 if any(f["severity"] in ("CRITICAL", "MAJOR") for f in findings) else 0)


if __name__ == "__main__":
    main()
