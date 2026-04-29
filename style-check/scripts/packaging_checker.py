#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import yaml


def load_config():
    config_path = Path(__file__).resolve().parent.parent / "config" / "standards.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _finding(base, severity, message, recommendation):
    return {**base, "severity": severity, "message": message, "recommendation": recommendation}


def check_packaging(repo_path: str) -> list[dict]:
    findings = []
    config = load_config()
    pkg_config = config["packaging"]
    executor_image = config["seiji"]["executor_image"]

    repo = Path(repo_path)
    packaging_file = repo / "seiji-packaging.yaml"

    if not packaging_file.exists():
        return [_finding(
            {"dimension": "packaging", "file": str(packaging_file)},
            "CRITICAL", "seiji-packaging.yaml not found", "Create seiji-packaging.yaml"
        )]

    with open(packaging_file) as f:
        data = yaml.safe_load(f)

    base = {"dimension": "packaging", "file": str(packaging_file)}

    if "deployable_packages" not in data:
        return [_finding(base, "CRITICAL", "Missing 'deployable_packages' key",
                         "Add deployable_packages section")]

    for coord, pkg in data["deployable_packages"].items():
        pkg = pkg or {}
        hooks = pkg.get("hooks", {})

        for required_hook in pkg_config["required_hooks"]:
            if required_hook not in hooks:
                findings.append(_finding(base, "CRITICAL",
                    f"Package '{coord}' missing hooks.{required_hook}",
                    f"Add hooks.{required_hook} to package"))
            else:
                hook_path = repo / hooks[required_hook]
                if not hook_path.exists():
                    findings.append(_finding(base, "MAJOR",
                        f"Hook file not found: {hooks[required_hook]}",
                        f"Create {hooks[required_hook]}"))

        descriptors = pkg.get("descriptors", {})
        for desc_key in ("config", "dependencies"):
            if desc_key in descriptors:
                desc_path = repo / descriptors[desc_key]
                if not desc_path.exists():
                    findings.append(_finding(base, "MAJOR",
                        f"Descriptor file not found: {descriptors[desc_key]}",
                        f"Create {descriptors[desc_key]}"))

        executor = pkg.get("executor", {})
        if "image" in executor and not executor["image"].startswith(executor_image):
            findings.append(_finding(base, "MAJOR",
                f"Unexpected executor image: {executor['image']}",
                f"Expected image starting with {executor_image}"))

        files = pkg.get("files", {})
        if "include" not in files:
            findings.append(_finding(base, "MINOR",
                f"Package '{coord}' missing files.include",
                "Add files.include to specify included files"))

    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to repo root")
    args = parser.parse_args()
    findings = check_packaging(args.path)
    for f in findings:
        print(f"[{f['severity']}] {f['message']}")
    if not findings:
        print("No packaging issues found.")
    sys.exit(1 if any(f["severity"] == "CRITICAL" for f in findings) else 0)


if __name__ == "__main__":
    main()
