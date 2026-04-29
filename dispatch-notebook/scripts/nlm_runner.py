#!/usr/bin/env python3
"""
NLM CLI runner — single gateway for all NotebookLM operations.

All nlm commands pass through this module. No direct nlm calls elsewhere.

Usage as module:
    from nlm_runner import NLMRunner
    runner = NLMRunner()
    if runner.login_check():
        result = runner.notebook_query("dispatch", "What patterns recur?")

Usage as CLI:
    python scripts/nlm_runner.py check
    python scripts/nlm_runner.py query dispatch "What patterns recur?"
    python scripts/nlm_runner.py sources dispatch
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config" / "notebook.yaml"

AUTH_ERROR_PATTERNS = [
    "Cookies have expired",
    "authentication may have expired",
    "Authentication required",
    "not authenticated",
    "401",
    "login required",
]

SOURCE_LIMIT_PATTERNS = [
    "source limit",
    "maximum sources",
    "too many sources",
    "50 sources",
]

NETWORK_ERROR_PATTERNS = [
    "network",
    "connection refused",
    "connection reset",
    "timed out",
    "DNS",
    "ECONNREFUSED",
]


class NLMError(Exception):
    pass


class NLMAuthError(NLMError):
    def __init__(self, message: str = ""):
        detail = message or "NotebookLM authentication expired."
        super().__init__(f"{detail} Run: nlm login")


class NLMSourceLimitError(NLMError):
    pass


class NLMTimeoutError(NLMError):
    pass


class NLMNetworkError(NLMError):
    pass


@dataclass
class NLMResult:
    returncode: int
    stdout: str
    stderr: str
    success: bool


@dataclass
class NLMQueryResult:
    answer: str
    sources_used: list[str]
    raw_response: str


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _match_patterns(text: str, patterns: list[str]) -> bool:
    lower = text.lower()
    return any(p.lower() in lower for p in patterns)


class NLMRunner:
    def __init__(self, config_path: Optional[Path] = None):
        self._config = _load_config() if config_path is None else yaml.safe_load(config_path.read_text()) or {}
        self._default_timeout = self._config.get("default_timeout_seconds", 180)

    def _check_circuit(self):
        try:
            store_path = str(Path(__file__).resolve().parents[2] / "dispatch" / "scripts")
            if store_path not in sys.path:
                sys.path.insert(0, store_path)
            from state_store import StateStore
            store = StateStore()
            state = store.check_circuit("nlm_auth")
            store.close()
            return state
        except Exception:
            return "CLOSED"

    def _record_circuit(self, success, error=None):
        try:
            store_path = str(Path(__file__).resolve().parents[2] / "dispatch" / "scripts")
            if store_path not in sys.path:
                sys.path.insert(0, store_path)
            from state_store import StateStore
            store = StateStore()
            if success:
                store.record_success("nlm_auth")
            else:
                store.record_failure("nlm_auth", error or "unknown")
            store.close()
        except Exception:
            pass

    def run(self, args: list[str], capture_output: bool = True, timeout: int = 60) -> NLMResult:
        circuit_state = self._check_circuit()
        if circuit_state == "OPEN":
            raise NLMError("[CIRCUIT OPEN] NotebookLM auth is degraded, skipping operation")

        cmd = ["nlm"] + args
        hard_timeout = timeout + 30
        try:
            proc = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=hard_timeout,
            )
            result = NLMResult(
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                success=proc.returncode == 0,
            )
        except subprocess.TimeoutExpired:
            self._record_circuit(False, f"Timeout after {hard_timeout}s")
            raise NLMTimeoutError(f"Command timed out after {hard_timeout}s: nlm {' '.join(args)}")
        except FileNotFoundError:
            raise NLMError("nlm binary not found. Install with: pip install notebooklm-mcp-cli")

        if not result.success:
            combined = result.stdout + result.stderr
            if _match_patterns(combined, AUTH_ERROR_PATTERNS):
                self._record_circuit(False, result.stderr.strip()[:200])
                raise NLMAuthError(result.stderr.strip())
            if _match_patterns(combined, SOURCE_LIMIT_PATTERNS):
                raise NLMSourceLimitError(result.stderr.strip() or "Source limit reached (max 50)")
            if _match_patterns(combined, NETWORK_ERROR_PATTERNS):
                self._record_circuit(False, result.stderr.strip()[:200])
                raise NLMNetworkError(result.stderr.strip())

        if result.success:
            self._record_circuit(True)

        return result

    def _run_with_network_retry(self, args: list[str], timeout: int = 60) -> NLMResult:
        try:
            return self.run(args, timeout=timeout)
        except NLMNetworkError:
            time.sleep(10)
            return self.run(args, timeout=timeout)

    def login_check(self) -> bool:
        try:
            result = self.run(["login", "--check"], timeout=15)
            return result.success
        except NLMAuthError:
            return False
        except (NLMTimeoutError, NLMNetworkError, NLMError):
            return False

    def notebook_create(self, title: str) -> str:
        result = self._run_with_network_retry(
            ["notebook", "create", title],
            timeout=30,
        )
        if not result.success:
            raise NLMError(f"Failed to create notebook: {result.stderr}")
        try:
            data = json.loads(result.stdout)
            nb_id = data.get("id") or data.get("notebook_id") or data.get("notebookId", "")
            if nb_id:
                return str(nb_id)
        except (json.JSONDecodeError, KeyError):
            pass
        import re
        for line in result.stdout.strip().splitlines():
            m = re.search(r'ID:\s*(\S+)', line)
            if m:
                return m.group(1)
            stripped = line.strip()
            if len(stripped) > 10 and not stripped.startswith(("✓", "{", "Created")):
                return stripped
        raise NLMError(f"Could not extract notebook ID from output: {result.stdout[:200]}")

    def alias_get(self, name: str) -> Optional[str]:
        try:
            result = self.run(["alias", "get", name], timeout=10)
        except NLMError:
            return None
        if result.success and result.stdout.strip():
            output = result.stdout.strip()
            for line in output.splitlines():
                line = line.strip()
                if len(line) > 10:
                    return line
        return None

    def alias_set(self, name: str, uuid: str) -> bool:
        result = self._run_with_network_retry(["alias", "set", name, uuid], timeout=10)
        return result.success

    def source_add(
        self,
        notebook: str,
        file_path: Optional[str] = None,
        text: Optional[str] = None,
        title: Optional[str] = None,
        wait: bool = True,
    ) -> str:
        args = ["source", "add", notebook]
        if file_path:
            args.extend(["--file", file_path])
        elif text:
            args.extend(["--text", text])
        else:
            raise NLMError("source_add requires either file_path or text")
        if title:
            args.extend(["--title", title])
        if wait:
            args.append("--wait")
        timeout = self._config.get("source_add_timeout", 300) if wait else 30

        result = self._run_with_network_retry(args, timeout=timeout)
        if not result.success:
            raise NLMError(f"Failed to add source: {result.stderr}")

        import re
        try:
            data = json.loads(result.stdout)
            if isinstance(data, str):
                # nlm source add --wait sometimes returns the ID as a bare JSON string
                return data
            if isinstance(data, dict):
                sid = data.get("id") or data.get("source_id") or data.get("sourceId", "")
                if sid:
                    return str(sid)
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, str):
                    return first
                if isinstance(first, dict):
                    sid = first.get("id") or first.get("source_id") or first.get("sourceId", "")
                    if sid:
                        return str(sid)
        except (json.JSONDecodeError, KeyError):
            pass
        for line in result.stdout.strip().splitlines():
            m = re.search(r'ID:\s*(\S+)', line)
            if m:
                return m.group(1)
            m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', line)
            if m:
                return m.group(0)
        raise NLMError(f"Could not extract source ID from output: {result.stdout[:200]}")

    def source_delete(self, notebook: str, source_id: str) -> bool:
        result = self._run_with_network_retry(
            ["source", "delete", source_id, "--confirm"],
            timeout=30,
        )
        return result.success

    def source_list(self, notebook: str) -> list[dict]:
        result = self._run_with_network_retry(
            ["source", "list", notebook, "--json"],
            timeout=30,
        )
        if not result.success:
            raise NLMError(f"Failed to list sources: {result.stderr}")
        try:
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("sources", data.get("items", [data]))
        except json.JSONDecodeError:
            pass
        return []

    def notebook_query(
        self,
        notebook: str,
        question: str,
        timeout: int = 180,
        source_ids: Optional[list[str]] = None,
    ) -> NLMQueryResult:
        args = ["notebook", "query", notebook, question, "--json"]
        if source_ids:
            args.extend(["--source-ids", ",".join(source_ids)])

        result = self._run_with_network_retry(args, timeout=timeout)
        if not result.success:
            raise NLMError(f"Query failed: {result.stderr}")

        try:
            data = json.loads(result.stdout)
            answer = data.get("answer") or data.get("response") or data.get("text", "")
            sources = data.get("sources_used") or data.get("sources") or data.get("citations", [])
            if isinstance(sources, list) and sources and isinstance(sources[0], dict):
                sources = [s.get("title", s.get("id", str(s))) for s in sources]
            return NLMQueryResult(
                answer=str(answer),
                sources_used=sources,
                raw_response=result.stdout,
            )
        except json.JSONDecodeError:
            return NLMQueryResult(
                answer=result.stdout.strip(),
                sources_used=[],
                raw_response=result.stdout,
            )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="NLM CLI Runner")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="Check authentication")

    q = sub.add_parser("query", help="Query a notebook")
    q.add_argument("notebook", help="Notebook alias or ID")
    q.add_argument("question", help="Question to ask")
    q.add_argument("--timeout", type=int, default=180)

    s = sub.add_parser("sources", help="List sources")
    s.add_argument("notebook", help="Notebook alias or ID")

    a = sub.add_parser("add-source", help="Add a source")
    a.add_argument("notebook", help="Notebook alias or ID")
    a.add_argument("--file", dest="file_path", help="File to upload")
    a.add_argument("--text", help="Text content")
    a.add_argument("--title", help="Source title")

    args = parser.parse_args()
    runner = NLMRunner()

    if args.command == "check":
        ok = runner.login_check()
        print("Authenticated" if ok else "Not authenticated")
        sys.exit(0 if ok else 1)

    elif args.command == "query":
        try:
            result = runner.notebook_query(args.notebook, args.question, args.timeout)
            print(result.answer)
            if result.sources_used:
                print(f"\nSources: {', '.join(result.sources_used)}")
        except NLMError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "sources":
        try:
            sources = runner.source_list(args.notebook)
            for s in sources:
                if isinstance(s, dict):
                    print(f"  {s.get('id', '?')}: {s.get('title', s.get('name', '?'))}")
                else:
                    print(f"  {s}")
        except NLMError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "add-source":
        try:
            sid = runner.source_add(args.notebook, file_path=args.file_path, text=args.text, title=args.title)
            print(f"Added source: {sid}")
        except NLMError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
