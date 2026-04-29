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


VERSION_PATTERN = re.compile(r"^(>=|=)\d+\.\d+\.\d+")


def _finding(base, severity, message, recommendation):
    return {**base, "severity": severity, "message": message, "recommendation": recommendation}


def check_dependencies(dep_path: str) -> list[dict]:
    findings = []
    config = load_config()
    coord_pattern = config["seiji"]["coordinate_pattern"]
    registry = load_registry()

    path = Path(dep_path)
    base = {"dimension": "dependency", "file": str(path)}

    if not path.exists():
        return [_finding(base, "CRITICAL", "Dependencies file not found",
                         "Create luna-dependencies.yaml")]

    with open(path) as f:
        data = yaml.safe_load(f)

    if "dependencies" not in (data or {}):
        return [_finding(base, "CRITICAL", "Missing 'dependencies' key",
                         "Add dependencies root key")]

    for dep_key, dep_val in (data["dependencies"] or {}).items():
        if not re.match(coord_pattern, dep_key):
            findings.append(_finding(base, "MAJOR",
                f"Dependency '{dep_key}' does not match coordinate pattern",
                "Use format product.subsystem.operation"))

        version = str(dep_val.get("version", "")) if isinstance(dep_val, dict) else str(dep_val)
        if version and not VERSION_PATTERN.match(version):
            findings.append(_finding(base, "MAJOR",
                f"Dependency '{dep_key}' version '{version}' has invalid format",
                "Use format >=X.Y.Z or =X.Y.Z"))

        if dep_key not in registry:
            findings.append(_finding(base, "MINOR",
                f"Dependency '{dep_key}' not found in coordinate registry",
                "Verify this coordinate exists"))

    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to luna-dependencies.yaml")
    args = parser.parse_args()
    findings = check_dependencies(args.path)
    for f in findings:
        print(f"[{f['severity']}] {f['message']}")
    if not findings:
        print("No dependency issues found.")
    sys.exit(1 if any(f["severity"] == "CRITICAL" for f in findings) else 0)


if __name__ == "__main__":
    main()
