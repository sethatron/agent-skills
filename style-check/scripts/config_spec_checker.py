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


def find_tf_variables(spec_path: Path) -> set[str]:
    variables = set()
    for tf_file in spec_path.parent.glob("*.tf"):
        for match in re.finditer(r'variable\s+"(\w+)"', tf_file.read_text()):
            variables.add(match.group(1))
    return variables


def _finding(base, severity, message, recommendation):
    return {**base, "severity": severity, "message": message, "recommendation": recommendation}


def check_config_spec(spec_path: str) -> list[dict]:
    findings = []
    config = load_config()
    cs = config["config_spec"]
    valid_types = cs["valid_types"]
    required_fields = cs["required_fields"]

    path = Path(spec_path)
    base = {"dimension": "config_spec", "file": str(path)}

    if not path.exists():
        return [_finding(base, "CRITICAL", "Config spec file not found",
                         "Create luna-config-spec.yaml")]

    with open(path) as f:
        data = yaml.safe_load(f)

    if "config" not in (data or {}):
        return [_finding(base, "CRITICAL", "Missing 'config' root key", "Add config root key")]

    tf_vars = find_tf_variables(path)

    for component, variables in (data["config"] or {}).items():
        if not isinstance(variables, dict):
            continue
        for var_name, var_def in variables.items():
            var_def = var_def or {}
            qualified = f"{component}/{var_name}"

            for field in required_fields:
                if field not in var_def:
                    findings.append(_finding(base, "CRITICAL",
                        f"Variable '{qualified}' missing required field '{field}'",
                        f"Add '{field}' to variable definition"))

            if "type" in var_def and var_def["type"] not in valid_types:
                findings.append(_finding(base, "MAJOR",
                    f"Variable '{qualified}' has invalid type '{var_def['type']}'",
                    f"Use one of: {', '.join(valid_types)}"))

            if var_def.get("tfvar") and var_name not in tf_vars:
                findings.append(_finding(base, "MINOR",
                    f"Variable '{qualified}' has tfvar=true but no matching Terraform variable",
                    f'Add variable "{var_name}" block to a .tf file'))

            if var_def.get("secret") and "default" in var_def:
                findings.append(_finding(base, "MAJOR",
                    f"Secret variable '{qualified}' has a default value",
                    "Remove default from secret variables"))

    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to luna-config-spec.yaml")
    args = parser.parse_args()
    findings = check_config_spec(args.path)
    for f in findings:
        print(f"[{f['severity']}] {f['message']}")
    if not findings:
        print("No config spec issues found.")
    sys.exit(1 if any(f["severity"] == "CRITICAL" for f in findings) else 0)


if __name__ == "__main__":
    main()
