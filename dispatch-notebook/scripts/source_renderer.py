#!/usr/bin/env python3
"""
Source content renderer — transforms files to annotated prose for NotebookLM upload.

Usage:
    python scripts/source_renderer.py render-skill <path>
    python scripts/source_renderer.py render-yaml <path> --title "Title"
    python scripts/source_renderer.py render-optimus <path>
    python scripts/source_renderer.py render-session <session-yaml-path>
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SKILL_DIR / "templates"


class SourceRenderer:
    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            keep_trailing_newline=True,
        )

    def render_skill_md(self, path: Path) -> str:
        path = Path(path)
        content = path.read_text()
        version = "unknown"
        match = re.search(r'^version:\s*["\']?([^"\'\n]+)', content, re.MULTILINE)
        if match:
            version = match.group(1).strip()
        now = datetime.now(timezone.utc).isoformat()
        header = (
            f"---\n"
            f"source_type: framework_core\n"
            f"origin_path: {path}\n"
            f"version: \"{version}\"\n"
            f"rendered_at: \"{now}\"\n"
            f"---\n\n"
        )
        return header + content

    def render_yaml_file(self, path: Path, title: str) -> str:
        path = Path(path)
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raw = {"content": raw}

        fields = []
        for key, value in raw.items():
            explanation = ""
            if isinstance(value, dict) and "description" in value:
                explanation = value["description"]
            if isinstance(value, (dict, list)):
                value_str = yaml.dump(value, default_flow_style=False).strip()
            else:
                value_str = str(value)
            fields.append({"name": key, "value": value_str, "explanation": explanation})

        template = self._env.get_template("yaml_to_prose.md.j2")
        return template.render(
            title=title,
            description=f"Rendered from {path.name}",
            fields=fields,
        )

    def render_optimus_report(self, path: Path) -> str:
        path = Path(path)
        content = path.read_text()

        frontmatter = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()

        template = self._env.get_template("optimus_header.md.j2")
        header = template.render(
            report_date=frontmatter.get("report_date", "unknown"),
            period=frontmatter.get("period", "unknown"),
            source_path=str(path),
            finding_counts=frontmatter.get("finding_counts", {"total": 0}),
        )
        return header + "\n" + body

    def render_session_summary(self, session_data: dict) -> str:
        template = self._env.get_template("session_summary.md.j2")
        return template.render(
            date=session_data.get("date", "unknown"),
            duration=session_data.get("duration", "unknown"),
            tasks=session_data.get("tasks", []),
            steps_completed=session_data.get("steps_completed", []),
            bottlenecks=session_data.get("bottlenecks", []),
            deferred=session_data.get("deferred", []),
        )


def main():
    parser = argparse.ArgumentParser(description="Source content renderer")
    sub = parser.add_subparsers(dest="command")

    s = sub.add_parser("render-skill")
    s.add_argument("path")

    y = sub.add_parser("render-yaml")
    y.add_argument("path")
    y.add_argument("--title", required=True)

    o = sub.add_parser("render-optimus")
    o.add_argument("path")

    ss = sub.add_parser("render-session")
    ss.add_argument("path")

    args = parser.parse_args()
    renderer = SourceRenderer()

    if args.command == "render-skill":
        print(renderer.render_skill_md(Path(args.path)))
    elif args.command == "render-yaml":
        print(renderer.render_yaml_file(Path(args.path), args.title))
    elif args.command == "render-optimus":
        print(renderer.render_optimus_report(Path(args.path)))
    elif args.command == "render-session":
        data = yaml.safe_load(Path(args.path).read_text())
        print(renderer.render_session_summary(data))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
