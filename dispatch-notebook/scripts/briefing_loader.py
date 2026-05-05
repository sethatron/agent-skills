#!/usr/bin/env python3
"""
Briefing generator and context injector.

Usage:
    python scripts/briefing_loader.py generate [--output path]
    python scripts/briefing_loader.py summarize <briefing-path> [--max-bullets 5]
    python scripts/briefing_loader.py check-staleness <briefing-path> [--threshold 48]
"""

import argparse
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SKILL_DIR / "templates"
CONFIG_PATH = SKILL_DIR / "config" / "notebook.yaml"
NOTEBOOK_DIR = Path.home() / ".zsh" / "dispatch" / "notebook"


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


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, text
    return meta, parts[2].strip()


class BriefingLoader:
    def __init__(self, templates_dir: Optional[Path] = None, config_path: Optional[Path] = None):
        self.templates_dir = templates_dir or TEMPLATES_DIR
        cp = config_path or CONFIG_PATH
        self._config = yaml.safe_load(cp.read_text()) if cp.exists() else {}
        self._env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            keep_trailing_newline=True,
        )

    def generate_briefing(self, query_results: list[dict]) -> str:
        template = self._env.get_template("briefing.md.j2")
        now = datetime.now(timezone.utc)

        ctx = {
            "generated_at": now.isoformat(),
            "notebook_alias": self._config.get("notebook_alias", "dispatch"),
            "sources_count": 0,
            "query_ids": [],
            "date": now.strftime("%Y-%m-%d"),
        }

        for r in query_results:
            key = r.get("id", r.get("output_section", ""))
            ctx[key] = r.get("answer", "")
            ctx["query_ids"].append(r.get("id", ""))

        content = template.render(**ctx)
        briefing_path = NOTEBOOK_DIR / "morning_briefing.md"
        _atomic_write(briefing_path, content)
        return str(briefing_path)

    def summarize_for_context(self, briefing_path: Path, max_bullets: int = 5) -> str:
        text = Path(briefing_path).read_text()
        _, body = _parse_frontmatter(text)

        sections = re.split(r'^## ', body, flags=re.MULTILINE)
        summaries = []

        for section in sections:
            if not section.strip():
                continue
            lines = section.strip().splitlines()
            header = lines[0].strip()
            content_lines = [l for l in lines[1:] if l.strip()]

            bullets = [l for l in content_lines if re.match(r'^\s*[-*]\s', l)]
            if bullets:
                kept = bullets[:max_bullets]
                items = "; ".join(b.strip().lstrip("-* ").strip() for b in kept)
            else:
                kept = content_lines[:max_bullets]
                items = " ".join(l.strip() for l in kept)

            if items:
                summaries.append(f"**{header}:** {items}")

        return "\n".join(summaries)

    def check_briefing_staleness(self, path: Path, threshold_hours: float = 48) -> tuple[bool, int]:
        path = Path(path)
        if not path.exists():
            return (True, -1)

        try:
            text = path.read_text()
            meta, _ = _parse_frontmatter(text)
            generated = meta.get("generated_at")
            if generated:
                ts = datetime.fromisoformat(str(generated))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
                return (age_hours > threshold_hours, int(age_hours))
        except (ValueError, TypeError, yaml.YAMLError):
            pass

        try:
            mtime = path.stat().st_mtime
            age_hours = (datetime.now(timezone.utc).timestamp() - mtime) / 3600
            return (age_hours > threshold_hours, int(age_hours))
        except OSError:
            return (True, -1)


def main():
    parser = argparse.ArgumentParser(description="Briefing generator and context injector")
    sub = parser.add_subparsers(dest="command")

    g = sub.add_parser("generate")
    g.add_argument("--output", help="Output path for briefing")

    s = sub.add_parser("summarize")
    s.add_argument("briefing_path")
    s.add_argument("--max-bullets", type=int, default=5)

    c = sub.add_parser("check-staleness")
    c.add_argument("briefing_path")
    c.add_argument("--threshold", type=int, default=48, help="Staleness threshold in hours")

    args = parser.parse_args()

    if args.command == "generate":
        loader = BriefingLoader()
        sys.path.insert(0, str(SKILL_DIR / "scripts"))
        from query_runner import QueryRunner
        runner = QueryRunner()
        queries_path = SKILL_DIR / "queries" / "morning_briefing.yaml"
        results = runner.run_query_set(queries_path)
        ok_count = sum(1 for r in results if r.get("status") == "ok" and r.get("answer"))
        path = loader.generate_briefing(results)
        print(f"Briefing written to {path} ({ok_count}/{len(results)} queries returned content)")
        if ok_count == 0:
            print(
                "ERROR: every query returned empty/error. Briefing is a placeholder. "
                "Check stderr for [NLM ERROR] lines.",
                file=sys.stderr,
            )
            sys.exit(2)
    elif args.command == "summarize":
        loader = BriefingLoader()
        result = loader.summarize_for_context(Path(args.briefing_path), args.max_bullets)
        print(result)
    elif args.command == "check-staleness":
        loader = BriefingLoader()
        is_stale, age = loader.check_briefing_staleness(Path(args.briefing_path), args.threshold)
        print(f"Stale: {is_stale} (age: {age}h)")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
