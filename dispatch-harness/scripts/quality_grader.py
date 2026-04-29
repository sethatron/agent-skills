#!/usr/bin/env python3
"""Quality grader for dispatch framework skills."""

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

GRADES_PATH = Path.home() / ".zsh" / "dispatch" / "harness" / "quality-grades.yaml"
HISTORY_PATH = Path.home() / ".zsh" / "dispatch" / "harness" / "grade-history.yaml"
ECOSYSTEM_PATH = Path("/Users/sethallen/agent-skills/dispatch-manager/config/ecosystem.yaml")
REGISTRY_PATH = Path("/Users/sethallen/agent-skills/dispatch-manager/contracts/registry.yaml")
DISPATCH_DIR = Path.home() / ".zsh" / "dispatch"
SKILL_MD_MAX_LINES = 200
DOCS_REQUIRED = ["architecture.md", "integration.md", "failure-modes.md", "quality.md"]

GRADE_ORDER = ["A", "B", "C", "D", "F"]
STATE_STORE_PATH = Path("/Users/sethallen/agent-skills/dispatch/scripts")


def _get_store():
    if str(STATE_STORE_PATH) not in sys.path:
        sys.path.insert(0, str(STATE_STORE_PATH))
    from state_store import StateStore
    store = StateStore()
    store.schema_init()
    return store


def _is_stub_body(body: list) -> bool:
    stmts = body
    if not stmts:
        return True
    if (len(stmts) == 1 and isinstance(stmts[0], ast.Expr)
        and isinstance(stmts[0].value, (ast.Constant, ast.JoinedStr))
        and isinstance(getattr(stmts[0].value, "value", None), str)):
        return True
    if len(stmts) == 2:
        first, second = stmts
        if (isinstance(first, ast.Expr) and isinstance(first.value, (ast.Constant, ast.JoinedStr))
            and isinstance(getattr(first.value, "value", None), str)):
            if _is_stub_body([second]):
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


def _get_public_functions(tree: ast.Module) -> list:
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                funcs.append(node)
    return funcs


def _has_docstring(func_node) -> bool:
    if not func_node.body:
        return False
    first = func_node.body[0]
    return (isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str))


def _has_return_annotation(func_node) -> bool:
    return func_node.returns is not None


@dataclass
class SkillGrade:
    slug: str
    overall: str
    components: dict
    beads_issues: list = field(default_factory=list)


@dataclass
class GradeChange:
    slug: str
    component: str
    old_grade: str
    new_grade: str
    direction: str


