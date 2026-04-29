#!/usr/bin/env python3
"""
Dispatch ecosystem scanner. Produces a structured ScanReport of stubs,
optimus findings, workflow steps, and discovered skills.

Usage:
    python scripts/board_scanner.py [--json] [--verbose]
"""

import argparse
import ast
import json
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

AGENT_SKILLS_ROOT = Path("/Users/sethallen/agent-skills")
DISPATCH_DIR = Path.home() / ".zsh" / "dispatch"
OPTIMUS_DIR = DISPATCH_DIR / "optimus"
WORKFLOW_PATH = DISPATCH_DIR / "workflow.yaml"
BEADS_CONFIG = AGENT_SKILLS_ROOT / "beads" / "config" / "beads.yaml"

KNOWN_SKILL_DIRS = [
    "dispatch", "dispatch-manager", "dispatch-notebook",
    "gitlab-mr-review", "jira", "beads",
]

PRIORITY_MAP = {
    "dispatch_runner.py": 0,
    "state_store.py": 1,
    "slack_notifier.py": 1,
    "bottleneck_detector.py": 1,
}

EPIC_MAP = {
    "dispatch": "[ENG] Workflow Engine",
    "dispatch-manager": "[ENG] Ecosystem Management",
    "notebook": "[ENG] Knowledge Layer",
    "dispatch-notebook": "[ENG] Knowledge Layer",
    "beads": "[ENG] Beads Integration",
    "ecosystem": "[ENG] Infrastructure",
}

EFFORT_MAP = {
    "dispatch_runner.py": "large",
    "state_store.py": "medium",
    "slack_notifier.py": "small",
    "bottleneck_detector.py": "medium",
    "skill_author.py": "large",
    "optimus_manager.py": "medium",
    "change_manager.py": "large",
    "backup_manager.py": "small",
    "changelog_writer.py": "small",
    "ecosystem_map.py": "small",
    "version_manager.py": "xs",
    "update_runner.py": "medium",
    "source_renderer.py": "small",
    "source_manager.py": "small",
    "query_runner.py": "small",
    "briefing_loader.py": "xs",
    "label_enforcer.py": "xs",
    "sync_runner.py": "xs",
}


@dataclass
class StubResult:
    script_name: str
    skill_slug: str
    function_names: list
    is_fully_stub: bool
    suggested_priority: int
    suggested_effort: str
    parent_epic_title: str


@dataclass
class FindingResult:
    finding_id: str
    title: str
    severity: str
    status: str
    affected_skill: str


@dataclass
class WorkflowStepResult:
    step_id: str
    name: str
    script_ref: str
    is_stub: bool


@dataclass
class ScanReport:
    stubs: list = field(default_factory=list)
    optimus_findings: list = field(default_factory=list)
    workflow_steps: list = field(default_factory=list)
    skills_found: list = field(default_factory=list)
    scan_timestamp: str = ""


