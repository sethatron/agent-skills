#!/usr/bin/env python3
"""
Init orchestrator — 13-step guided initialization for dispatch-notebook.

Usage:
    python scripts/init_runner.py [--dry-run] [--skip-queries] [--skip-integration]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

SKILL_DIR = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = Path.home() / ".zsh" / "dispatch" / "notebook"
DISPATCH_DIR = Path.home() / ".zsh" / "dispatch"
WORKFLOW_PATH = DISPATCH_DIR / "workflow.yaml"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from nlm_runner import NLMRunner, NLMError, NLMAuthError
from source_renderer import SourceRenderer
from source_manager import SourceManager


def _log(step: int, msg: str):
    print(f"  [{step:02d}/13] {msg}")


class InitRunner:
    def __init__(self, dry_run: bool = False, skip_queries: bool = False, skip_integration: bool = False):
        self.dry_run = dry_run
        self.skip_queries = skip_queries
        self.skip_integration = skip_integration
        self._runner = NLMRunner()
        self._renderer = SourceRenderer()
        self._manager = None
        self._notebook_id = None
        self._config = yaml.safe_load((SKILL_DIR / "config" / "notebook.yaml").read_text()) or {}
        self._alias = self._config.get("notebook_alias", "dispatch")
        self._stats = {
            "tier1_uploaded": 0, "tier1_skipped": 0, "tier1_failed": 0,
            "tier2_uploaded": 0, "tier3_uploaded": 0,
            "queries_run": 0, "queries_failed": 0,
        }

    def execute(self) -> dict:
        print("\n=== dispatch-notebook init ===\n")
        if self.dry_run:
            print("  [DRY RUN] No changes will be made.\n")

        if not self.step_01_auth_check():
            return {"success": False, "error": "auth_failed"}

        reuse = self.step_02_check_alias()
        if not reuse:
            if not self.step_03_create_notebook():
                return {"success": False, "error": "notebook_creation_failed"}
        else:
            _log(3, f"Reusing existing notebook: {self._notebook_id}")

        self.step_04_create_dirs()
        self._manager = SourceManager()

        self.step_05_push_tier1()
        self.step_06_push_tier2()
        self.step_07_push_tier3()

        if not self.skip_queries:
            self.step_08_generate_briefing()
        else:
            _log(8, "Skipped (--skip-queries)")

        if not self.skip_integration:
            self.step_09_add_workflow_steps()
            self.step_10_apply_dispatch_changes()
            self.step_11_apply_manager_changes()
            self.step_12_register_skill()
        else:
            _log(9, "Skipped (--skip-integration)")
            _log(10, "Skipped")
            _log(11, "Skipped")
            _log(12, "Skipped")

        self.step_13_final_validation()

        print("\n=== Init complete ===\n")
        self._print_summary()
        return {"success": True, "stats": self._stats, "notebook_id": self._notebook_id}

    def step_01_auth_check(self) -> bool:
        _log(1, "Checking nlm authentication...")
        if self._runner.login_check():
            _log(1, "Authenticated.")
            return True
        _log(1, "NOT AUTHENTICATED. Run: nlm login")
        return False

    def step_02_check_alias(self) -> bool:
        _log(2, "Checking for existing dispatch alias...")
        existing = self._runner.alias_get(self._alias)
        if existing:
            self._notebook_id = existing
            _log(2, f"Found existing alias -> {existing}")
            nb_id_path = NOTEBOOK_DIR / "notebook_id"
            if not nb_id_path.exists() and not self.dry_run:
                nb_id_path.parent.mkdir(parents=True, exist_ok=True)
                nb_id_path.write_text(existing)
            return True
        _log(2, "No existing alias. Will create new notebook.")
        return False

    def step_03_create_notebook(self) -> bool:
        _log(3, "Creating notebook: Dispatch Framework Intelligence")
        if self.dry_run:
            self._notebook_id = "dry-run-id"
            return True
        try:
            self._notebook_id = self._runner.notebook_create("Dispatch Framework Intelligence")
            _log(3, f"Created notebook: {self._notebook_id}")
            self._runner.alias_set(self._alias, self._notebook_id)
            _log(3, f"Alias '{self._alias}' -> {self._notebook_id}")
            nb_id_path = NOTEBOOK_DIR / "notebook_id"
            nb_id_path.parent.mkdir(parents=True, exist_ok=True)
            nb_id_path.write_text(self._notebook_id)
            return True
        except NLMError as e:
            _log(3, f"FAILED: {e}")
            return False

    def step_04_create_dirs(self):
        _log(4, "Ensuring directories exist...")
        if not self.dry_run:
            (NOTEBOOK_DIR / "staging").mkdir(parents=True, exist_ok=True)
            (NOTEBOOK_DIR / "query_cache").mkdir(parents=True, exist_ok=True)
        _log(4, "Directories ready.")

    def step_05_push_tier1(self):
        _log(5, "Pushing TIER 1 sources...")
        manifest_path = SKILL_DIR / "config" / "tier1_manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        sources = manifest.get("sources", [])

        for i, src in enumerate(sources, 1):
            title = src["title"]
            path = Path(src["path"])
            render_type = src["render"]

            if not path.exists():
                _log(5, f"  [{i}/{len(sources)}] SKIP (missing): {title}")
                self._stats["tier1_failed"] += 1
                continue

            try:
                if render_type == "yaml":
                    rendered = self._renderer.render_yaml_file(path, title)
                else:
                    rendered = self._renderer.render_skill_md(path)

                if self.dry_run:
                    staging_dir = NOTEBOOK_DIR / "staging"
                    staging_dir.mkdir(parents=True, exist_ok=True)
                    slug = title.lower().replace(" ", "_").replace("/", "_")[:60]
                    (staging_dir / f"{slug}.md").write_text(rendered)
                    _log(5, f"  [{i}/{len(sources)}] STAGED: {title}")
                    self._stats["tier1_skipped"] += 1
                    continue

                sid = self._manager.upload_source(rendered, title, "tier1", origin_path=str(path))
                _log(5, f"  [{i}/{len(sources)}] OK: {title} -> {sid[:12]}...")
                self._stats["tier1_uploaded"] += 1
            except NLMError as e:
                _log(5, f"  [{i}/{len(sources)}] FAILED: {title} — {e}")
                self._stats["tier1_failed"] += 1
            except Exception as e:
                _log(5, f"  [{i}/{len(sources)}] ERROR: {title} — {e}")
                self._stats["tier1_failed"] += 1

        _log(5, f"TIER 1 complete: {self._stats['tier1_uploaded']} uploaded, "
             f"{self._stats['tier1_skipped']} skipped, {self._stats['tier1_failed']} failed")

    def step_06_push_tier2(self):
        _log(6, "Checking for TIER 2 sources (Optimus reports)...")
        optimus_dir = DISPATCH_DIR / "optimus"
        if not optimus_dir.exists() or not list(optimus_dir.iterdir()):
            _log(6, "No Optimus reports found (expected for fresh install).")
            return
        _log(6, f"Found {len(list(optimus_dir.iterdir()))} files (upload not yet implemented for init).")

    def step_07_push_tier3(self):
        _log(7, "Checking for TIER 3 sources (session summaries)...")
        _log(7, "No session summaries found (expected for fresh install).")

    def step_08_generate_briefing(self):
        _log(8, "Generating morning briefing (5 queries)...")
        queries_path = SKILL_DIR / "queries" / "morning_briefing.yaml"
        query_defs = yaml.safe_load(queries_path.read_text())
        queries = query_defs.get("queries", [])

        results = {}
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        cache_dir = NOTEBOOK_DIR / "query_cache" / today
        cache_dir.mkdir(parents=True, exist_ok=True)

        for q in queries:
            qid = q["id"]
            question = q["question"]
            section = q["output_section"]
            timeout = q.get("timeout_seconds", 180)

            if self.dry_run:
                results[section] = f"[DRY RUN] Would query: {question[:60]}..."
                self._stats["queries_run"] += 1
                continue

            try:
                _log(8, f"  Querying: {q['name']}...")
                result = self._runner.notebook_query(self._alias, question, timeout=timeout)
                results[section] = result.answer

                cache_entry = (
                    f"---\n"
                    f"query_id: {qid}\n"
                    f"question: \"{question}\"\n"
                    f"asked_at: \"{datetime.now(timezone.utc).isoformat()}\"\n"
                    f"notebook_alias: {self._alias}\n"
                    f"sources_cited: {json.dumps(result.sources_used)}\n"
                    f"---\n\n"
                    f"{result.answer}\n"
                )
                (cache_dir / f"{qid}.md").write_text(cache_entry)
                self._stats["queries_run"] += 1
            except NLMError as e:
                _log(8, f"  FAILED: {q['name']} — {e}")
                results[section] = ""
                self._stats["queries_failed"] += 1

        env = Environment(loader=FileSystemLoader(str(SKILL_DIR / "templates")), keep_trailing_newline=True)
        template = env.get_template("briefing.md.j2")
        now = datetime.now(timezone.utc)
        briefing = template.render(
            generated_at=now.isoformat(),
            notebook_alias=self._alias,
            sources_count=self._stats["tier1_uploaded"],
            query_ids=[q["id"] for q in queries],
            date=now.strftime("%Y-%m-%d"),
            **{q["output_section"]: results.get(q["output_section"], "") for q in queries},
        )

        briefing_path = NOTEBOOK_DIR / "morning_briefing.md"
        if not self.dry_run:
            briefing_path.write_text(briefing)
        _log(8, f"Briefing written to {briefing_path}")

    def step_09_add_workflow_steps(self):
        _log(9, "Adding workflow steps...")
        if not WORKFLOW_PATH.exists():
            _log(9, "SKIP: workflow.yaml not found")
            return

        content = yaml.safe_load(WORKFLOW_PATH.read_text())
        steps = content.get("steps", [])
        schedule = content.get("schedule", {})
        modified = False

        step_ids = {s["id"] for s in steps}
        if "morning_briefing_load" not in step_ids:
            briefing_step = {
                "id": "morning_briefing_load",
                "name": "Morning Briefing Intelligence",
                "skill": "/dispatch-notebook",
                "args": "briefing",
                "description": "Load NotebookLM intelligence briefing into session context",
                "on_blocker": "log_and_continue",
                "timeout_minutes": 2,
                "tags": ["notebook", "morning"],
                "enabled": True,
            }
            steps.insert(0, briefing_step)
            content["steps"] = steps
            modified = True
            _log(9, "  Added morning_briefing_load step (position: first)")

        if "notebook_update" not in schedule:
            schedule["notebook_update"] = {
                "cron": "0 22 * * 1-5",
                "command": "dispatch-notebook update",
                "approval_required": True,
                "approved": False,
            }
            content["schedule"] = schedule
            modified = True
            _log(9, "  Added notebook_update schedule entry")

        if modified and not self.dry_run:
            WORKFLOW_PATH.write_text(yaml.dump(content, default_flow_style=False, sort_keys=False))
        _log(9, "Workflow steps configured.")

    def step_10_apply_dispatch_changes(self):
        _log(10, "Applying dispatch SKILL.md notebook hooks...")
        dispatch_skill = Path.home() / "agent-skills" / "dispatch" / "SKILL.md"
        if not dispatch_skill.exists():
            _log(10, "SKIP: dispatch/SKILL.md not found")
            return

        content = dispatch_skill.read_text()
        marker = "## NotebookLM Integration Hooks"
        if marker in content:
            _log(10, "Hooks already present. Skipping.")
            return

        hook_section = """