class QualityGrader:
    def __init__(self):
        self.ecosystem = self._load_ecosystem()
        self.registry = self._load_registry()

    def _load_ecosystem(self) -> dict:
        if not ECOSYSTEM_PATH.exists():
            return {}
        with open(ECOSYSTEM_PATH) as f:
            data = yaml.safe_load(f) or {}
        return data.get("skills", {})

    def _load_registry(self) -> dict:
        if not REGISTRY_PATH.exists():
            return {}
        with open(REGISTRY_PATH) as f:
            data = yaml.safe_load(f) or {}
        return data.get("contracts", {})

    def grade_script(self, path: Path) -> str:
        if not path.exists():
            return "F"
        try:
            source = path.read_text()
            tree = ast.parse(source)
        except SyntaxError:
            return "F"

        public_funcs = _get_public_functions(tree)
        if not public_funcs:
            return "B"

        stub_count = sum(1 for f in public_funcs if _is_stub_body(f.body))
        impl_count = len(public_funcs) - stub_count

        if stub_count == len(public_funcs):
            return "D"
        if stub_count > 0:
            return "C"

        all_docstrings = all(_has_docstring(f) for f in public_funcs)
        all_annotations = all(_has_return_annotation(f) for f in public_funcs)

        if all_docstrings and all_annotations:
            return "A"
        return "B"

    def grade_skill_md(self, skill_dir: Path) -> str:
        md_path = skill_dir / "SKILL.md"
        if not md_path.exists():
            return "F"
        try:
            content = md_path.read_text()
        except Exception:
            return "F"

        lines = content.splitlines()
        line_count = len(lines)

        has_frontmatter = False
        has_version = False
        has_docs_key = False
        has_guardrails = False
        docs_paths = []

        if lines and lines[0].strip() == "---":
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_idx = i
                    break
            if end_idx:
                has_frontmatter = True
                try:
                    fm = yaml.safe_load("\n".join(lines[1:end_idx]))
                    if isinstance(fm, dict):
                        has_version = "version" in fm
                        if "docs" in fm:
                            has_docs_key = True
                            docs_val = fm["docs"]
                            if isinstance(docs_val, list):
                                docs_paths = docs_val
                            elif isinstance(docs_val, dict):
                                docs_paths = list(docs_val.values())
                except Exception:
                    pass

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("┌") or stripped.startswith("+---"):
                has_guardrails = True
                break

        all_docs_resolve = False
        if docs_paths:
            all_docs_resolve = all(
                (skill_dir / p).exists() for p in docs_paths if isinstance(p, str)
            )

        if (has_docs_key and line_count <= SKILL_MD_MAX_LINES
                and all_docs_resolve and has_guardrails and has_version):
            return "A"

        if line_count <= SKILL_MD_MAX_LINES and has_guardrails and has_version:
            return "B"

        if line_count > SKILL_MD_MAX_LINES or not has_guardrails:
            return "C"

        return "C"

    def grade_docs_coverage(self, skill_dir: Path) -> str:
        docs_dir = skill_dir / "docs"
        if not docs_dir.exists() or not docs_dir.is_dir():
            return "F"

        present = 0
        for doc in DOCS_REQUIRED:
            p = docs_dir / doc
            if p.exists() and p.stat().st_size > 0:
                present += 1

        if present == 0:
            return "F"
        if present <= 2:
            return "C"
        if present == 3:
            return "B"
        return "A"

    def grade_contracts(self, slug: str) -> str:
        if slug not in self.ecosystem:
            return "F"

        in_registry = False
        for contract in self.registry.values():
            producers = []
            consumers = []
            if isinstance(contract, dict):
                p = contract.get("producer") or contract.get("producers", [])
                c = contract.get("consumers", [])
                if isinstance(p, str):
                    producers = [p]
                elif isinstance(p, list):
                    producers = p
                if isinstance(c, str):
                    consumers = [c]
                elif isinstance(c, list):
                    consumers = c
                known_callers = contract.get("known_callers", [])
                for kc in known_callers:
                    if isinstance(kc, dict) and kc.get("skill") == slug:
                        in_registry = True
                        break
            if slug in producers or slug in consumers:
                in_registry = True
                break

        if in_registry:
            return "A"
        return "B"

    def compute_overall(self, components: dict) -> str:
        grades = list(components.values())
        if not grades:
            return "F"

        has_f = "F" in grades

        counts = Counter(grades)
        modal_grade = max(counts, key=lambda g: (counts[g], -GRADE_ORDER.index(g)))

        if has_f and GRADE_ORDER.index(modal_grade) < GRADE_ORDER.index("C"):
            return "C"
        return modal_grade

    def grade_skill(self, slug: str) -> SkillGrade:
        skill_info = self.ecosystem.get(slug, {})
        skill_path_str = skill_info.get("path", "")
        if not skill_path_str:
            return SkillGrade(slug=slug, overall="F", components={"ecosystem": "F"})

        skill_dir = Path(skill_path_str).expanduser()
        components = {}

        components["skill_md"] = self.grade_skill_md(skill_dir)
        components["docs_coverage"] = self.grade_docs_coverage(skill_dir)

        check_env = skill_dir / "scripts" / "check_env.py"
        if check_env.exists():
            components["check_env_py"] = self.grade_script(check_env)

        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for py_file in sorted(scripts_dir.glob("*.py")):
                if py_file.name.startswith("__"):
                    continue
                if py_file.name == "check_env.py":
                    continue
                key = py_file.stem + "_py"
                components[key] = self.grade_script(py_file)

        components["contracts"] = self.grade_contracts(slug)

        overall = self.compute_overall(components)
        return SkillGrade(slug=slug, overall=overall, components=components)

    def grade_all_skills(self) -> dict[str, SkillGrade]:
        results = {}
        for slug in self.ecosystem:
            results[slug] = self.grade_skill(slug)
        return results

    def detect_changes(self, old_grades: dict, new_grades: dict[str, SkillGrade]) -> list[GradeChange]:
        changes = []
        old_skills = old_grades.get("skills", {})
        for slug, sg in new_grades.items():
            old_skill = old_skills.get(slug, {})
            old_components = old_skill.get("components", {})
            for comp, new_g in sg.components.items():
                old_g = old_components.get(comp)
                if old_g and old_g != new_g:
                    old_idx = GRADE_ORDER.index(old_g) if old_g in GRADE_ORDER else 4
                    new_idx = GRADE_ORDER.index(new_g) if new_g in GRADE_ORDER else 4
                    direction = "improvement" if new_idx < old_idx else "regression"
                    changes.append(GradeChange(
                        slug=slug, component=comp,
                        old_grade=old_g, new_grade=new_g,
                        direction=direction,
                    ))
        return changes

    def create_beads_issues(self, changes: list[GradeChange]) -> None:
        regressions = [c for c in changes if c.direction == "regression"]
        for change in regressions:
            title = f"Quality regression: {change.slug}/{change.component} {change.old_grade}->{change.new_grade}"
            try:
                search_result = subprocess.run(
                    ["br", "search", title],
                    capture_output=True, text=True, cwd=str(DISPATCH_DIR),
                )
                if search_result.returncode == 0 and title in search_result.stdout:
                    continue
            except FileNotFoundError:
                continue

            priority = "high" if change.new_grade in ("D", "F") else "medium"
            labels = "quality-regression,dispatch-harness"
            try:
                subprocess.run(
                    ["br", "create", title, "-t", "bug", "-p", priority, "-l", labels],
                    cwd=str(DISPATCH_DIR), capture_output=True, text=True,
                )
            except FileNotFoundError:
                pass

    def update_grade_history(self, grades: dict[str, SkillGrade]) -> None:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        history = {}
        if HISTORY_PATH.exists():
            with open(HISTORY_PATH) as f:
                history = yaml.safe_load(f) or {}

        entries = history.get("entries", [])
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skills": {},
        }
        for slug, sg in grades.items():
            snapshot["skills"][slug] = {
                "overall": sg.overall,
                "components": dict(sg.components),
            }
        entries.append(snapshot)

        if len(entries) > 100:
            entries = entries[-100:]

        history["entries"] = entries
        with open(HISTORY_PATH, "w") as f:
            yaml.dump(history, f, default_flow_style=False, sort_keys=False)

    def write_grades(self, grades: dict[str, SkillGrade]) -> Path:
        GRADES_PATH.parent.mkdir(parents=True, exist_ok=True)

        old_grades = {}
        if GRADES_PATH.exists():
            with open(GRADES_PATH) as f:
                old_grades = yaml.safe_load(f) or {}

        changes = self.detect_changes(old_grades, grades)
        self.create_beads_issues(changes)
        self.update_grade_history(grades)

        try:
            store = _get_store()
            for slug, sg in grades.items():
                for comp_name, grade in sg.components.items():
                    store.upsert_grade(slug, comp_name, grade)

                prev_grade = store.get_previous_overall_grade(slug)
                if prev_grade:
                    prev_idx = GRADE_ORDER.index(prev_grade) if prev_grade in GRADE_ORDER else 4
                    new_idx = GRADE_ORDER.index(sg.overall) if sg.overall in GRADE_ORDER else 4
                    if new_idx < prev_idx:
                        trend = "improvement"
                    elif new_idx > prev_idx:
                        trend = "regression"
                    else:
                        trend = "stable"
                else:
                    trend = "stable"

                store.append_grade_history(slug, sg.overall, sg.components, trend)
                store.emit_event("grade_evaluated", "dispatch-harness", {
                    "skill_slug": slug,
                    "overall_grade": sg.overall,
                    "trend": trend,
                    "prev_grade": prev_grade,
                    "components": dict(sg.components),
                })

            store.export_quality_grades()
            store.export_grade_history()
            store.close()
        except Exception:
            pass

        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": "dispatch-harness v1.0.0",
            "skills": {},
        }
        for slug, sg in grades.items():
            trend = None
            for c in changes:
                if c.slug == slug:
                    trend = c.direction
                    break
            output["skills"][slug] = {
                "overall": sg.overall,
                "components": dict(sg.components),
                "trend": trend,
                "beads_issues": sg.beads_issues,
            }

        with open(GRADES_PATH, "w") as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False)

        return GRADES_PATH