class BoardScanner:

    def __init__(
        self,
        skills_root: Path = AGENT_SKILLS_ROOT,
        dispatch_dir: Path = DISPATCH_DIR,
    ):
        self.skills_root = skills_root
        self.dispatch_dir = dispatch_dir
        self.optimus_dir = dispatch_dir / "optimus"
        self.workflow_path = dispatch_dir / "workflow.yaml"
        self._workflow_script_refs: set = set()

    def scan(self) -> ScanReport:
        skills_found = self._discover_skills()
        stubs = []
        for slug in skills_found:
            skill_dir = (self.skills_root / slug).resolve()
            stubs.extend(self.scan_skill(skill_dir))

        self._workflow_script_refs = set()
        workflow_steps = self.scan_workflow_steps()

        for stub in stubs:
            if stub.script_name in self._workflow_script_refs and stub.suggested_priority > 1:
                stub.suggested_priority = 1

        return ScanReport(
            stubs=stubs,
            optimus_findings=self.scan_optimus_findings(),
            workflow_steps=workflow_steps,
            skills_found=skills_found,
            scan_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _discover_skills(self) -> list[str]:
        found = []
        for name in sorted(self.skills_root.iterdir()):
            resolved = name.resolve()
            if resolved.is_dir() and (resolved / "SKILL.md").exists():
                found.append(name.name)
        return found

    def scan_skill(self, skill_dir: Path) -> list[StubResult]:
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.is_dir():
            return []

        slug = skill_dir.name
        results = []

        for py_file in sorted(scripts_dir.glob("*.py")):
            if py_file.name == "check_env.py":
                continue

            stubbed_fns = self.detect_stubs(py_file)
            if not stubbed_fns:
                continue

            all_fns = self._all_function_names(py_file)
            public_fns = [f for f in all_fns if not f.startswith("_")]
            is_fully = len(stubbed_fns) >= len(public_fns) if public_fns else True

            results.append(StubResult(
                script_name=py_file.name,
                skill_slug=slug,
                function_names=stubbed_fns,
                is_fully_stub=is_fully,
                suggested_priority=PRIORITY_MAP.get(py_file.name, 2),
                suggested_effort=EFFORT_MAP.get(py_file.name, "medium"),
                parent_epic_title=EPIC_MAP.get(slug, "[ENG] Infrastructure"),
            ))

        return results

    def detect_stubs(self, script_path: Path) -> list[str]:
        try:
            source = script_path.read_text()
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return []

        stubbed = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if self._is_stub_body(node.body):
                stubbed.append(node.name)

        return stubbed

    def _is_stub_body(self, body: list[ast.stmt]) -> bool:
        stmts = body
        if not stmts:
            return True

        if (
            len(stmts) == 1
            and isinstance(stmts[0], ast.Expr)
            and isinstance(stmts[0].value, (ast.Constant, ast.JoinedStr))
            and isinstance(getattr(stmts[0].value, "value", None), str)
        ):
            return True

        if len(stmts) == 2:
            first, second = stmts
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, (ast.Constant, ast.JoinedStr))
                and isinstance(getattr(first.value, "value", None), str)
            ):
                if self._is_stub_body([second]):
                    return True

        effective = []
        for s in stmts:
            if isinstance(s, ast.Expr) and isinstance(s.value, (ast.Constant, ast.JoinedStr)):
                if isinstance(getattr(s.value, "value", None), str):
                    continue
            effective.append(s)

        if not effective:
            return True

        if len(effective) != 1:
            return False

        stmt = effective[0]

        if isinstance(stmt, ast.Pass):
            return True

        if isinstance(stmt, ast.Raise):
            exc = stmt.exc
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                if exc.func.id == "NotImplementedError":
                    return True
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                return True

        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if isinstance(stmt.value.value, str):
                val = stmt.value.value.strip().upper()
                if val in ("STUB", "TODO") or val.startswith("# STUB") or val.startswith("# TODO"):
                    return True

        return False

    def _all_function_names(self, script_path: Path) -> list[str]:
        try:
            source = script_path.read_text()
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return []

        return [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

    def scan_optimus_findings(self) -> list[FindingResult]:
        if not self.optimus_dir.is_dir():
            return []

        findings = []
        for f in sorted(self.optimus_dir.iterdir()):
            if f.suffix in (".yaml", ".yml"):
                findings.extend(self._parse_finding_yaml(f))
            elif f.suffix == ".md":
                finding = self._parse_finding_md(f)
                if finding:
                    findings.append(finding)

        return [f for f in findings if f.status in ("PENDING", "IN_PROGRESS")]

    def _parse_finding_yaml(self, path: Path) -> list[FindingResult]:
        if yaml is None:
            return []
        try:
            data = yaml.safe_load(path.read_text())
        except Exception:
            return []

        if not data:
            return []

        items = data if isinstance(data, list) else [data]
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append(FindingResult(
                finding_id=str(item.get("id", item.get("finding_id", path.stem))),
                title=str(item.get("title", item.get("name", path.stem))),
                severity=str(item.get("severity", "UNKNOWN")),
                status=str(item.get("status", "UNKNOWN")),
                affected_skill=str(item.get("affected_skill", item.get("skill", "unknown"))),
            ))
        return results

    def _parse_finding_md(self, path: Path) -> Optional[FindingResult]:
        try:
            text = path.read_text()
        except OSError:
            return None

        meta = {}
        lines = text.splitlines()
        in_frontmatter = False
        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                    continue
                else:
                    break
            if in_frontmatter and ":" in stripped:
                key, _, val = stripped.partition(":")
                meta[key.strip().lower()] = val.strip()

        if not meta:
            return None

        return FindingResult(
            finding_id=meta.get("id", meta.get("finding_id", path.stem)),
            title=meta.get("title", path.stem),
            severity=meta.get("severity", "UNKNOWN"),
            status=meta.get("status", "UNKNOWN"),
            affected_skill=meta.get("affected_skill", meta.get("skill", "unknown")),
        )

    def scan_workflow_steps(self) -> list[WorkflowStepResult]:
        if not self.workflow_path.exists() or yaml is None:
            return []

        try:
            data = yaml.safe_load(self.workflow_path.read_text())
        except Exception:
            return []

        if not data or "steps" not in data:
            return []

        all_stubs = self._collect_all_stub_names()
        results = []

        for step in data["steps"]:
            step_id = step.get("id", "")
            name = step.get("name", "")
            script_ref = step.get("runner", step.get("skill", ""))

            script_name = ""
            if "runner" in step:
                script_name = Path(step["runner"]).name
                self._workflow_script_refs.add(script_name)

            is_stub = script_name in all_stubs if script_name else False

            results.append(WorkflowStepResult(
                step_id=step_id,
                name=name,
                script_ref=script_ref,
                is_stub=is_stub,
            ))

        return results

    def _collect_all_stub_names(self) -> set[str]:
        names = set()
        for slug_dir in self.skills_root.iterdir():
            resolved = slug_dir.resolve()
            scripts_dir = resolved / "scripts"
            if not scripts_dir.is_dir():
                continue
            for py_file in scripts_dir.glob("*.py"):
                if py_file.name == "check_env.py":
                    continue
                if self.detect_stubs(py_file):
                    names.add(py_file.name)
        return names

    def get_current_board(self) -> list[dict]:
        try:
            result = subprocess.run(
                ["br", "list", "--format", "json", "--all", "--limit", "0"],
                cwd=str(self.dispatch_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return []
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError):
            return []


def _render_human(report: ScanReport, verbose: bool = False) -> str:
    lines = []
    lines.append(f"Dispatch Ecosystem Scan  ({report.scan_timestamp})")
    lines.append("=" * 60)

    lines.append(f"\nSkills discovered: {len(report.skills_found)}")
    for s in report.skills_found:
        lines.append(f"  - {s}")

    lines.append(f"\nStub scripts: {len(report.stubs)}")
    for stub in sorted(report.stubs, key=lambda s: s.suggested_priority):
        tag = "FULL STUB" if stub.is_fully_stub else "partial"
        lines.append(
            f"  P{stub.suggested_priority} [{stub.suggested_effort:>6}] "
            f"{stub.skill_slug}/{stub.script_name}  ({tag}, {len(stub.function_names)} fn)"
        )
        if verbose:
            for fn in stub.function_names:
                lines.append(f"           -> {fn}()")

    lines.append(f"\nOptimus findings (active): {len(report.optimus_findings)}")
    for f in report.optimus_findings:
        lines.append(f"  [{f.severity}] {f.finding_id}: {f.title}  (status={f.status})")

    lines.append(f"\nWorkflow steps: {len(report.workflow_steps)}")
    for ws in report.workflow_steps:
        stub_flag = " ** STUB **" if ws.is_stub else ""
        lines.append(f"  {ws.step_id}: {ws.name}  -> {ws.script_ref}{stub_flag}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Dispatch ecosystem board scanner")
    parser.add_argument("--json", action="store_true", help="Output full ScanReport as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show stubbed function names")
    args = parser.parse_args()

    scanner = BoardScanner()
    report = scanner.scan()

    if args.json:
        data = asdict(report)
        print(json.dumps(data, indent=2, default=str))
    else:
        print(_render_human(report, verbose=args.verbose))


if __name__ == "__main__":
    main()