## NotebookLM Integration Hooks

### Post-bottleneck_scan Hook (CRITICAL/HIGH only)

After bottleneck_scan completes, for each CRITICAL or HIGH severity
bottleneck, invoke `/dispatch-notebook query` with BC-01 and BC-02
queries, substituting the bottleneck type. Append inline:

    [BOTTLENECK] <description>
    [NOTEBOOK] Prior resolution: <BC-01 summary, 2-3 sentences>
    [NOTEBOOK] Prevention:       <BC-02 summary, 2-3 sentences>

On query failure: log error, display alert without notebook context.
Never block the bottleneck notification on a query failure.
MEDIUM severity bottlenecks do NOT trigger live queries.

### Task Start Notebook Query

On `/dispatch task start`, if the task has tags, invoke
`/dispatch-notebook query` with TC-01, substituting task.tags.
Timeout: 30 seconds. Display 2-3 sentence summary as [NOTEBOOK]
context block before task confirmation. Skip silently if no tags,
cache hit within 20 hours, or query failure.

### Post-/compact Briefing Re-injection

After any /compact event, re-inject the morning briefing summary
by reading `~/.zsh/dispatch/notebook/morning_briefing.md` and
compressing to max 5 bullets per section. This is a file read only —
no live NotebookLM query. The briefing is the persistent intelligence
anchor that survives context compaction.

