#!/usr/bin/env python3
"""Grade report formatting for dispatch-harness.

Reads quality-grades.yaml and grade-history.yaml to produce formatted
reports for standalone display and dispatch weekly report insertion.

Usage:
    python grade_reporter.py [--weekly] [--json]
"""

import argparse
import json as json_mod
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

GRADES_PATH = Path.home() / ".zsh" / "dispatch" / "harness" / "quality-grades.yaml"
HISTORY_PATH = Path.home() / ".zsh" / "dispatch" / "harness" / "grade-history.yaml"

GRADE_ORDER = ["A", "B", "C", "D", "F"]

COMPONENT_DISPLAY = {
    "skill_md": "SKILL.md",
    "docs_coverage": "docs/",
    "check_env_py": "check_env",
    "contracts": "Contracts",
}


def generate_report(grades: dict) -> str:
    """Generate a formatted grade report from quality-grades.yaml data."""
    skills = grades.get("skills", {})
    if not skills:
        return "No grade data available. Run `/dispatch-harness grade` first.\n"

    lines = []
    lines.append("# Framework Quality Report")
    lines.append("")
    lines.append(f"Generated: {grades.get('generated_at', 'unknown')}")
    lines.append(f"Generator: {grades.get('generated_by', 'unknown')}")
    lines.append("")

    summary = _build_summary_table(skills)
    lines.append("## Overall Grades")
    lines.append("")
    lines.extend(summary)
    lines.append("")

    regressions = []
    improvements = []
    for slug, data in skills.items():
        trend = data.get("trend")
        if trend == "regression":
            regressions.append(slug)
        elif trend == "improvement":
            improvements.append(slug)

    if regressions:
        lines.append("## Regressions")
        lines.append("")
        for slug in regressions:
            lines.append(f"- **{slug}**: grade regressed (beads issue created)")
        lines.append("")

    if improvements:
        lines.append("## Improvements")
        lines.append("")
        for slug in improvements:
            lines.append(f"- **{slug}**: grade improved")
        lines.append("")

    for slug in sorted(skills):
        data = skills[slug]
        components = data.get("components", {})
        lines.append(f"## {slug}")
        lines.append("")
        lines.append(f"**Overall: {data.get('overall', '?')}**")
        lines.append("")
        lines.append("| Component | Grade |")
        lines.append("|-----------|-------|")
        for comp in sorted(components):
            display = COMPONENT_DISPLAY.get(comp, comp.replace("_py", ".py"))
            lines.append(f"| {display} | {components[comp]} |")
        lines.append("")

    return "\n".join(lines)


def generate_weekly_summary(grade_history: list) -> str:
    """Generate weekly summary section for dispatch weekly report.

    Takes the 'entries' list from grade-history.yaml. Returns a markdown
    section suitable for insertion into the dispatch weekly report.
    """
    if not grade_history:
        return "## Framework Quality Grades\n\nNo grade history available.\n"

    latest = grade_history[-1]
    skills = latest.get("skills", {})

    lines = []
    lines.append("## Framework Quality Grades")
    lines.append("")
    lines.extend(_build_summary_table(skills))
    lines.append("")

    if len(grade_history) >= 2:
        previous = grade_history[-2]
        prev_skills = previous.get("skills", {})
        changes = _diff_snapshots(prev_skills, skills)
        if changes:
            lines.append("### Changes Since Last Run")
            lines.append("")
            for change in changes:
                arrow = "improved" if change["direction"] == "improvement" else "regressed"
                lines.append(
                    f"- {change['slug']}/{change['component']}: "
                    f"{change['old']} -> {change['new']} ({arrow})"
                )
            lines.append("")

    return "\n".join(lines)


def _build_summary_table(skills: dict) -> list[str]:
    all_components = set()
    for data in skills.values():
        all_components.update(data.get("components", {}).keys())

    core_cols = ["skill_md", "docs_coverage", "check_env_py", "contracts"]
    script_cols = sorted(c for c in all_components if c not in core_cols)

    cols = [c for c in core_cols if c in all_components]
    display_cols = [COMPONENT_DISPLAY.get(c, c.replace("_py", ".py")) for c in cols]

    lines = []
    header = "| Skill | Overall | " + " | ".join(display_cols) + " |"
    sep = "|---|---|" + "|".join("---" for _ in cols) + "|"
    lines.append(header)
    lines.append(sep)

    for slug in sorted(skills):
        data = skills[slug]
        components = data.get("components", {})
        row = f"| {slug} | {data.get('overall', '?')} |"
        for c in cols:
            row += f" {components.get(c, '-')} |"
        lines.append(row)

    return lines


def _diff_snapshots(prev: dict, current: dict) -> list[dict]:
    changes = []
    for slug, cur_data in current.items():
        prev_data = prev.get(slug, {})
        cur_comps = cur_data.get("components", {})
        prev_comps = prev_data.get("components", {})
        for comp, new_g in cur_comps.items():
            old_g = prev_comps.get(comp)
            if old_g and old_g != new_g:
                old_idx = GRADE_ORDER.index(old_g) if old_g in GRADE_ORDER else 4
                new_idx = GRADE_ORDER.index(new_g) if new_g in GRADE_ORDER else 4
                changes.append({
                    "slug": slug,
                    "component": comp,
                    "old": old_g,
                    "new": new_g,
                    "direction": "improvement" if new_idx < old_idx else "regression",
                })
    return changes


def main():
    parser = argparse.ArgumentParser(description="Generate grade report")
    parser.add_argument("--weekly", action="store_true", help="Weekly summary mode")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.weekly:
        if not HISTORY_PATH.exists():
            print("No grade history found. Run `/dispatch-harness grade` first.")
            sys.exit(1)
        with open(HISTORY_PATH) as f:
            history = yaml.safe_load(f) or {}
        entries = history.get("entries", [])

        if args.json:
            json_mod.dump({"entries_count": len(entries), "latest": entries[-1] if entries else None}, sys.stdout, indent=2)
            print()
        else:
            print(generate_weekly_summary(entries))
    else:
        if not GRADES_PATH.exists():
            print("No grade data found. Run `/dispatch-harness grade` first.")
            sys.exit(1)
        with open(GRADES_PATH) as f:
            grades = yaml.safe_load(f) or {}

        if args.json:
            json_mod.dump(grades, sys.stdout, indent=2)
            print()
        else:
            print(generate_report(grades))


if __name__ == "__main__":
    main()
