#!/usr/bin/env python3
"""
Guided skill creation workflow for dispatch-compatible skills.

Usage (CLI):
    python scripts/skill_author.py new
    python scripts/skill_author.py from-spec <spec-path>

Usage (module):
    from skill_author import SkillAuthor
    author = SkillAuthor()
    spec = author.run_interview()
    author.generate_skill(spec)
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
AGENT_SKILLS_ROOT = SKILL_DIR.parent
DSI_TYPES = {"A": "Workflow Step", "B": "On-Demand Managed", "C": "Hybrid (A+B)"}

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from ecosystem_map import EcosystemMap
from changelog_writer import ChangelogWriter
from version_manager import VersionManager


@dataclass
class SkillSpec:
    slug: str = ""
    name: str = ""
    purpose: str = ""
    description: str = ""
    dsi_type: str = "B"
    invokes_jira: bool = False
    invokes_mr_review: bool = False
    invokes_dispatch: bool = False
    git_write_ops: bool = False
    artifact_filename_pattern: str = ""
    artifact_dir_pattern: str = ""
    custom_frontmatter_fields: List[Dict] = field(default_factory=list)
    write_operations: List[str] = field(default_factory=list)
    prohibited_operations: List[str] = field(default_factory=list)
    external_apis: List[Dict] = field(default_factory=list)
    primary_command: str = ""
    trigger_phrases: List[str] = field(default_factory=list)
    pushy_description: bool = True


class SkillAuthor:

    def __init__(self, ecosystem_path: Optional[Path] = None):
        self.ecosystem_path = ecosystem_path or SKILL_DIR / "config" / "ecosystem.yaml"
        self._eco = EcosystemMap(ecosystem_path=self.ecosystem_path)
        self._cw = ChangelogWriter()
        self._vm = VersionManager()

    def run_interview(self) -> SkillSpec:
        spec = SkillSpec()
        for phase in [self._phase_identity, self._phase_integration_type,
                      self._phase_dependencies, self._phase_artifact_contract,
                      self._phase_guardrails, self._phase_triggers]:
            spec = phase(spec)
        return spec

    def _phase_identity(self, spec: SkillSpec) -> SkillSpec:
        print("\n=== Phase 1: Identity ===")
        print("[SKILL-AUTHOR] Provide the following:")
        print("  - slug: lowercase-hyphenated identifier (e.g., my-tool)")
        print("  - name: Human-readable name")
        print("  - purpose: One-line purpose statement")
        print("  - description: Detailed description for SKILL.md")
        return spec

    def _phase_integration_type(self, spec: SkillSpec) -> SkillSpec:
        print("\n=== Phase 2: Integration Type ===")
        for code, desc in DSI_TYPES.items():
            print(f"  {code}: {desc}")
        print("  A = Satisfies a dispatch workflow step (produces artifacts, has step-snippet)")
        print("  B = On-demand skill (invoked by operator or other skills)")
        print("  C = Both A and B")
        print("[SKILL-AUTHOR] Select DSI type (A/B/C):")
        return spec

    def _phase_dependencies(self, spec: SkillSpec) -> SkillSpec:
        print("\n=== Phase 3: Dependencies ===")
        all_skills = self._eco._all_skills()
        print(f"  Available skills: {', '.join(all_skills.keys())}")
        print("[SKILL-AUTHOR] Which skills does this one invoke?")
        print("  - invokes_jira? (y/n)")
        print("  - invokes_mr_review? (y/n)")
        print("  - invokes_dispatch? (y/n)")
        print("  - Requires git write operations? (y/n)")
        return spec

    def _phase_artifact_contract(self, spec: SkillSpec) -> SkillSpec:
        if spec.dsi_type not in ("A", "C"):
            return spec
        print("\n=== Phase 4: Artifact Contract (TYPE A/C) ===")
        print("[SKILL-AUTHOR] Define output artifacts:")
        print("  - artifact_filename_pattern: e.g., 'report_{date}.md'")
        print("  - artifact_dir_pattern: e.g., '~/.zsh/{skill}/{YYYY}/{MM}/{DD}/'")
        print("  - Custom frontmatter fields (name, type, required):")
        return spec

    def _phase_guardrails(self, spec: SkillSpec) -> SkillSpec:
        print("\n=== Phase 5: Guardrails ===")
        print("[SKILL-AUTHOR] Define safety boundaries:")
        print("  - Write operations this skill performs:")
        print("  - Operations that are PROHIBITED:")
        print("  - External APIs accessed (name, purpose, auth method):")
        return spec

    def _phase_triggers(self, spec: SkillSpec) -> SkillSpec:
        print("\n=== Phase 6: Triggers ===")
        print("[SKILL-AUTHOR] How is this skill invoked?")
        print("  - Primary command: e.g., '/my-tool review'")
        print("  - Trigger phrases: natural language patterns")
        print("  - Pushy description? (skill auto-activates on matching input)")
        return spec

    def build_spec(self, spec: SkillSpec) -> str:
        skill_dir = AGENT_SKILLS_ROOT / spec.slug
        skill_dir.mkdir(parents=True, exist_ok=True)

        deps = []
        if spec.invokes_jira:
            deps.append("jira")
        if spec.invokes_mr_review:
            deps.append("gitlab-mr-review")
        if spec.invokes_dispatch:
            deps.append("dispatch")

        prohibited = list(spec.prohibited_operations)
        if not spec.git_write_ops:
            prohibited.extend(["git add", "git commit", "git push"])

        text = f"""# Skill Specification: {spec.name}

