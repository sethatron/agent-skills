#!/usr/bin/env python3
"""
Ecosystem map reader and validator.

Usage (CLI):
    python scripts/ecosystem_map.py list
    python scripts/ecosystem_map.py validate
    python scripts/ecosystem_map.py deps --order leaf-first

Usage (module):
    from ecosystem_map import EcosystemMap
    eco = EcosystemMap()
    skills = eco.load_ecosystem()
"""

import argparse
import os
import sys
import tempfile
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
REQUIRED_FIELDS = ["path", "symlink", "dsi_type", "dependencies", "produces", "consumed_by"]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class EcosystemMap:

    def __init__(self, ecosystem_path: Optional[Path] = None):
        self.ecosystem_path = ecosystem_path or SKILL_DIR / "config" / "ecosystem.yaml"

    def load_ecosystem(self) -> Dict[str, Any]:
        if not self.ecosystem_path.exists():
            return {"version": "1.0", "skills": {}, "extended_skills": {}}
        return yaml.safe_load(self.ecosystem_path.read_text()) or {}

    def _save_ecosystem(self, data: Dict) -> None:
        _atomic_write(self.ecosystem_path,
                      yaml.dump(data, default_flow_style=False, sort_keys=False))

    def _all_skills(self, data: Optional[Dict] = None) -> Dict[str, Dict]:
        data = data or self.load_ecosystem()
        merged = dict(data.get("skills", {}))
        merged.update(data.get("extended_skills", {}) or {})
        return merged

    def get_skill(self, name: str) -> Optional[Dict]:
        all_skills = self._all_skills()
        if name in all_skills:
            return all_skills[name]
        for _, entry in all_skills.items():
            if name in entry.get("aliases", []):
                return entry
        return None

    def validate_ecosystem(self) -> List[Dict]:
        results = []
        all_skills = self._all_skills()

        for name, entry in all_skills.items():
            missing = [f for f in REQUIRED_FIELDS if f not in entry]
            if missing:
                results.append({"skill": name, "ok": False,
                                "message": f"Missing fields: {', '.join(missing)}"})
                continue

            skill_path = Path(os.path.expanduser(entry["path"]))
            if not skill_path.exists():
                results.append({"skill": name, "ok": False,
                                "message": f"Path does not exist: {skill_path}"})
                continue

            symlink = Path(os.path.expanduser(entry["symlink"]))
            if not symlink.exists():
                results.append({"skill": name, "ok": False,
                                "message": f"Symlink missing: {symlink}"})
                continue

            for dep in entry.get("dependencies", []):
                if dep not in all_skills:
                    results.append({"skill": name, "ok": False,
                                    "message": f"Dependency '{dep}' not in ecosystem"})
                    continue

            results.append({"skill": name, "ok": True, "message": "OK"})

        try:
            self.dependency_order()
        except ValueError as e:
            results.append({"skill": "_ecosystem", "ok": False, "message": str(e)})

        return results

    def add_skill(self, name: str, entry: Dict) -> None:
        data = self.load_ecosystem()
        all_skills = self._all_skills(data)
        if name in all_skills:
            raise ValueError(f"Skill '{name}' already exists")

        for dep in entry.get("dependencies", []):
            if dep not in all_skills:
                raise ValueError(f"Dependency '{dep}' not found in ecosystem")

        if data.get("extended_skills") is None:
            data["extended_skills"] = {}
        data["extended_skills"][name] = entry

        all_after = self._all_skills(data)
        self._check_cycles(all_after)
        self._save_ecosystem(data)

    def remove_skill(self, name: str) -> None:
        data = self.load_ecosystem()
        if name in data.get("skills", {}):
            raise ValueError(f"Cannot remove core skill '{name}'")
        extended = data.get("extended_skills", {}) or {}
        if name not in extended:
            raise ValueError(f"Skill '{name}' not found in extended_skills")

        all_skills = self._all_skills(data)
        for sname, entry in all_skills.items():
            if sname != name and name in entry.get("dependencies", []):
                raise ValueError(f"Cannot remove '{name}': '{sname}' depends on it")

        del data["extended_skills"][name]
        self._save_ecosystem(data)

    def dependency_order(self, reverse: bool = False) -> List[str]:
        all_skills = self._all_skills()
        return self._topo_sort(all_skills, reverse)

    def _topo_sort(self, skills: Dict, reverse: bool = False) -> List[str]:
        in_degree = {name: 0 for name in skills}
        graph = {name: [] for name in skills}
        for name, entry in skills.items():
            for dep in entry.get("dependencies", []):
                if dep in skills:
                    graph[dep].append(name)
                    in_degree[name] += 1

        queue = deque(n for n in skills if in_degree[n] == 0)
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(skills):
            raise ValueError("Circular dependency detected in ecosystem")

        return list(reversed(order)) if reverse else order

    def _check_cycles(self, skills: Dict) -> None:
        self._topo_sort(skills)

    def resolve_path(self, skill_name: str) -> Optional[Path]:
        entry = self.get_skill(skill_name)
        if not entry:
            return None
        return Path(os.path.expanduser(entry["path"])).resolve()

    def resolve_symlink(self, skill_name: str) -> Optional[Path]:
        entry = self.get_skill(skill_name)
        if not entry:
            return None
        symlink = Path(os.path.expanduser(entry["symlink"]))
        return symlink.resolve() if symlink.exists() else None


def main():
    parser = argparse.ArgumentParser(description="Ecosystem map operations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all managed skills")
    sub.add_parser("validate", help="Validate ecosystem integrity")

    p_deps = sub.add_parser("deps", help="Show dependency order")
    p_deps.add_argument("--order", choices=["leaf-first", "root-first"], default="leaf-first")

    args = parser.parse_args()
    eco = EcosystemMap()

    if args.command == "list":
        data = eco.load_ecosystem()
        for name, entry in {**data.get("skills", {}), **data.get("extended_skills", {})}.items():
            print(f"  {name} ({entry.get('dsi_type', '?')}) — {entry.get('path', '?')}")
    elif args.command == "validate":
        results = eco.validate_ecosystem()
        for r in results:
            status = "OK" if r["ok"] else "FAIL"
            print(f"  [{status}] {r['skill']}: {r['message']}")
    elif args.command == "deps":
        order = eco.dependency_order(reverse=(args.order == "root-first"))
        for i, s in enumerate(order, 1):
            print(f"  {i}. {s}")


if __name__ == "__main__":
    main()