### Briefing Staleness

If the morning briefing is older than 48 hours or missing:
inject warning "[NOTEBOOK] Briefing stale (>48h). Run /dispatch-notebook update."
Never block on a stale briefing.
"""

        if not self.dry_run:
            dispatch_skill.write_text(content + hook_section)
        _log(10, "Notebook hooks appended to dispatch/SKILL.md.")

    def step_11_apply_manager_changes(self):
        _log(11, "Applying dispatch-manager config changes...")
        eco_path = Path.home() / "agent-skills" / "dispatch-manager" / "config" / "ecosystem.yaml"
        reg_path = Path.home() / "agent-skills" / "dispatch-manager" / "contracts" / "registry.yaml"

        if eco_path.exists():
            eco = yaml.safe_load(eco_path.read_text())
            skills = eco.get("skills", {})
            if "dispatch-notebook" not in skills:
                skills["dispatch-notebook"] = {
                    "path": str(SKILL_DIR),
                    "symlink": "~/.claude/skills/dispatch-notebook",
                    "config": "config/notebook.yaml",
                    "dsi_type": "C",
                    "dependencies": ["dispatch"],
                    "produces": ["update_log", "morning_briefing"],
                    "consumed_by": ["dispatch", "dispatch-manager"],
                }
                eco["skills"] = skills
                eco["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if not self.dry_run:
                    eco_path.write_text(yaml.dump(eco, default_flow_style=False, sort_keys=False))
                _log(11, "  Added dispatch-notebook to ecosystem.yaml")
            else:
                _log(11, "  dispatch-notebook already in ecosystem.yaml")

        if reg_path.exists():
            reg = yaml.safe_load(reg_path.read_text())
            contracts = reg.get("contracts", {})
            if "notebook_artifact" not in contracts:
                contracts["notebook_artifact"] = {
                    "description": "Artifact frontmatter for dispatch-notebook update_log.yaml",
                    "schema_version": "1.0",
                    "discovered_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "drift_notes": "No drift detected",
                    "required_fields": ["skill_name", "skill_version", "produced_at", "artifact_path", "status"],
                    "custom_fields": [
                        "update_id", "notebook_alias", "sources_added", "sources_deleted",
                        "sources_unchanged", "sources_errored", "tier_summary",
                        "duration_seconds", "queries_executed", "briefing_path", "errors",
                    ],
                    "immutable_fields": [
                        "skill_name", "skill_version", "produced_at",
                        "artifact_path", "status", "update_id", "notebook_alias",
                    ],
                    "extensible": True,
                    "producer": "dispatch-notebook",
                    "consumers": ["dispatch"],
                }
                reg["contracts"] = contracts
                if not self.dry_run:
                    reg_path.write_text(yaml.dump(reg, default_flow_style=False, sort_keys=False))
                _log(11, "  Added notebook_artifact contract to registry.yaml")
            else:
                _log(11, "  notebook_artifact already in registry.yaml")

        _log(11, "Manager changes applied.")

    def step_12_register_skill(self):
        _log(12, "Verifying skill registration...")
        symlink = Path.home() / ".claude" / "skills" / "dispatch-notebook"
        checks = []
        checks.append(("Symlink exists", symlink.exists()))

        eco_path = Path.home() / "agent-skills" / "dispatch-manager" / "config" / "ecosystem.yaml"
        if eco_path.exists():
            eco = yaml.safe_load(eco_path.read_text())
            checks.append(("Ecosystem entry", "dispatch-notebook" in eco.get("skills", {})))

        reg_path = Path.home() / "agent-skills" / "dispatch-manager" / "contracts" / "registry.yaml"
        if reg_path.exists():
            reg = yaml.safe_load(reg_path.read_text())
            checks.append(("Contract entry", "notebook_artifact" in reg.get("contracts", {})))

        for name, ok in checks:
            status = "OK" if ok else "MISSING"
            _log(12, f"  {name}: {status}")

        all_ok = all(ok for _, ok in checks)
        _log(12, f"Registration: {'COMPLETE' if all_ok else 'INCOMPLETE'}")

    def step_13_final_validation(self):
        _log(13, "Running final validation...")
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, str(SKILL_DIR / "scripts" / "check_env.py"), "--json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                passed = sum(1 for c in data.get("checks", []) if c.get("ok"))
                total = len(data.get("checks", []))
                _log(13, f"Environment: {passed}/{total} checks passed")
            else:
                _log(13, f"Environment check returned non-zero: {result.stderr[:100]}")
        except Exception as e:
            _log(13, f"Could not run check_env: {e}")

    def _print_summary(self):
        print("  Summary:")
        print(f"    Notebook ID:    {self._notebook_id}")
        print(f"    Alias:          {self._alias}")
        print(f"    TIER 1:         {self._stats['tier1_uploaded']} uploaded, "
              f"{self._stats['tier1_skipped']} skipped, {self._stats['tier1_failed']} failed")
        print(f"    TIER 2:         {self._stats['tier2_uploaded']} uploaded")
        print(f"    TIER 3:         {self._stats['tier3_uploaded']} uploaded")
        print(f"    Queries:        {self._stats['queries_run']} run, {self._stats['queries_failed']} failed")
        print()


def main():
    parser = argparse.ArgumentParser(description="dispatch-notebook init orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Stage files but don't upload or modify")
    parser.add_argument("--skip-queries", action="store_true", help="Skip morning briefing generation")
    parser.add_argument("--skip-integration", action="store_true", help="Skip steps 9-12 (workflow/SKILL.md changes)")
    args = parser.parse_args()

    runner = InitRunner(
        dry_run=args.dry_run,
        skip_queries=args.skip_queries,
        skip_integration=args.skip_integration,
    )
    result = runner.execute()
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
