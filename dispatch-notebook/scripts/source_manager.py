#!/usr/bin/env python3
"""
Source lifecycle manager — upload, delete, hash, inventory CRUD, reconciliation.

Usage:
    python scripts/source_manager.py upload <path> --title "Title" --tier tier1
    python scripts/source_manager.py delete <source-id>
    python scripts/source_manager.py reconcile
    python scripts/source_manager.py prune
    python scripts/source_manager.py inventory
"""

import argparse
import hashlib
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = Path.home() / ".zsh" / "dispatch" / "notebook"
STATE_STORE_PATH = Path(__file__).resolve().parents[2] / "dispatch" / "scripts"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from nlm_runner import NLMRunner, NLMError


def _get_store():
    if str(STATE_STORE_PATH) not in sys.path:
        sys.path.insert(0, str(STATE_STORE_PATH))
    from state_store import StateStore
    store = StateStore()
    store.schema_init()
    return store


class SourceManager:
    def __init__(self, inventory_path: Optional[Path] = None, config_path: Optional[Path] = None):
        self.inventory_path = inventory_path or NOTEBOOK_DIR / "source_inventory.yaml"
        self.config_path = config_path or SKILL_DIR / "config" / "notebook.yaml"
        self._config = {}
        if self.config_path.exists():
            self._config = yaml.safe_load(self.config_path.read_text()) or {}
        self._runner = NLMRunner()
        self._alias = self._config.get("notebook_alias", "dispatch")

    def get_content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def load_inventory(self) -> dict:
        if not self.inventory_path.exists():
            return {"sources": []}
        data = yaml.safe_load(self.inventory_path.read_text())
        if not data or "sources" not in data:
            return {"sources": []}
        sources = data["sources"]
        # Accept both flat-list form ({sources: [...]}) and dict-keyed-by-tier
        # form ({sources: {tier1: [...], tier2: [...]}}) — the dispatch skill's
        # state_store.export_source_inventory emits the latter; normalize to flat.
        if isinstance(sources, dict):
            flat = []
            for tier_entries in sources.values():
                if isinstance(tier_entries, list):
                    flat.extend(e for e in tier_entries if isinstance(e, dict))
            data["sources"] = flat
        elif isinstance(sources, list):
            data["sources"] = [e for e in sources if isinstance(e, dict)]
        else:
            data["sources"] = []
        return data

    def save_inventory(self, data: dict) -> None:
        self.inventory_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.inventory_path.with_suffix(".tmp")
        tmp_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        tmp_path.rename(self.inventory_path)

    def upload_source(self, content: str, title: str, tier: str, origin_path: str = "") -> str:
        """Upload rendered content as a text source. Hash-check against inventory; skip if unchanged."""
        content_hash = self.get_content_hash(content)
        inv = self.load_inventory()

        for entry in inv["sources"]:
            if entry.get("title") == title and entry.get("content_hash") == content_hash:
                return entry["nlm_source_id"]

        staging_dir = NOTEBOOK_DIR / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        slug = title.lower().replace(" ", "_").replace("/", "_")[:60]
        staging_file = staging_dir / f"{slug}.md"
        staging_file.write_text(content)

        source_id = self._runner.source_add(
            self._alias,
            file_path=str(staging_file),
            title=title,
            wait=True,
        )

        old_ids = [
            e["nlm_source_id"] for e in inv["sources"]
            if e.get("title") == title and e.get("content_hash") != content_hash
        ]

        now = datetime.now(timezone.utc).isoformat()
        tier_days = {
            "tier1": None,
            "tier2": self._config.get("tier2_days", 30),
            "tier3": self._config.get("tier3_days", 7),
        }
        expires = None
        if tier_days.get(tier):
            from datetime import timedelta
            expires = (datetime.now(timezone.utc) + timedelta(days=tier_days[tier])).isoformat()

        inv["sources"] = [e for e in inv["sources"] if e.get("title") != title]
        inv["sources"].append({
            "nlm_source_id": source_id,
            "title": title,
            "tier": tier,
            "origin_path": origin_path,
            "content_hash": content_hash,
            "uploaded_at": now,
            "expires_at": expires,
            "last_verified": now,
        })
        self.save_inventory(inv)

        for old_id in old_ids:
            try:
                self._runner.source_delete(self._alias, old_id)
            except NLMError:
                pass

        try:
            store = _get_store()
            store.upsert_source(source_id, title, tier, origin_path, content_hash, now, expires)
            store.emit_event("source_uploaded", "dispatch-notebook", {
                "nlm_source_id": source_id,
                "title": title,
                "tier": tier,
                "origin_path": origin_path,
            })
            store.export_source_inventory()
            store.close()
        except Exception:
            pass

        return source_id

    def delete_source(self, source_id: str) -> bool:
        ok = self._runner.source_delete(self._alias, source_id)
        if ok:
            inv = self.load_inventory()
            inv["sources"] = [e for e in inv["sources"] if e.get("nlm_source_id") != source_id]
            self.save_inventory(inv)
            try:
                store = _get_store()
                store.delete_source(source_id)
                store.export_source_inventory()
                store.close()
            except Exception:
                pass
        return ok

    def get_sources_by_tier(self, tier: str) -> list[dict]:
        inv = self.load_inventory()
        return [e for e in inv["sources"] if e.get("tier") == tier]

    def reconcile(self, live_sources: list[dict], inventory: dict) -> dict:
        live_ids = set()
        for s in live_sources:
            sid = s.get("id") or s.get("source_id") or s.get("sourceId", "")
            if sid:
                live_ids.add(str(sid))

        inv_ids = {e["nlm_source_id"] for e in inventory.get("sources", [])}

        return {
            "missing_remote": sorted(inv_ids - live_ids),
            "missing_local": sorted(live_ids - inv_ids),
            "synced": sorted(inv_ids & live_ids),
        }

    def prune_expired(self) -> list[str]:
        inv = self.load_inventory()
        now = datetime.now(timezone.utc)
        deleted = []
        keep = []
        for entry in inv["sources"]:
            exp = entry.get("expires_at")
            if exp and datetime.fromisoformat(exp) < now:
                try:
                    self._runner.source_delete(self._alias, entry["nlm_source_id"])
                    deleted.append(entry["nlm_source_id"])
                except NLMError:
                    keep.append(entry)
            else:
                keep.append(entry)
        inv["sources"] = keep
        self.save_inventory(inv)
        return deleted


def main():
    parser = argparse.ArgumentParser(description="Source lifecycle manager")
    sub = parser.add_subparsers(dest="command")

    u = sub.add_parser("upload")
    u.add_argument("path")
    u.add_argument("--title", required=True)
    u.add_argument("--tier", required=True, choices=["tier1", "tier2", "tier3"])

    d = sub.add_parser("delete")
    d.add_argument("source_id")

    sub.add_parser("reconcile")
    sub.add_parser("prune")
    sub.add_parser("inventory")

    args = parser.parse_args()
    manager = SourceManager()

    if args.command == "upload":
        content = Path(args.path).read_text()
        sid = manager.upload_source(content, args.title, args.tier, origin_path=args.path)
        print(f"Uploaded: {sid}")
    elif args.command == "delete":
        manager.delete_source(args.source_id)
    elif args.command == "reconcile":
        inv = manager.load_inventory()
        live = manager._runner.source_list(manager._alias)
        print(yaml.dump(manager.reconcile(live, inv), default_flow_style=False))
    elif args.command == "prune":
        deleted = manager.prune_expired()
        print(f"Pruned {len(deleted)} sources")
    elif args.command == "inventory":
        print(yaml.dump(manager.load_inventory(), default_flow_style=False))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
