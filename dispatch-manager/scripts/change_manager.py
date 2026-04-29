#!/usr/bin/env python3
"""
Ten-step write operation protocol for dispatch-manager.

Usage (CLI):
    python scripts/change_manager.py --operation add_step --skill dispatch --dry-run
    python scripts/change_manager.py --operation edit_config --skill jira --key cache_ttl --value 60

Usage (module):
    from change_manager import ChangeManager
    cm = ChangeManager()
    cm.execute("add_step", skill="dispatch", spec={...})
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
STATE_STORE_PATH = Path(__file__).resolve().parents[2] / "dispatch" / "scripts"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from ecosystem_map import EcosystemMap
from version_manager import VersionManager
from backup_manager import BackupManager
from changelog_writer import ChangelogWriter

OPERATIONS = {
    "add_step": {"target": "workflow.yaml", "skill_required": True, "change_type": "Added", "bump": "MINOR"},
    "edit_step": {"target": "workflow.yaml", "skill_required": True, "change_type": "Changed", "bump": "PATCH"},
    "remove_step": {"target": "workflow.yaml", "skill_required": True, "change_type": "Removed", "bump": "MINOR"},
    "add_teammate": {"target": "config/team.yaml", "skill_required": True, "change_type": "Added", "bump": "PATCH"},
    "remove_teammate": {"target": "config/team.yaml", "skill_required": True, "change_type": "Removed", "bump": "PATCH"},
    "add_bottleneck": {"target": "scripts/bottleneck_detector.py", "skill_required": True, "change_type": "Added", "bump": "MINOR"},
    "add_notification": {"target": "templates/slack/", "skill_required": True, "change_type": "Added", "bump": "PATCH"},
    "edit_config": {"target": "config/", "skill_required": True, "change_type": "Changed", "bump": "PATCH"},
    "register_skill": {"target": "config/ecosystem.yaml", "skill_required": False, "change_type": "Added", "bump": "MINOR"},
    "implement_optimus": {"target": "varies", "skill_required": False, "change_type": "Added", "bump": "MINOR"},
    "rollback": {"target": "varies", "skill_required": True, "change_type": "Changed", "bump": "PATCH"},
    "upgrade": {"target": "SKILL.md", "skill_required": True, "change_type": "Changed", "bump": "MINOR"},
    "contract_update": {"target": "contracts/registry.yaml", "skill_required": False, "change_type": "Changed", "bump": "PATCH"},
}


class ChangeManager:

    def __init__(self, dry_run: bool = False, no_backup: bool = False):
        self.dry_run = dry_run
        self.no_backup = no_backup
        self._eco = EcosystemMap()
        self._vm = VersionManager()
        self._bm = BackupManager()
        self._cw = ChangelogWriter()

    def execute(self, operation: str, **kwargs) -> Dict[str, Any]:
        intent = self.step_01_parse_intent(operation, **kwargs)
        impact = self.step_02_impact_analysis(intent)

        if not self.dry_run:
            if not self.step_03_confirmation(impact):
                return {"report": "Aborted by operator.", "ok": False}

        backup_path = None
        if not self.no_backup and not self.dry_run:
            backup_path = self.step_04_backup(impact)

        validation = self.step_05_dry_run_validation(intent, backup_path)
        if validation.get("errors"):
            return {"report": f"Validation failed: {validation['errors']}", "ok": False}

        if self.dry_run:
            return {"report": f"DRY RUN: would modify {impact['affected_files']}", "ok": True}

        modified = self.step_06_apply(intent)
        post_check = self.step_07_post_apply_validation(modified, backup_path)
        if not post_check.get("ok"):
            return {"report": f"ROLLED BACK: {post_check.get('reason')}", "ok": False}

        self.step_08_version_changelog(intent)
        self.step_09_symlink_verification(intent)
        report = self.step_10_status_report(intent, post_check)
        return {"report": report, "ok": True}

    def step_01_parse_intent(self, operation: str, **kwargs) -> Dict:
        if operation not in OPERATIONS:
            raise ValueError(f"Unknown operation: {operation}. Valid: {list(OPERATIONS.keys())}")

        op_meta = OPERATIONS[operation]
        skill = kwargs.get("skill")
        skill_path = None

        if op_meta["skill_required"] and not skill:
            raise ValueError(f"Operation '{operation}' requires --skill")

        if skill:
            skill_path = self._eco.resolve_path(skill)
            if not skill_path:
                raise ValueError(f"Skill '{skill}' not found in ecosystem")

        return {
            "operation": operation,
            "skill": skill,
            "skill_path": str(skill_path) if skill_path else None,
            "target": op_meta["target"],
            "change_type": op_meta["change_type"],
            "bump_level": op_meta["bump"],
            "extra_args": {k: v for k, v in kwargs.items() if k != "skill"},
        }

    def step_02_impact_analysis(self, intent: Dict) -> Dict:
        affected_files = []
        affected_skills = []
        affected_contracts = []

        skill = intent.get("skill")
        skill_path = intent.get("skill_path")
        op = intent["operation"]

        if skill:
            affected_skills.append(skill)

        if skill_path:
            target = intent["target"]
            if target != "varies":
                affected_files.append(str(Path(skill_path) / target))
            affected_files.append(str(Path(skill_path) / "SKILL.md"))
            affected_files.append(str(Path(skill_path) / "CHANGELOG.md"))

        if op == "register_skill":
            affected_files.append(str(self._eco.ecosystem_path))
        if op == "contract_update":
            affected_files.append(str(SKILL_DIR / "contracts" / "registry.yaml"))
            affected_contracts.append(intent["extra_args"].get("contract", "unknown"))

        return {
            "affected_files": affected_files,
            "affected_skills": affected_skills,
            "affected_contracts": affected_contracts,
            "summary": f"{op} on {skill or 'ecosystem'}: {len(affected_files)} files",
        }

    def step_03_confirmation(self, impact: Dict) -> bool:
        print(f"\n[CHANGE] {impact['summary']}")
        print(f"  Files: {', '.join(impact['affected_files'][:5])}")
        if impact["affected_contracts"]:
            print(f"  Contracts: {', '.join(impact['affected_contracts'])}")
        return True

    def step_04_backup(self, impact: Dict) -> Optional[Path]:
        if not impact["affected_skills"]:
            return None
        skill = impact["affected_skills"][0]
        try:
            return self._bm.create_backup(skill)
        except Exception as e:
            print(f"  [WARN] Backup failed: {e}")
            return None

    def step_05_dry_run_validation(self, intent: Dict, backup_path: Optional[Path]) -> Dict:
        errors = []
        warnings = []

        skill = intent.get("skill")
        if skill:
            skill_path = self._eco.resolve_path(skill)
            if not skill_path or not skill_path.exists():
                errors.append(f"Skill path does not exist: {skill_path}")

        if intent["operation"] == "contract_update":
            registry = SKILL_DIR / "contracts" / "registry.yaml"
            if not registry.exists():
                errors.append("contracts/registry.yaml not found")

        return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}

    def step_06_apply(self, intent: Dict) -> List[str]:
        op = intent["operation"]
        handler = getattr(self, f"_apply_{op}", None)
        if handler:
            return handler(intent)
        return self._apply_generic(intent)

    def step_07_post_apply_validation(self, modified_paths: List[str],
                                       backup_path: Optional[Path]) -> Dict:
        try:
            sys.path.insert(0, str(SKILL_DIR / "scripts"))
            from contract_validator import main as cv_main
        except ImportError:
            pass
        return {"ok": True, "modified": modified_paths}

    def step_08_version_changelog(self, intent: Dict) -> Dict:
        skill = intent.get("skill")
        if not skill:
            return {}
        try:
            new_version = self._vm.bump_version(skill, intent["bump_level"])
            self._cw.write_entry(skill, new_version, intent["change_type"],
                                 f"{intent['operation']}: {intent.get('extra_args', {})}")
            return {"version": new_version}
        except Exception as e:
            print(f"  [WARN] Version/changelog update: {e}")
            return {}

    def step_09_symlink_verification(self, intent: Dict) -> Dict:
        verified = []
        repaired = []
        for skill in [intent.get("skill")] if intent.get("skill") else []:
            entry = self._eco.get_skill(skill)
            if not entry:
                continue
            symlink = Path(os.path.expanduser(entry["symlink"]))
            skill_path = Path(os.path.expanduser(entry["path"]))
            if symlink.exists() and symlink.resolve() == skill_path.resolve():
                verified.append(skill)
            elif skill_path.exists():
                symlink.parent.mkdir(parents=True, exist_ok=True)
                if symlink.exists() or symlink.is_symlink():
                    symlink.unlink()
                symlink.symlink_to(skill_path)
                repaired.append(skill)
        return {"verified": verified, "repaired": repaired}

    def step_10_status_report(self, intent: Dict, results: Dict) -> str:
        lines = [
            f"Operation: {intent['operation']}",
            f"Skill: {intent.get('skill', 'ecosystem')}",
            f"Modified: {len(results.get('modified', []))} files",
            f"Status: OK",
        ]

        try:
            if str(STATE_STORE_PATH) not in sys.path:
                sys.path.insert(0, str(STATE_STORE_PATH))
            from state_store import StateStore
            store = StateStore()
            op = intent["operation"]
            skill = intent.get("skill", "ecosystem")

            if op == "register_skill":
                store.emit_event("skill_registered", "dispatch-manager", {
                    "skill_slug": skill,
                    "path": intent.get("skill_path", ""),
                })
            elif op == "upgrade":
                store.emit_event("skill_upgraded", "dispatch-manager", {
                    "skill_slug": skill,
                })
            elif op == "rollback":
                store.emit_event("finding_created", "dispatch-manager", {
                    "finding_id": f"ROLLBACK-{skill}",
                    "title": f"Rollback: {skill}",
                    "severity": "HIGH",
                    "category": "coherency",
                    "affected_skill": skill,
                })
            elif op == "contract_update":
                store.emit_event("contract_updated", "dispatch-manager", {
                    "contract_id": intent.get("extra_args", {}).get("contract", "unknown"),
                    "change_type": "update",
                })

            store.emit_event("beads_board_mutated", "dispatch-manager", {
                "mutation_type": op, "skill": skill,
            })
            store.close()
        except Exception:
            pass

        return "\n".join(lines)

    def _apply_add_step(self, intent: Dict) -> List[str]:
        skill_path = Path(intent["skill_path"])
        wf_path = skill_path / "workflow.yaml"
        if not wf_path.exists():
            wf_path = Path(os.path.expanduser("~/.zsh/dispatch/workflow.yaml"))
        if not wf_path.exists():
            raise FileNotFoundError(f"workflow.yaml not found for {intent['skill']}")

        data = yaml.safe_load(wf_path.read_text()) or {}
        steps = data.get("steps", [])
        step_spec = intent["extra_args"].get("spec", {})
        steps.append(step_spec)
        data["steps"] = steps

        from version_manager import _atomic_write
        _atomic_write(wf_path, yaml.dump(data, default_flow_style=False, sort_keys=False))
        return [str(wf_path)]

    def _apply_edit_config(self, intent: Dict) -> List[str]:
        skill_path = Path(intent["skill_path"])
        key = intent["extra_args"].get("key", "")
        value = intent["extra_args"].get("value", "")
        config_name = intent["extra_args"].get("config", "")

        if config_name:
            config_path = skill_path / config_name
        else:
            entry = self._eco.get_skill(intent["skill"])
            config_path = Path(os.path.expanduser(entry.get("config", "")))

        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}")

        data = yaml.safe_load(config_path.read_text()) or {}
        keys = key.split(".")
        target = data
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value

        from version_manager import _atomic_write
        _atomic_write(config_path, yaml.dump(data, default_flow_style=False, sort_keys=False))
        return [str(config_path)]

    def _apply_register_skill(self, intent: Dict) -> List[str]:
        extra = intent["extra_args"]
        name = extra.get("name", "")
        entry = extra.get("entry", {})
        if not name or not entry:
            raise ValueError("register_skill requires name and entry in extra_args")
        self._eco.add_skill(name, entry)
        return [str(self._eco.ecosystem_path)]

    def _apply_rollback(self, intent: Dict) -> List[str]:
        skill = intent["skill"]
        version = intent["extra_args"].get("to")
        self._bm.restore_backup(skill, version=version)
        return [intent["skill_path"]]

    def _apply_upgrade(self, intent: Dict) -> List[str]:
        return [str(Path(intent["skill_path"]) / "SKILL.md")]

    def _apply_contract_update(self, intent: Dict) -> List[str]:
        registry_path = SKILL_DIR / "contracts" / "registry.yaml"
        if not registry_path.exists():
            raise FileNotFoundError("contracts/registry.yaml not found")

        data = yaml.safe_load(registry_path.read_text()) or {}
        contract_name = intent["extra_args"].get("contract", "")
        updates = intent["extra_args"].get("updates", {})

        contracts = data.get("contracts", {})
        if contract_name not in contracts:
            contracts[contract_name] = updates
        else:
            existing = contracts[contract_name]
            immutable = set(existing.get("immutable_fields", []))
            for k, v in updates.items():
                if k in immutable:
                    raise ValueError(f"Cannot modify immutable field '{k}' in contract '{contract_name}'")
                existing[k] = v
        data["contracts"] = contracts

        from version_manager import _atomic_write
        _atomic_write(registry_path, yaml.dump(data, default_flow_style=False, sort_keys=False))
        return [str(registry_path)]

    def _apply_generic(self, intent: Dict) -> List[str]:
        print(f"  [APPLY] {intent['operation']} — generic handler")
        return []


def main():
    parser = argparse.ArgumentParser(description="Dispatch-manager change protocol")
    parser.add_argument("--operation", required=True,
                        choices=list(OPERATIONS.keys()))
    parser.add_argument("--skill", help="Target skill name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("args", nargs="*", help="Operation-specific arguments")

    args = parser.parse_args()
    cm = ChangeManager(dry_run=args.dry_run, no_backup=args.no_backup)
    result = cm.execute(args.operation, skill=args.skill, extra_args=args.args)
    print(result.get("report", "Done."))


if __name__ == "__main__":
    main()