def _print_table(grades: dict[str, SkillGrade], verbose: bool = False):
    all_components = set()
    for sg in grades.values():
        all_components.update(sg.components.keys())
    comp_list = sorted(all_components)

    headers = ["Skill", "Overall"] + comp_list
    col_widths = [max(len(h), 12) for h in headers]

    for i, slug in enumerate(grades):
        col_widths[0] = max(col_widths[0], len(slug))

    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "  ".join("-" * col_widths[i] for i in range(len(headers)))

    print(header_line)
    print(separator)

    for slug in sorted(grades):
        sg = grades[slug]
        row = [slug, sg.overall]
        for comp in comp_list:
            row.append(sg.components.get(comp, "-"))
        line = "  ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        print(line)


def main():
    parser = argparse.ArgumentParser(description="Quality grader for dispatch skills")
    parser.add_argument("--skill", type=str, help="Grade a single skill by slug")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    grader = QualityGrader()

    if args.skill:
        grades = {args.skill: grader.grade_skill(args.skill)}
    else:
        grades = grader.grade_all_skills()

    path = grader.write_grades(grades)

    if args.json:
        out = {}
        for slug, sg in grades.items():
            out[slug] = {
                "overall": sg.overall,
                "components": sg.components,
                "beads_issues": sg.beads_issues,
            }
        print(json.dumps(out, indent=2))
    else:
        _print_table(grades, verbose=args.verbose)
        print(f"\nGrades written to {path}")


if __name__ == "__main__":
    main()
