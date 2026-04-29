#!/usr/bin/env python3

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_skill_path(ecosystem, skill_name):
    skills = ecosystem.get("skills", {})
    entry = skills.get(skill_name)
    if not entry:
        return None
    return Path(os.path.expanduser(entry["path"]))


def file_contains(path, pattern):
    if not path.exists():
        return False, f"{path} not found"
    text = path.read_text()
    if pattern in text:
        return True, None
    return False, f"'{pattern}' not found in {path}"


def load_frontmatter_fields(path):
    spec = importlib.util.spec_from_file_location("review_writer", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FRONTMATTER_FIELDS


def check(ok, detail):
    return {"ok": ok, "detail": detail}


def validate_jira_caller(registry, ecosystem, verbose):
    contract = registry["contracts"]["jira_caller"]
    results = []

    jira_path = resolve_skill_path(ecosystem, "jira")
    dispatch_path = resolve_skill_path(ecosystem, "dispatch")
    mr_review_path = resolve_skill_path(ecosystem, "gitlab-mr-review")

    # owner_check
    if jira_path is None:
        results.append(("owner_check", check(False, "jira skill not found in ecosystem")))
    else:
        skill_md = jira_path / "SKILL.md"
        found, err = file_contains(skill_md, "JIRA_CALLER")
        if found:
            results.append(("owner_check", check(True, "JIRA_CALLER documented in jira SKILL.md")))
        else:
            results.append(("owner_check", check(False, err or "JIRA_CALLER not found in jira SKILL.md")))

    # caller_dispatch
    if dispatch_path is None:
        results.append(("caller_dispatch", check(False, "dispatch skill not found in ecosystem")))
    else:
        skill_md = dispatch_path / "SKILL.md"
        found, err = file_contains(skill_md, "JIRA_CALLER=dispatch")
        if found:
            results.append(("caller_dispatch", check(True, "JIRA_CALLER=dispatch found in dispatch SKILL.md")))
        else:
            results.append(("caller_dispatch", check(False, err or "JIRA_CALLER=dispatch not found in dispatch SKILL.md")))

    # caller_mr_review
    if mr_review_path is None:
        results.append(("caller_mr_review", check(False, "gitlab-mr-review skill not found in ecosystem")))
    else:
        skill_md = mr_review_path / "SKILL.md"
        found, err = file_contains(skill_md, "JIRA_CALLER=gitlab-mr-review")
        if found:
            results.append(("caller_mr_review", check(True, "JIRA_CALLER=gitlab-mr-review found in mr-review SKILL.md")))
        else:
            results.append(("caller_mr_review", check(False, err or "JIRA_CALLER=gitlab-mr-review not found in mr-review SKILL.md")))

    # error_schema
    if jira_path is None:
        results.append(("error_schema", check(False, "jira skill not found in ecosystem")))
    else:
        skill_md = jira_path / "SKILL.md"
        found, err = file_contains(skill_md, "WRITE_BLOCKED_CROSS_SKILL")
        if found:
            results.append(("error_schema", check(True, "WRITE_BLOCKED_CROSS_SKILL error format documented")))
        else:
            results.append(("error_schema", check(False, err or "WRITE_BLOCKED_CROSS_SKILL not found in jira SKILL.md")))

    return results


def validate_review_md_frontmatter(registry, ecosystem, verbose):
    contract = registry["contracts"]["review_md_frontmatter"]
    registry_fields = contract["immutable_fields"]
    results = []

    mr_review_path = resolve_skill_path(ecosystem, "gitlab-mr-review")
    dispatch_path = resolve_skill_path(ecosystem, "dispatch")

    # producer_fields
    if mr_review_path is None:
        results.append(("producer_fields", check(False, "gitlab-mr-review skill not found in ecosystem")))
        results.append(("field_match", check(False, "skipped — producer_fields failed")))
    else:
        writer_path = mr_review_path / contract["validation"]["producer_file"]
        if not writer_path.exists():
            results.append(("producer_fields", check(False, f"{writer_path} not found")))
            results.append(("field_match", check(False, "skipped — producer_fields failed")))
        else:
            try:
                code_fields = load_frontmatter_fields(writer_path)
                count = len(code_fields)
                registry_set = set(registry_fields)
                code_set = set(code_fields)

                if registry_set == code_set:
                    results.append(("producer_fields", check(True, f"{count} fields match between review_writer.py and registry")))
                    results.append(("field_match", check(True, "No drift detected")))
                else:
                    results.append(("producer_fields", check(False, f"Field count mismatch: registry={len(registry_set)}, code={len(code_set)}")))
                    in_code_not_registry = code_set - registry_set
                    in_registry_not_code = registry_set - code_set
                    drift_parts = []
                    if in_code_not_registry:
                        drift_parts.append(f"in code but not registry: {sorted(in_code_not_registry)}")
                    if in_registry_not_code:
                        drift_parts.append(f"in registry but not code: {sorted(in_registry_not_code)}")
                    results.append(("field_match", check(False, "Drift: " + "; ".join(drift_parts))))
            except Exception as e:
                results.append(("producer_fields", check(False, f"Failed to import review_writer.py: {e}")))
                results.append(("field_match", check(False, "skipped — producer_fields failed")))

    # consumer_reference
    if dispatch_path is None:
        results.append(("consumer_reference", check(False, "dispatch skill not found in ecosystem")))
    else:
        skill_md = dispatch_path / "SKILL.md"
        found, err = file_contains(skill_md, "frontmatter")
        if found:
            results.append(("consumer_reference", check(True, "Dispatch SKILL.md references frontmatter")))
        else:
            results.append(("consumer_reference", check(False, err or "frontmatter not found in dispatch SKILL.md")))

    return results


def validate_artifact_paths(registry, ecosystem, verbose):
    contract = registry["contracts"]["artifact_paths"]
    results = []

    checks = [
        ("review_base_dir", contract["review_md"]["base_dir"], "~/.zsh/review/"),
        ("jira_export_dir", contract["jira_export"]["base_dir"], "~/.zsh/jira/exports/"),
        ("dispatch_state_dir", contract["dispatch_state"]["base_dir"], "~/.zsh/dispatch/"),
    ]

    for name, raw_path, display in checks:
        expanded = Path(os.path.expanduser(raw_path))
        if expanded.is_dir():
            results.append((name, check(True, f"{display} exists")))
        else:
            results.append((name, check(False, f"{display} does not exist (looked at {expanded})")))

    return results


def run_validation(registry_path, ecosystem_path, verbose):
    registry = load_yaml(registry_path)
    ecosystem = load_yaml(ecosystem_path)

    contracts = []

    jira_checks = validate_jira_caller(registry, ecosystem, verbose)
    contracts.append(("jira_caller", jira_checks))

    frontmatter_checks = validate_review_md_frontmatter(registry, ecosystem, verbose)
    contracts.append(("review_md_frontmatter", frontmatter_checks))

    artifact_checks = validate_artifact_paths(registry, ecosystem, verbose)
    contracts.append(("artifact_paths", artifact_checks))

    return contracts


def format_text(contracts):
    lines = ["Contract Validation Report", "\u2550" * 26, ""]

    total = 0
    passed = 0

    for contract_id, checks in contracts:
        lines.append(contract_id)
        for check_name, result in checks:
            total += 1
            tag = "PASS" if result["ok"] else "FAIL"
            if result["ok"]:
                passed += 1
            lines.append(f"  [{tag}] {check_name} \u2014 {result['detail']}")
        lines.append("")

    lines.append("\u2550" * 26)
    lines.append(f"Overall: {passed}/{total} PASS")
    return "\n".join(lines)


def format_json(contracts):
    total = 0
    passed = 0
    failed = 0
    output = []

    for contract_id, checks in contracts:
        all_ok = all(r["ok"] for _, r in checks)
        entry = {
            "id": contract_id,
            "status": "VALID" if all_ok else "INVALID",
            "checks": [],
        }
        for check_name, result in checks:
            total += 1
            if result["ok"]:
                passed += 1
            else:
                failed += 1
            entry["checks"].append({
                "check": check_name,
                "ok": result["ok"],
                "detail": result["detail"],
            })
        output.append(entry)

    return json.dumps({
        "contracts": output,
        "all_valid": failed == 0,
        "total_checks": total,
        "passed": passed,
        "failed": failed,
    }, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Validate integration contracts")
    parser.add_argument("--registry", default=str(SKILL_DIR / "contracts" / "registry.yaml"))
    parser.add_argument("--ecosystem", default=str(SKILL_DIR / "config" / "ecosystem.yaml"))
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = Path(args.registry)
    ecosystem_path = Path(args.ecosystem)

    if not registry_path.exists():
        print(f"Registry not found: {registry_path}", file=sys.stderr)
        sys.exit(1)
    if not ecosystem_path.exists():
        print(f"Ecosystem config not found: {ecosystem_path}", file=sys.stderr)
        sys.exit(1)

    contracts = run_validation(registry_path, ecosystem_path, args.verbose)

    if args.json_output:
        print(format_json(contracts))
    else:
        print(format_text(contracts))

    all_ok = all(r["ok"] for _, checks in contracts for _, r in checks)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
