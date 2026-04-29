#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

import yaml


def load_config():
    config_path = Path(__file__).resolve().parent.parent / "config" / "standards.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_registry():
    registry_path = Path(__file__).resolve().parent.parent / "references" / "coordinate-registry.md"
    coords = set()
    if not registry_path.exists():
        return coords
    for line in registry_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("|") and not line.startswith("|-") and "Coordinate" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and parts[1]:
                coords.add(parts[1])
    return coords


def _finding(base, severity, message, recommendation):
    return {**base, "severity": severity, "message": message, "recommendation": recommendation}


def check_coordinates(repo_path: str) -> list[dict]:
    findings = []
    config = load_config()
    seiji = config["seiji"]
    pattern = seiji["coordinate_pattern"]
    known_products = seiji["known_products"]
    known_operations = seiji["known_operations"]
    registry = load_registry()

    repo = Path(repo_path)
    packaging_file = repo / "seiji-packaging.yaml"
    if not packaging_file.exists():
        return [_finding(
            {"dimension": "coordinate", "file": str(packaging_file)},
            "CRITICAL", "seiji-packaging.yaml not found", "Create seiji-packaging.yaml"
        )]

    with open(packaging_file) as f:
        data = yaml.safe_load(f)

    packages = data.get("deployable_packages", {})
    for coord_key in packages:
        base = {"dimension": "coordinate", "file": str(packaging_file)}

        if not re.match(pattern, coord_key):
            findings.append(_finding(base, "CRITICAL",
                f"Coordinate '{coord_key}' does not match pattern {pattern}",
                "Use format product.subsystem.operation"))
            continue

        if coord_key != coord_key.lower():
            findings.append(_finding(base, "CRITICAL",
                f"Coordinate '{coord_key}' contains uppercase", "Use lowercase only"))

        if "-" in coord_key:
            findings.append(_finding(base, "CRITICAL",
                f"Coordinate '{coord_key}' contains hyphens", "Use dots and underscores only"))

        parts = coord_key.split(".")
        if len(parts) == 3:
            product, _subsystem, operation = parts
            if product not in known_products:
                findings.append(_finding(base, "MAJOR",
                    f"Unknown product '{product}'", f"Expected one of: {', '.join(known_products)}"))
            if operation not in known_operations:
                findings.append(_finding(base, "MAJOR",
                    f"Unknown operation '{operation}'", f"Expected one of: {', '.join(known_operations)}"))

        if coord_key in registry:
            findings.append(_finding(base, "MINOR",
                f"Coordinate '{coord_key}' already exists in registry",
                "Verify this is intentional and not a collision"))

    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to repo root")
    args = parser.parse_args()
    findings = check_coordinates(args.path)
    for f in findings:
        print(f"[{f['severity']}] {f['message']}")
    if not findings:
        print("No coordinate issues found.")
    sys.exit(1 if any(f["severity"] == "CRITICAL" for f in findings) else 0)


if __name__ == "__main__":
    main()
