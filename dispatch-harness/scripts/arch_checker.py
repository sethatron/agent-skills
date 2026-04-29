#!/usr/bin/env python3
"""Architecture constraint checker for the dispatch-harness skill."""

import argparse
import graphlib
import json
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SKILL_ROOT = Path.home() / "agent-skills"
ARCH_PATH = Path.home() / ".zsh" / "dispatch" / "contracts" / "architecture.yaml"
ECOSYSTEM_PATH = Path("/Users/sethallen/agent-skills/dispatch-manager/config/ecosystem.yaml")


@dataclass
class Invocation:
    calling_skill: str
    called_skill: str
    source_file: str
    line_number: int
    pattern: str


@dataclass
class Violation:
    calling_skill: str
    called_skill: str
    source_file: str
    line_number: int
    violation_type: str


@dataclass
class ArchReport:
    invocations: list = field(default_factory=list)
    violations: list = field(default_factory=list)
    cycles: list = field(default_factory=list)
    depth_violations: list = field(default_factory=list)
    arch_loaded: bool = False

    @property
    def passed(self) -> bool:
        return not self.cycles and not self.depth_violations

    @property
    def has_warnings(self) -> bool:
        return bool(self.violations)


class ArchChecker:
    def __init__(self):
        self.arch = None
        self.skill_slugs = []
        self._slug_to_canonical = {}

    def load_architecture(self) -> dict:
        if not ARCH_PATH.exists():
            return {}
        with open(ARCH_PATH) as f:
            self.arch = yaml.safe_load(f)
        return self.arch

    def _load_skill_slugs(self) -> list[str]:
        if not ECOSYSTEM_PATH.exists():
            return []

        with open(ECOSYSTEM_PATH) as f:
            eco = yaml.safe_load(f)

        skills = eco.get("skills", {})
        slugs = []
        for slug, info in skills.items():
            slugs.append(slug)
            self._slug_to_canonical[slug] = slug
            for alias in info.get("aliases", []):
                slugs.append(alias)
                self._slug_to_canonical[alias] = slug

        self.skill_slugs = slugs
        return slugs

    def _resolve_slug(self, slug: str) -> str:
        return self._slug_to_canonical.get(slug, slug)

    def scan_skill_invocations(self, skill_dir: Path, skill_slug: str) -> list[Invocation]:
        invocations = []
        canonical_self = self._resolve_slug(skill_slug)

        targets = list(skill_dir.rglob("*.py"))
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            targets.append(skill_md)
        docs_dir = skill_dir / "docs"
        if docs_dir.is_dir():
            targets.extend(docs_dir.glob("*.md"))

        slug_pattern = re.compile(
            r'(?<![a-zA-Z0-9_/:.])/'
            r'(' + '|'.join(re.escape(s) for s in self.skill_slugs) + r')'
            r'(?:\s|$|[),\]"\'])',
        )

        claude_p_pattern = re.compile(
            r'claude\s+-p\s+.*?(' + '|'.join(re.escape(s) for s in self.skill_slugs) + r')'
        )

        subprocess_pattern = re.compile(
            r'subprocess\.\w+\(.*?(' + '|'.join(re.escape(s) for s in self.skill_slugs) + r')'
        )

        jira_caller_pattern = re.compile(r'JIRA_CALLER\s*=\s*(\w[\w-]*)')

        not_invoke_pattern = re.compile(
            r'(does\s+NOT\s+invoke|does\s+not\s+invoke|NOT\s+call|does\s+not\s+call)',
            re.IGNORECASE,
        )

        url_pattern = re.compile(r'https?://')

        md_doc_patterns = re.compile(
            r'(^\|.*\|$'          # table rows
            r'|^[-*]\s'           # unordered list items
            r'|^\d+\.\s'         # numbered list items
            r'|^\s*#'             # headings
            r'|consumed_by|produces|dependencies'  # config descriptions
            r'|called_by|calls\b'  # architecture descriptions
            r'|is the|does the|will the|should the'
            r'|relationship|integration|replaces|tracks'
            r'|currently|previously'
            r'|via\s+`'           # "via `/command`" descriptions
            r'|Register\s+with'   # registration descriptions
            r'|On\s+`?/'          # "On /dispatch task start" event descriptions
            r'|Final:'            # final step descriptions
            r')',
            re.IGNORECASE,
        )

        for fpath in targets:
            try:
                lines = fpath.read_text(errors="replace").splitlines()
            except OSError:
                continue

            is_md = fpath.suffix == ".md"
            in_code_block = False

            for i, line in enumerate(lines, start=1):
                stripped = line.strip()

                if is_md and stripped.startswith("```"):
                    in_code_block = not in_code_block
                    continue

                if not_invoke_pattern.search(stripped):
                    continue

                if is_md and not in_code_block:
                    if md_doc_patterns.search(stripped):
                        continue

                for m in slug_pattern.finditer(stripped):
                    matched_slug = m.group(1)
                    start = m.start()
                    prefix = stripped[:start]
                    if url_pattern.search(prefix):
                        continue
                    canonical = self._resolve_slug(matched_slug)
                    if canonical == canonical_self:
                        continue
                    invocations.append(Invocation(
                        calling_skill=skill_slug,
                        called_skill=canonical,
                        source_file=str(fpath),
                        line_number=i,
                        pattern=f"/{matched_slug}",
                    ))

                for m in claude_p_pattern.finditer(stripped):
                    matched_slug = m.group(1)
                    canonical = self._resolve_slug(matched_slug)
                    if canonical == canonical_self:
                        continue
                    invocations.append(Invocation(
                        calling_skill=skill_slug,
                        called_skill=canonical,
                        source_file=str(fpath),
                        line_number=i,
                        pattern=f"claude -p ...{matched_slug}",
                    ))

                for m in subprocess_pattern.finditer(stripped):
                    matched_slug = m.group(1)
                    canonical = self._resolve_slug(matched_slug)
                    if canonical == canonical_self:
                        continue
                    invocations.append(Invocation(
                        calling_skill=skill_slug,
                        called_skill=canonical,
                        source_file=str(fpath),
                        line_number=i,
                        pattern=f"subprocess...{matched_slug}",
                    ))

                for m in jira_caller_pattern.finditer(stripped):
                    caller_value = m.group(1)
                    if caller_value.lower() in ("operator", "unset"):
                        continue
                    canonical = self._resolve_slug("jira")
                    if canonical == canonical_self:
                        continue
                    invocations.append(Invocation(
                        calling_skill=skill_slug,
                        called_skill="jira",
                        source_file=str(fpath),
                        line_number=i,
                        pattern=f"JIRA_CALLER={caller_value}",
                    ))

        return invocations

    def scan_all_invocations(self) -> list[Invocation]:
        if not self.skill_slugs:
            self._load_skill_slugs()

        all_invocations = []
        for slug in set(self._slug_to_canonical.values()):
            skill_dir = SKILL_ROOT / slug
            if not skill_dir.is_dir():
                continue
            all_invocations.extend(self.scan_skill_invocations(skill_dir, slug))

        return all_invocations

    def check_declared(self, invocations: list, arch: dict) -> list[Violation]:
        if not arch:
            return []

        declared_calls = {}
        for entry in arch.get("dependency_order", []):
            slug = entry["slug"]
            declared_calls[slug] = set(entry.get("calls", []))

        violations = []
        for inv in invocations:
            caller = self._resolve_slug(inv.calling_skill)
            callee = self._resolve_slug(inv.called_skill)
            allowed = declared_calls.get(caller, set())
            if callee not in allowed:
                violations.append(Violation(
                    calling_skill=caller,
                    called_skill=callee,
                    source_file=inv.source_file,
                    line_number=inv.line_number,
                    violation_type="undeclared_call",
                ))

        return violations

    def check_cycles(self, arch: dict) -> list:
        if not arch:
            return []

        graph = {}
        for entry in arch.get("dependency_order", []):
            slug = entry["slug"]
            graph[slug] = set(entry.get("calls", []))

        try:
            ts = graphlib.TopologicalSorter(graph)
            ts.prepare()
            return []
        except graphlib.CycleError as e:
            return [str(e)]

    def check_depth(self, arch: dict) -> list[Violation]:
        if not arch:
            return []

        max_depth = 2
        for rule in arch.get("rules", []):
            if rule.get("id") == "max_call_depth":
                max_depth = rule.get("value", 2)
                break

        adj = defaultdict(set)
        for entry in arch.get("dependency_order", []):
            slug = entry["slug"]
            for callee in entry.get("calls", []):
                adj[slug].add(callee)

        violations = []
        all_nodes = {e["slug"] for e in arch.get("dependency_order", [])}

        for start in all_nodes:
            queue = deque()
            queue.append((start, 0, [start]))

            while queue:
                node, depth, path = queue.popleft()
                for neighbor in adj.get(node, []):
                    new_depth = depth + 1
                    new_path = path + [neighbor]
                    if new_depth > max_depth:
                        violations.append(Violation(
                            calling_skill=start,
                            called_skill=neighbor,
                            source_file="architecture.yaml",
                            line_number=0,
                            violation_type=f"depth_{new_depth}_exceeds_max_{max_depth} (path: {' -> '.join(new_path)})",
                        ))
                    else:
                        queue.append((neighbor, new_depth, new_path))

        return violations

    def run(self) -> ArchReport:
        report = ArchReport()

        self._load_skill_slugs()
        arch = self.load_architecture()
        report.arch_loaded = bool(arch)

        report.invocations = self.scan_all_invocations()

        if arch:
            report.violations = self.check_declared(report.invocations, arch)
            report.cycles = self.check_cycles(arch)
            report.depth_violations = self.check_depth(arch)

        return report


