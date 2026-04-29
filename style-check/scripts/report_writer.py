#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def compute_grade(findings: list[dict]) -> str:
    crits = sum(1 for f in findings if f["severity"] == "CRITICAL")
    majors = sum(1 for f in findings if f["severity"] == "MAJOR")
    has_missing_packaging = any(
        f["severity"] == "CRITICAL" and "seiji-packaging.yaml" in f.get("message", "")
        for f in findings
    )
    if crits >= 5 or has_missing_packaging:
        return "F"
    if crits >= 1:
        return "D"
    if majors > 2:
        return "C"
    if majors >= 1:
        return "B"
    return "A"


def generate_report(
    findings: list[dict],
    scan_target: str = "",
    scan_mode: str = "full",
) -> str:
    crits = sum(1 for f in findings if f["severity"] == "CRITICAL")
    majors = sum(1 for f in findings if f["severity"] == "MAJOR")
    minors = sum(1 for f in findings if f["severity"] == "MINOR")
    suggestions = sum(1 for f in findings if f["severity"] == "SUGGESTION")
    dimensions = sorted(set(f.get("dimension", "unknown") for f in findings))
    grade = compute_grade(findings)

    grouped: dict[str, list[dict]] = {}
    for f in findings:
        grouped.setdefault(f.get("dimension", "unknown"), []).append(f)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), keep_trailing_newline=True)
    template = env.get_template("style-report.md.j2")

    return template.render(
        scan_target=scan_target,
        scan_mode=scan_mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
        verdict_critical=crits,
        verdict_major=majors,
        verdict_minor=minors,
        verdict_suggestion=suggestions,
        dimensions_checked=dimensions,
        overall_compliance=grade,
        grouped=grouped,
    )


def main():
    parser = argparse.ArgumentParser(description="Generate style-check report from findings JSON")
    parser.add_argument("findings_json", help="Path to findings JSON file")
    parser.add_argument("--target", default="", help="Scan target path")
    parser.add_argument("--mode", default="full", choices=["full", "diff", "single"])
    args = parser.parse_args()

    with open(args.findings_json) as f:
        findings = json.load(f)

    report = generate_report(findings, scan_target=args.target, scan_mode=args.mode)
    print(report)


if __name__ == "__main__":
    main()
