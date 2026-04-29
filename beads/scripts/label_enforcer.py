#!/usr/bin/env python3
"""
Label taxonomy compliance checking.

Usage:
    python scripts/label_enforcer.py validate <labels...>
    python scripts/label_enforcer.py suggest --context '{"skill": "dispatch", "kind": "stub"}'
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
DISPATCH_DIR = Path.home() / ".zsh" / "dispatch"

TAXONOMY = {
    "scope": ["dispatch", "dispatch-manager", "dispatch-harness", "jira", "mr-review", "notebook",
              "beads", "ecosystem", "optimus", "auditor"],
    "layer": ["script", "skill-md", "config", "contracts", "agent", "workflow", "db", "hook"],
    "source": ["optimus", "audit", "operator", "scaffold", "entropy", "harness"],
    "kind": ["stub", "bug", "improvement", "refactor", "new-feature", "debt", "config", "docs"],
    "phase": ["stub", "in-design", "in-progress", "review", "complete"],
    "effort": ["xs", "small", "medium", "large"],
}

REQUIRED_NAMESPACES = ["scope", "kind", "source"]


@dataclass
class ValidationResult:
    valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class LabelEnforcer:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or SKILL_DIR / "config" / "beads.yaml"
        self._config = {}
        if self.config_path.exists():
            self._config = yaml.safe_load(self.config_path.read_text()) or {}

    def validate_labels(self, labels: list[str]) -> ValidationResult:
        errors = []
        warnings = []
        seen_namespaces = set()

        for label in labels:
            if ":" not in label:
                errors.append(f"Invalid format '{label}': must be namespace:value")
                continue

            ns, value = label.split(":", 1)
            if ns not in TAXONOMY:
                errors.append(f"Unknown namespace '{ns}' in '{label}'. Valid: {list(TAXONOMY.keys())}")
                continue

            if value not in TAXONOMY[ns]:
                errors.append(f"Unknown value '{value}' for namespace '{ns}'. Valid: {TAXONOMY[ns]}")
                continue

            seen_namespaces.add(ns)

        for req in REQUIRED_NAMESPACES:
            if req not in seen_namespaces:
                errors.append(f"Missing required namespace '{req}:'")

        is_stub = any(l == "kind:stub" for l in labels)
        if is_stub:
            for extra in ["layer", "phase"]:
                if extra not in seen_namespaces:
                    warnings.append(f"Stub issues should have '{extra}:' label")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_issue(self, issue: dict) -> list[str]:
        labels = issue.get("labels", [])
        if isinstance(labels, str):
            labels = [l.strip() for l in labels.split(",") if l.strip()]
        result = self.validate_labels(labels)
        return result.errors + [f"WARN: {w}" for w in result.warnings]

    def enforce_board(self) -> dict:
        try:
            result = subprocess.run(
                ["br", "list", "--format", "json", "-s", "open", "--limit", "0"],
                cwd=str(DISPATCH_DIR), capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return {"error": result.stderr}
            issues = json.loads(result.stdout)
        except Exception as e:
            return {"error": str(e)}

        violations = {}
        for issue in issues:
            issue_id = issue.get("id", "unknown")
            v = self.validate_issue(issue)
            if v:
                violations[issue_id] = v

        return {
            "checked": len(issues),
            "violations": violations,
            "violation_count": len(violations),
        }

    def suggest_labels(self, context: dict) -> list[str]:
        suggestions = []
        if "skill" in context:
            skill = context["skill"]
            if skill in TAXONOMY["scope"]:
                suggestions.append(f"scope:{skill}")
        if "kind" in context:
            kind = context["kind"]
            if kind in TAXONOMY["kind"]:
                suggestions.append(f"kind:{kind}")
        if "source" in context:
            source = context["source"]
            if source in TAXONOMY["source"]:
                suggestions.append(f"source:{source}")
        if not any(s.startswith("source:") for s in suggestions):
            suggestions.append("source:operator")
        if "layer" in context:
            layer = context["layer"]
            if layer in TAXONOMY["layer"]:
                suggestions.append(f"layer:{layer}")
        if "phase" in context:
            phase = context["phase"]
            if phase in TAXONOMY["phase"]:
                suggestions.append(f"phase:{phase}")
        if "effort" in context:
            effort = context["effort"]
            if effort in TAXONOMY["effort"]:
                suggestions.append(f"effort:{effort}")
        return suggestions


def main():
    parser = argparse.ArgumentParser(description="Label taxonomy enforcer")
    sub = parser.add_subparsers(dest="command")

    v = sub.add_parser("validate")
    v.add_argument("labels", nargs="+")

    s = sub.add_parser("suggest")
    s.add_argument("--context", required=True)

    sub.add_parser("enforce")

    args = parser.parse_args()

    if args.command == "validate":
        enforcer = LabelEnforcer()
        result = enforcer.validate_labels(args.labels)
        print(f"Valid: {result.valid}")
        for e in result.errors:
            print(f"  ERROR: {e}")
        for w in result.warnings:
            print(f"  WARN: {w}")
        sys.exit(0 if result.valid else 1)
    elif args.command == "suggest":
        enforcer = LabelEnforcer()
        ctx = json.loads(args.context)
        suggestions = enforcer.suggest_labels(ctx)
        for s in suggestions:
            print(f"  {s}")
    elif args.command == "enforce":
        enforcer = LabelEnforcer()
        result = enforcer.enforce_board()
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"Checked: {result['checked']} issues")
        print(f"Violations: {result['violation_count']}")
        for issue_id, vs in result.get("violations", {}).items():
            print(f"  {issue_id}:")
            for v in vs:
                print(f"    - {v}")
        sys.exit(1 if result['violation_count'] > 0 else 0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