- **Slug:** {spec.slug}
- **DSI Type:** {spec.dsi_type} ({DSI_TYPES.get(spec.dsi_type, '')})
- **Purpose:** {spec.purpose}
- **Dependencies:** {', '.join(deps) or 'none'}
- **Git Write Ops:** {'yes' if spec.git_write_ops else 'no'}
- **Primary Command:** {spec.primary_command or f'/{spec.slug}'}

## Description
{spec.description}

## Artifacts
- Filename pattern: {spec.artifact_filename_pattern or 'N/A'}
- Directory pattern: {spec.artifact_dir_pattern or 'N/A'}

## Guardrails
### Prohibited Operations
{chr(10).join(f'- {p}' for p in prohibited) or '- None specified'}

### Write Operations
{chr(10).join(f'- {w}' for w in spec.write_operations) or '- None specified'}
"""
        spec_path = skill_dir / "spec.md"
        spec_path.write_text(text)
        return text

    def generate_skill(self, spec: SkillSpec) -> Path:
        skill_dir = AGENT_SKILLS_ROOT / spec.slug
        skill_dir.mkdir(parents=True, exist_ok=True)

        self._generate_skill_md(skill_dir, spec)
        self._generate_check_env(skill_dir, spec)
        self._generate_changelog(skill_dir, spec)
        (skill_dir / "scripts").mkdir(exist_ok=True)
        (skill_dir / "config").mkdir(exist_ok=True)

        if spec.dsi_type in ("A", "C"):
            self._generate_step_snippet(skill_dir, spec)
            (skill_dir / "references").mkdir(exist_ok=True)

        (skill_dir / "docs").mkdir(exist_ok=True)

        report = self.validate_generated(skill_dir, spec.dsi_type)
        self.register_skill(skill_dir, spec)
        self.write_changelogs(spec)

        return skill_dir

    def _generate_skill_md(self, skill_dir: Path, spec: SkillSpec) -> None:
        deps = []
        if spec.invokes_jira:
            deps.append("jira")
        if spec.invokes_mr_review:
            deps.append("gitlab-mr-review")
        if spec.invokes_dispatch:
            deps.append("dispatch")

        prohibited = list(spec.prohibited_operations)
        if not spec.git_write_ops:
            prohibited.extend(["git add", "git commit", "git push"])

        guardrails = "\n".join(f"  {p} — PROHIBITED" for p in prohibited) if prohibited else "  No specific prohibitions"

        content = f"""---
name: {spec.slug}
version: "1.0.0"
dsi_type: "{spec.dsi_type}"
description: >-
  {spec.description or spec.purpose}
---

# {spec.name}

{spec.purpose}

+{'─' * 70}+
| GUARDRAILS{' ' * 59}|
|{' ' * 72}|
{guardrails}
+{'─' * 70}+

## Scripts

| Script | Purpose | Implemented |
|--------|---------|-------------|
| check_env.py | Environment validation | Full |

## Idempotency

Read operations are idempotent. Write operations require confirmation.
"""
        (skill_dir / "SKILL.md").write_text(content)

    def _generate_check_env(self, skill_dir: Path, spec: SkillSpec) -> None:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        content = f"""#!/usr/bin/env python3
\"\"\"Environment validation for {spec.slug}.\"\"\"

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

def check_skill_md():
    path = SKILL_DIR / "SKILL.md"
    return path.exists(), "SKILL.md exists" if path.exists() else "SKILL.md missing"

