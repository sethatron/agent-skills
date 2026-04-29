#!/usr/bin/env python3
"""
Structured changelog entry writer.

Usage (CLI):
    python scripts/changelog_writer.py write --skill dispatch --version 1.1.0 --type Added --message "New step"
    python scripts/changelog_writer.py read --skill dispatch --last 5

Usage (module):
    from changelog_writer import ChangelogWriter
    cw = ChangelogWriter()
    cw.write_entry("dispatch", "1.1.0", "Added", "New workflow step for linting")
"""

import argparse
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from ecosystem_map import EcosystemMap


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


class ChangelogWriter:

    def __init__(self):
        self._eco = EcosystemMap()

    def _resolve_changelog_path(self, skill_name: str) -> Path:
        skill_path = self._eco.resolve_path(skill_name)
        if not skill_path:
            raise ValueError(f"Skill '{skill_name}' not found in ecosystem")
        return skill_path / "CHANGELOG.md"

    def format_entry(self, version: str, change_type: str, message: str,
                     **metadata) -> str:
        lines = [f"## [{version}] — {date.today().isoformat()}", f"### {change_type}"]
        detail = message
        annotations = []
        if metadata.get("optimus_finding"):
            annotations.append(f"Optimus: {metadata['optimus_finding']}")
        if metadata.get("contract_impact"):
            annotations.append(f"Contract: {metadata['contract_impact']}")
        if metadata.get("dsi_result"):
            annotations.append(f"DSI: {metadata['dsi_result']}")
        if annotations:
            detail += " (" + ", ".join(annotations) + ")"
        lines.append(f"- {detail}")
        if metadata.get("cascading_updates"):
            for cu in metadata["cascading_updates"]:
                lines.append(f"- Cascading: {cu}")
        return "\n".join(lines)

    def write_entry(self, skill_name: str, version: str, change_type: str,
                    message: str, optimus_finding: Optional[str] = None,
                    contract_impact: Optional[str] = None,
                    dsi_result: Optional[str] = None,
                    cascading_updates: Optional[List[str]] = None) -> None:
        cl_path = self._resolve_changelog_path(skill_name)
        entry = self.format_entry(version, change_type, message,
                                  optimus_finding=optimus_finding,
                                  contract_impact=contract_impact,
                                  dsi_result=dsi_result,
                                  cascading_updates=cascading_updates)

        if cl_path.exists():
            existing = cl_path.read_text()
            header_match = re.match(r'^(# .+\n)', existing)
            if header_match:
                rest = existing[header_match.end():]
                content = header_match.group(1) + "\n" + entry + "\n\n" + rest.lstrip("\n")
            else:
                content = "# Changelog\n\n" + entry + "\n\n" + existing
        else:
            content = "# Changelog\n\n" + entry + "\n"

        _atomic_write(cl_path, content)

    def read_changelog(self, skill_name: str, last_n: Optional[int] = None) -> List[Dict]:
        cl_path = self._resolve_changelog_path(skill_name)
        if not cl_path.exists():
            return []

        content = cl_path.read_text()
        entries = []
        blocks = re.split(r'^## ', content, flags=re.MULTILINE)

        for block in blocks[1:]:
            lines = block.strip().splitlines()
            if not lines:
                continue
            header = lines[0]
            m = re.match(r'\[(.+?)\]\s*—\s*(\S+)', header)
            if not m:
                continue
            version = m.group(1)
            entry_date = m.group(2)
            change_type = ""
            messages = []
            for line in lines[1:]:
                type_match = re.match(r'^### (.+)', line)
                if type_match:
                    change_type = type_match.group(1).strip()
                elif line.startswith("- "):
                    messages.append(line[2:].strip())

            entries.append({
                "version": version,
                "date": entry_date,
                "type": change_type,
                "message": "; ".join(messages) if messages else "",
                "messages": messages,
            })

        if last_n:
            entries = entries[:last_n]
        return entries


def main():
    parser = argparse.ArgumentParser(description="Changelog writer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_write = sub.add_parser("write", help="Write changelog entry")
    p_write.add_argument("--skill", required=True)
    p_write.add_argument("--version", required=True)
    p_write.add_argument("--type", required=True, choices=["Added", "Changed", "Fixed", "Removed"])
    p_write.add_argument("--message", required=True)
    p_write.add_argument("--optimus-finding", help="Related Optimus finding ID")
    p_write.add_argument("--contract-impact", help="Affected contract name")
    p_write.add_argument("--dsi-result", help="DSI compliance result")

    p_read = sub.add_parser("read", help="Read changelog entries")
    p_read.add_argument("--skill", required=True)
    p_read.add_argument("--last", type=int, help="Show only last N entries")

    args = parser.parse_args()
    cw = ChangelogWriter()

    if args.command == "write":
        cw.write_entry(args.skill, args.version, args.type, args.message,
                       optimus_finding=args.optimus_finding,
                       contract_impact=args.contract_impact,
                       dsi_result=args.dsi_result)
        print("Entry written.")
    elif args.command == "read":
        entries = cw.read_changelog(args.skill, last_n=args.last)
        for e in entries:
            print(f"  [{e['version']}] {e['type']}: {e['message']}")


if __name__ == "__main__":
    main()