def _dedup_invocations(invocations: list[Invocation]) -> list[Invocation]:
    seen = set()
    result = []
    for inv in invocations:
        key = (inv.calling_skill, inv.called_skill, inv.source_file, inv.line_number)
        if key not in seen:
            seen.add(key)
            result.append(inv)
    return result


def format_plain(report: ArchReport, verbose: bool = False) -> str:
    lines = ["Architecture Check"]

    if report.arch_loaded:
        lines.append(f"  Loaded: architecture.yaml")
    else:
        lines.append("  Loaded: architecture.yaml NOT FOUND (scan-only mode)")

    deduped = _dedup_invocations(report.invocations)
    lines.append(f"  Invocations found: {len(deduped)}")
    lines.append(f"  Undeclared calls: {len(report.violations)}")
    lines.append(f"  Cycles: {len(report.cycles)}")
    lines.append(f"  Depth violations: {len(report.depth_violations)}")

    result = "PASS" if report.passed else "FAIL"
    lines.append(f"  RESULT: {result}")

    if verbose and deduped:
        lines.append("")
        lines.append("Invocations:")
        for inv in deduped:
            rel = inv.source_file.replace(str(SKILL_ROOT) + "/", "")
            lines.append(f"  {inv.calling_skill} -> {inv.called_skill}  [{rel}:{inv.line_number}] ({inv.pattern})")

    if verbose and report.violations:
        lines.append("")
        lines.append("Undeclared Calls:")
        for v in report.violations:
            rel = v.source_file.replace(str(SKILL_ROOT) + "/", "")
            lines.append(f"  {v.calling_skill} -> {v.called_skill}  [{rel}:{v.line_number}]")

    if verbose and report.cycles:
        lines.append("")
        lines.append("Cycles:")
        for c in report.cycles:
            lines.append(f"  {c}")

    if verbose and report.depth_violations:
        lines.append("")
        lines.append("Depth Violations:")
        for v in report.depth_violations:
            lines.append(f"  {v.violation_type}")

    return "\n".join(lines)


def format_json(report: ArchReport) -> str:
    deduped = _dedup_invocations(report.invocations)
    data = {
        "arch_loaded": report.arch_loaded,
        "invocations": [
            {
                "calling_skill": inv.calling_skill,
                "called_skill": inv.called_skill,
                "source_file": inv.source_file,
                "line_number": inv.line_number,
                "pattern": inv.pattern,
            }
            for inv in deduped
        ],
        "violations": [
            {
                "calling_skill": v.calling_skill,
                "called_skill": v.called_skill,
                "source_file": v.source_file,
                "line_number": v.line_number,
                "violation_type": v.violation_type,
            }
            for v in report.violations
        ],
        "cycles": report.cycles,
        "depth_violations": [
            {
                "calling_skill": v.calling_skill,
                "called_skill": v.called_skill,
                "violation_type": v.violation_type,
            }
            for v in report.depth_violations
        ],
        "result": "PASS" if report.passed else "FAIL",
    }
    return json.dumps(data, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Architecture constraint checker")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show detailed invocation list")
    args = parser.parse_args()

    checker = ArchChecker()
    report = checker.run()

    if args.json:
        print(format_json(report))
    else:
        print(format_plain(report, verbose=args.verbose))

    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
