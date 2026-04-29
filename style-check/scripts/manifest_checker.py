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


def check_manifest(coordinate: str, repo_name: str) -> list[dict]:
    config = load_config()
    findings = []

    coord_pattern = config["seiji"]["coordinate_pattern"]
    if not re.match(coord_pattern, coordinate):
        findings.append({
            "dimension": "manifest",
            "severity": "MAJOR",
            "file": "",
            "message": f"Coordinate '{coordinate}' does not match pattern {coord_pattern}",
            "recommendation": "Use format: product.subsystem.operation",
        })

    anchor_pattern = config["manifest"]["version_anchor_pattern"]
    expected_anchor = anchor_pattern.replace("{repo-name}", repo_name)
    findings.append({
        "dimension": "manifest",
        "severity": "SUGGESTION",
        "file": "",
        "message": f"Version anchor should be named '{expected_anchor}'",
        "recommendation": f"Use '&{expected_anchor}' in the deployment manifest.",
    })

    manifest_ver = config["manifest"]["manifest_version"]
    snippet = (
        f"  - coordinate: {coordinate}\n"
        f"    version: *{expected_anchor}\n"
        f"    manifest_version: \"{manifest_ver}\"\n"
        f"    protocol: {config['manifest']['shared_vars_protocol']}"
    )
    findings.append({
        "dimension": "manifest",
        "severity": "SUGGESTION",
        "file": "",
        "message": f"Suggested manifest entry:\n{snippet}",
        "recommendation": "Add this block to the ng-deployment-config-files manifest.",
    })

    return findings


def main():
    parser = argparse.ArgumentParser(description="Check manifest integration for a component")
    parser.add_argument("coordinate", help="Component coordinate (e.g., nextgen.eks.provision)")
    parser.add_argument("repo_name", help="Repository name")
    args = parser.parse_args()
    findings = check_manifest(args.coordinate, args.repo_name)
    for f in findings:
        print(f"[{f['severity']}] {f['message']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
