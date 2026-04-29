#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


def parse_frontmatter(path):
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError):
        return {}
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def get_skill_md_body(path):
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError):
        return ""
    match = re.match(r'^---\s*\n.*?\n---\s*\n(.*)', text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def validate_frontmatter_version(skill_dir, req, verbose):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return "FAIL", "SKILL.md not found"
    fm = parse_frontmatter(skill_md)
    version = fm.get("version")
    if not version:
        return "FAIL", "no version field in frontmatter"
    if not re.match(r'^\d+\.\d+\.\d+$', str(version)):
        return "FAIL", f"version '{version}' does not match semver"
    return "PASS", f"version field present (v{version})"


def validate_content_pattern(skill_dir, req, verbose):
    params = req.get("params", {})
    filename = params.get("file", "SKILL.md")
    pattern = params.get("pattern", "")
    target = skill_dir / filename
    if not target.exists():
        return "FAIL", f"{filename} not found"
    text = target.read_text()
    body = get_skill_md_body(target) if filename == "SKILL.md" else text
    if re.search(pattern, body):
        return "PASS", f"pattern '{pattern}' found in {filename}"
    return req.get("severity", "FAIL"), f"pattern '{pattern}' not found in {filename}"


def validate_file_exists(skill_dir, req, verbose):
    params = req.get("params", {})
    rel_path = params.get("path", "")
    target = skill_dir / rel_path
    if target.exists():
        return "PASS", f"{rel_path} exists"
    return "FAIL", f"{rel_path} not found"


def validate_caller_identification(skill_dir, req, verbose):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return "FAIL", "SKILL.md not found"
    text = skill_md.read_text()
    invokes_jira = bool(re.search(r'/jira|JIRA_CALLER', text))
    if not invokes_jira:
        return "PASS", "skill does not invoke /jira (not applicable)"
    if "JIRA_CALLER" in text:
        return "PASS", "JIRA_CALLER reference found"
    return "FAIL", "invokes /jira but JIRA_CALLER not set"


def validate_git_permission(skill_dir, req, verbose):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return "FAIL", "SKILL.md not found"
    text = skill_md.read_text()

    has_guard = bool(re.search(r'git_permission|dispatch\.db', text))
    if has_guard:
        return "PASS", "git permission guard found"

    has_prohibition = bool(re.search(
        r'PROHIBITED.*git|git\s+add.*NEVER|git.*commit.*NEVER', text, re.DOTALL
    )) or (re.search(r'PROHIBITED', text) and re.search(r'git\s+(add|commit|push)', text))
    if has_prohibition:
        return "PASS", "blanket git prohibition found"

    has_git_writes = bool(re.search(
        r'git\s+(add|commit|push|merge|rebase|reset|checkout\s+-b)', text
    ))
    if not has_git_writes:
        return "PASS", "no git write operations referenced"

    return "FAIL", "git write ops found without permission guard or prohibition"


def validate_symlink_check(skill_dir, req, verbose):
    skill_md = skill_dir / "SKILL.md"
    fm = parse_frontmatter(skill_md) if skill_md.exists() else {}
    slug = fm.get("name")
    if not slug:
        slug = skill_dir.name
    symlink_path = Path.home() / ".claude" / "skills" / slug
    if symlink_path.exists():
        return "PASS", f"~/.claude/skills/{slug} exists"
    return "WARN", f"~/.claude/skills/{slug} not found"


def validate_artifact_schema(skill_dir, req, verbose):
    schema_path = skill_dir / "references" / "artifact-schema.yaml"
    if not schema_path.exists():
        return "FAIL", "references/artifact-schema.yaml not found"
    try:
        data = yaml.safe_load(schema_path.read_text())
    except Exception as e:
        return "FAIL", f"artifact-schema.yaml parse error: {e}"
    if not isinstance(data, dict):
        return "FAIL", "artifact-schema.yaml is not a mapping"
    required_fields = ["skill_name", "skill_version", "produced_at", "artifact_path", "status"]
    fields_key = None
    for candidate in ["fields", "required_fields", "properties", "schema"]:
        if candidate in data:
            fields_key = candidate
            break
    if fields_key and isinstance(data[fields_key], (dict, list)):
        check_target = data[fields_key]
        if isinstance(check_target, dict):
            present = [f for f in required_fields if f in check_target]
        else:
            present = [f for f in required_fields if f in check_target]
    else:
        flat_text = schema_path.read_text()
        present = [f for f in required_fields if f in flat_text]

    missing = [f for f in required_fields if f not in present]
    if missing:
        return "FAIL", f"artifact-schema.yaml missing fields: {', '.join(missing)}"
    return "PASS", "artifact-schema.yaml has all required base fields"


def validate_failure_docs(skill_dir, req, verbose):
    pattern = re.compile(r'failure|error\s+handling|Failure\s+Handling', re.IGNORECASE)
    found_in = []

    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists() and pattern.search(skill_md.read_text()):
        found_in.append("SKILL.md")

    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for f in refs_dir.iterdir():
            if f.is_file():
                try:
                    if pattern.search(f.read_text()):
                        found_in.append(f"references/{f.name}")
                except (PermissionError, UnicodeDecodeError):
                    continue

    if found_in:
        return "PASS", f"failure docs found in: {', '.join(found_in)}"
    return "WARN", "no failure/error handling documentation found"


VALIDATORS = {
    "frontmatter_version": validate_frontmatter_version,
    "content_pattern": validate_content_pattern,
    "file_exists": validate_file_exists,
    "caller_identification": validate_caller_identification,
    "git_permission": validate_git_permission,
    "symlink_check": validate_symlink_check,
    "artifact_schema": validate_artifact_schema,
    "failure_docs": validate_failure_docs,
}


def load_checklist(checklist_path):
    with open(checklist_path) as f:
        data = yaml.safe_load(f)
    return data.get("requirements", [])


def run_checks(skill_dir, checklist, skill_type, verbose):
    results = []
    for req in checklist:
        req_id = req["id"]
        req_types = req.get("types", ["A", "B", "C"])
        if skill_type not in req_types:
            results.append({
                "id": req_id,
                "name": req.get("name", ""),
                "status": "SKIP",
                "detail": f"not required for TYPE {skill_type}",
            })
            continue

        validator_name = req.get("validator", "")
        validator_fn = VALIDATORS.get(validator_name)
        if not validator_fn:
            results.append({
                "id": req_id,
                "name": req.get("name", ""),
                "status": "FAIL",
                "detail": f"unknown validator: {validator_name}",
            })
            continue

        try:
            status, detail = validator_fn(skill_dir, req, verbose)
        except Exception as e:
            status, detail = "FAIL", f"validator error: {e}"

        results.append({
            "id": req_id,
            "name": req.get("name", ""),
            "status": status,
            "detail": detail,
        })
    return results


def get_skill_name(skill_dir):
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        fm = parse_frontmatter(skill_md)
        if fm.get("name"):
            return fm["name"]
    return skill_dir.name


def print_report(skill_name, skill_path, skill_type, results):
    width = 64

    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    compliant = counts["FAIL"] == 0

    def pad(text):
        inner = width - 4
        return f"\u2551  {text:<{inner}}\u2551"

    print(f"\u2554\u2550\u2550 DSI Compliance Report {'=' * (width - 26)}\u2557")
    print(pad(f"Skill: {skill_name}   Path: {skill_path}   Type: {skill_type}"))
    print(f"\u2560{'=' * (width - 2)}\u2563")

    status_icons = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}
    for r in results:
        tag = status_icons[r["status"]]
        line = f"[{tag}] {r['id']}  {r['detail']}"
        print(pad(line))

    print(f"\u2560{'=' * (width - 2)}\u2563")
    summary = f"{counts['PASS']} PASS   {counts['WARN']} WARN   {counts['FAIL']} FAIL"
    print(pad(summary))
    if compliant:
        print(pad("Result:  COMPLIANT"))
    else:
        print(pad("Result:  NON-COMPLIANT \u2014 resolve FAILs before registering"))
    print(f"\u255a{'=' * (width - 2)}\u255d")


