#!/usr/bin/env python3
"""
Query execution engine — run queries with variable substitution and caching.

Usage:
    python scripts/query_runner.py run <query-set-yaml> [--substitutions key=val ...]
    python scripts/query_runner.py single <notebook> "<question>" [--timeout 180]
    python scripts/query_runner.py cache-status
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

SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = Path("~/.zsh/dispatch/notebook/query_cache").expanduser()
CONFIG_PATH = SKILL_DIR / "config" / "notebook.yaml"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from nlm_runner import NLMRunner, NLMError


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


class QueryRunner:
    def __init__(self, cache_dir: Optional[Path] = None, config_path: Optional[Path] = None):
        self.cache_dir = cache_dir or CACHE_DIR
        cp = config_path or CONFIG_PATH
        self._config = yaml.safe_load(cp.read_text()) if cp.exists() else {}
        self._alias = self._config.get("notebook_alias", "dispatch")
        self._default_cache_hours = self._config.get("cache_hours", 20)
        self._nlm = NLMRunner()

    def run_query(self, query_def: dict, substitutions: Optional[dict] = None) -> dict:
        qid = query_def.get("id", "unknown")
        question = query_def.get("question", "")
        timeout = query_def.get("timeout_seconds", self._config.get("default_timeout_seconds", 180))
        cache_hours = query_def.get("cache_hours", self._default_cache_hours)
        output_section = query_def.get("output_section", "")

        question = self._apply_substitutions(question, query_def, substitutions)

        cached = self.load_from_cache(qid)
        if cached and self._is_fresh(cached, cache_hours):
            cached["from_cache"] = True
            return cached

        try:
            result = self._nlm.notebook_query(self._alias, question, timeout)
            now = datetime.now(timezone.utc).isoformat()
            entry = {
                "id": qid,
                "question": question,
                "answer": result.answer,
                "sources_cited": result.sources_used,
                "asked_at": now,
                "status": "ok",
                "output_section": output_section,
                "from_cache": False,
            }
            self.save_to_cache(qid, entry)
            return entry
        except NLMError as e:
            print(f"[NLM ERROR] {qid}: {e}", file=sys.stderr)
            return {
                "id": qid,
                "question": question,
                "answer": "",
                "sources_cited": [],
                "asked_at": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "error": str(e),
                "output_section": output_section,
                "from_cache": False,
            }

    def run_query_set(self, yaml_path: Path, substitutions: Optional[dict] = None) -> list[dict]:
        data = yaml.safe_load(yaml_path.read_text()) or {}
        queries = data.get("queries", [])
        results = []
        for q in queries:
            results.append(self.run_query(q, substitutions))
        return results

    def load_from_cache(self, query_id: str, date: Optional[str] = None) -> Optional[dict]:
        date_str = date or datetime.now(timezone.utc).strftime("%Y%m%d")
        cache_file = self.cache_dir / date_str / f"{query_id}.md"
        if not cache_file.exists():
            return None
        try:
            meta, body = _parse_frontmatter(cache_file.read_text())
            if not meta.get("query_id"):
                return None
            return {
                "id": meta["query_id"],
                "question": meta.get("question", ""),
                "answer": body,
                "sources_cited": meta.get("sources_cited", []),
                "asked_at": meta.get("asked_at", ""),
                "status": "ok",
                "output_section": meta.get("output_section", ""),
                "from_cache": True,
            }
        except Exception:
            return None

    def save_to_cache(self, query_id: str, result: dict) -> None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        cache_file = self.cache_dir / date_str / f"{query_id}.md"
        sources = result.get("sources_cited", [])
        frontmatter = {
            "query_id": query_id,
            "question": result.get("question", ""),
            "asked_at": result.get("asked_at", ""),
            "notebook_alias": self._alias,
            "sources_cited": sources,
            "output_section": result.get("output_section", ""),
        }
        content = "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\n"
        content += result.get("answer", "")
        _atomic_write(cache_file, content)

    def check_cache_freshness(self, query_id: str, max_age_hours: float = 20) -> bool:
        cached = self.load_from_cache(query_id)
        if not cached:
            return False
        return self._is_fresh(cached, max_age_hours)

    def _apply_substitutions(self, question: str, query_def: dict,
                             substitutions: Optional[dict]) -> str:
        if not substitutions:
            return question
        for sub in query_def.get("runtime_substitutions", []):
            placeholder = sub.get("placeholder", "")
            source_key = sub.get("source", "").split(".")[-1]
            if placeholder and source_key in substitutions:
                question = question.replace(placeholder, substitutions[source_key])
        return question

    def _is_fresh(self, cached: dict, max_age_hours: float) -> bool:
        asked_at = cached.get("asked_at", "")
        if not asked_at:
            return False
        try:
            ts = datetime.fromisoformat(asked_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            return age_hours < max_age_hours
        except (ValueError, TypeError):
            return False

    def cache_status(self) -> dict:
        if not self.cache_dir.exists():
            return {"total_entries": 0, "dates": {}, "total_size_bytes": 0}
        dates = {}
        total_size = 0
        total_entries = 0
        for date_dir in sorted(self.cache_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            files = list(date_dir.glob("*.md"))
            size = sum(f.stat().st_size for f in files)
            dates[date_dir.name] = {"entries": len(files), "size_bytes": size}
            total_entries += len(files)
            total_size += size
        return {"total_entries": total_entries, "dates": dates, "total_size_bytes": total_size}


def main():
    parser = argparse.ArgumentParser(description="Query execution engine")
    sub = parser.add_subparsers(dest="command")

    r = sub.add_parser("run")
    r.add_argument("query_set", help="Path to query set YAML")
    r.add_argument("--substitutions", nargs="*", help="key=val pairs")

    s = sub.add_parser("single")
    s.add_argument("notebook")
    s.add_argument("question")
    s.add_argument("--timeout", type=int, default=180)

    sub.add_parser("cache-status")

    args = parser.parse_args()

    if args.command == "run":
        runner = QueryRunner()
        subs = {}
        if args.substitutions:
            for pair in args.substitutions:
                k, v = pair.split("=", 1)
                subs[k] = v
        results = runner.run_query_set(Path(args.query_set), subs or None)
        for result in results:
            status = result.get("status", "?")
            cached = " (cached)" if result.get("from_cache") else ""
            print(f"  [{result.get('id', '?')}] {status}{cached}")
    elif args.command == "single":
        nlm = NLMRunner()
        result = nlm.notebook_query(args.notebook, args.question, args.timeout)
        print(result.answer)
    elif args.command == "cache-status":
        runner = QueryRunner()
        info = runner.cache_status()
        print(f"Cache: {info['total_entries']} entries, {info['total_size_bytes']} bytes")
        for date, stats in info.get("dates", {}).items():
            print(f"  {date}: {stats['entries']} entries ({stats['size_bytes']} bytes)")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
