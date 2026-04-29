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


def check_terraform(path: str) -> list[dict]:
    root = Path(path).resolve()
    config = load_config()["terraform"]
    findings = []

    tf_files = list(root.rglob("*.tf")) if root.is_dir() else [root]

    allowed_module_prefixes = config.get("allowed_module_source_prefixes", [])

    for tf in tf_files:
        content = tf.read_text()
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            m = re.search(r'module\s+"[^"]+"\s*\{', line)
            if m:
                for j in range(i - 1, min(i + 20, len(lines))):
                    src = re.search(r'source\s*=\s*"([^"]+)"', lines[j])
                    if src:
                        source_val = src.group(1)
                        if not any(source_val.startswith(p) for p in allowed_module_prefixes):
                            findings.append({
                                "dimension": "terraform",
                                "severity": "CRITICAL",
                                "file": str(tf),
                                "line": j + 1,
                                "message": f"Module source '{source_val}' does not use an allowed prefix",
                                "recommendation": f"Use source starting with one of: {', '.join(allowed_module_prefixes)}",
                            })
                        break

        for m in re.finditer(r'variable\s+"([^"]+)"', content):
            name = m.group(1)
            if name != name.lower() or not re.match(r'^[a-z][a-z0-9_]*$', name):
                line_num = content[:m.start()].count("\n") + 1
                findings.append({
                    "dimension": "terraform",
                    "severity": "MINOR",
                    "file": str(tf),
                    "line": line_num,
                    "message": f"Variable '{name}' does not use lower_snake_case",
                    "recommendation": "Rename variable to lower_snake_case.",
                })

    layer_pattern = re.compile(r"terraform/layers/[^/]+/[^/]+/")
    for tf in tf_files:
        rel = str(tf.relative_to(root)) if root.is_dir() else str(tf)
        if "terraform" in rel and "layers" not in rel:
            if not layer_pattern.search(rel):
                findings.append({
                    "dimension": "terraform",
                    "severity": "SUGGESTION",
                    "file": str(tf),
                    "message": "Terraform file not in standard layers/{domain}/{function}/ path",
                    "recommendation": "Organize terraform into terraform/layers/{domain}/{function}/.",
                })

    return findings


def main():
    parser = argparse.ArgumentParser(description="Check Terraform files for style compliance")
    parser.add_argument("path", help="Repo root or specific .tf file path")
    args = parser.parse_args()
    findings = check_terraform(args.path)
    for f in findings:
        line = f" (line {f['line']})" if f.get("line") else ""
        print(f"[{f['severity']}] {f['file']}{line}: {f['message']}")
    sys.exit(1 if any(f["severity"] in ("CRITICAL", "MAJOR") for f in findings) else 0)


if __name__ == "__main__":
    main()