def main():
    parser = argparse.ArgumentParser(description="DSI Compliance Validator")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("--type", choices=["A", "B", "C"], default="B", dest="skill_type")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--checklist", default=None, help="Path to checklist.yaml")
    args = parser.parse_args()

    skill_dir = Path(args.skill_path).resolve()
    if not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    if args.checklist:
        checklist_path = Path(args.checklist)
    else:
        checklist_path = Path(__file__).resolve().parent.parent / "dsi" / "checklist.yaml"

    if not checklist_path.exists():
        print(f"Error: checklist not found at {checklist_path}", file=sys.stderr)
        sys.exit(2)

    checklist = load_checklist(checklist_path)
    skill_name = get_skill_name(skill_dir)
    results = run_checks(skill_dir, checklist, args.skill_type, args.verbose)

    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    if args.json_output:
        output = {
            "skill": skill_name,
            "path": str(skill_dir),
            "type": args.skill_type,
            "checks": results,
            "pass_count": counts["PASS"],
            "fail_count": counts["FAIL"],
            "warn_count": counts["WARN"],
            "skip_count": counts["SKIP"],
            "compliant": counts["FAIL"] == 0,
        }
        print(json.dumps(output, indent=2))
    else:
        print_report(skill_name, str(skill_dir), args.skill_type, results)

    if counts["FAIL"] > 0:
        sys.exit(2)
    elif counts["WARN"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