def main():
    checks = [check_skill_md]
    all_ok = True
    for check in checks:
        ok, msg = check()
        status = "PASS" if ok else "FAIL"
        print(f"  [{{status}}] {{msg}}")
        if not ok:
            all_ok = False
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
"""
        (scripts_dir / "check_env.py").write_text(content)

    def _generate_changelog(self, skill_dir: Path, spec: SkillSpec) -> None:
        content = f"# Changelog\n\n## [1.0.0] — {date.today().isoformat()}\n### Added\n- Initial skill creation\n"
        (skill_dir / "CHANGELOG.md").write_text(content)

    def _generate_step_snippet(self, skill_dir: Path, spec: SkillSpec) -> None:
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        snippet = {
            "id": spec.slug.replace("-", "_"),
            "name": spec.name,
            "skill": f"/{spec.slug}",
            "description": spec.purpose,
            "on_blocker": "log_and_continue",
            "timeout_minutes": 5,
            "tags": [spec.slug],
            "enabled": True,
        }
        (refs_dir / "step-snippet.yaml").write_text(
            yaml.dump([snippet], default_flow_style=False, sort_keys=False))

    def validate_generated(self, skill_path: Path, dsi_type: str = "B") -> dict:
        try:
            from dsi_validator import run_validation
            return run_validation(str(skill_path), dsi_type)
        except (ImportError, Exception) as e:
            return {"ok": False, "error": str(e)}

    def register_skill(self, skill_path: Path, spec: SkillSpec) -> None:
        deps = []
        if spec.invokes_jira:
            deps.append("jira")
        if spec.invokes_mr_review:
            deps.append("gitlab-mr-review")
        if spec.invokes_dispatch:
            deps.append("dispatch")

        entry = {
            "path": str(skill_path),
            "symlink": f"~/.claude/skills/{spec.slug}",
            "dsi_type": spec.dsi_type,
            "dependencies": deps,
            "produces": [],
            "consumed_by": [],
        }
        try:
            self._eco.add_skill(spec.slug, entry)
        except ValueError as e:
            print(f"  [WARN] Registration: {e}")

        self.create_symlink(spec.slug, skill_path)

    def create_symlink(self, slug: str, skill_path: Path) -> None:
        target = Path.home() / ".claude" / "skills" / slug
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(skill_path)

    def offer_workflow_integration(self, spec: SkillSpec) -> None:
        if spec.dsi_type not in ("A", "C"):
            return
        snippet_path = AGENT_SKILLS_ROOT / spec.slug / "references" / "step-snippet.yaml"
        if snippet_path.exists():
            print(f"\n[SKILL-AUTHOR] Workflow step snippet at: {snippet_path}")
            print(snippet_path.read_text())
            print("[SKILL-AUTHOR] Add to workflow.yaml? (y/n)")

    def write_changelogs(self, spec: SkillSpec) -> None:
        try:
            manager_version = self._vm.read_version("dispatch-manager") or "1.0.0"
            self._cw.write_entry("dispatch-manager", manager_version, "Added",
                                 f"Registered new skill: {spec.slug}")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Dispatch-compatible skill authoring")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("new", help="Start guided skill creation interview")

    p_spec = sub.add_parser("from-spec", help="Generate skill from existing spec file")
    p_spec.add_argument("spec_path", help="Path to spec.md")

    args = parser.parse_args()
    author = SkillAuthor()

    if args.command == "new":
        spec = author.run_interview()
        author.build_spec(spec)
        path = author.generate_skill(spec)
        author.offer_workflow_integration(spec)
        print(f"\nSkill generated at: {path}")
    elif args.command == "from-spec":
        spec_content = Path(args.spec_path).read_text()
        spec = SkillSpec()
        for line in spec_content.splitlines():
            m = re.match(r'- \*\*Slug:\*\*\s*(.+)', line)
            if m:
                spec.slug = m.group(1).strip()
            m = re.match(r'- \*\*DSI Type:\*\*\s*(\w)', line)
            if m:
                spec.dsi_type = m.group(1).strip()
            m = re.match(r'- \*\*Purpose:\*\*\s*(.+)', line)
            if m:
                spec.purpose = m.group(1).strip()
        if spec.slug:
            spec.name = spec.slug.replace("-", " ").title()
            path = author.generate_skill(spec)
            print(f"Skill generated at: {path}")
        else:
            print("Could not parse slug from spec file", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
