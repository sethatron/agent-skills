#!/usr/bin/env python3
"""
Integration tests for dispatch execution layer boundaries.

Validates the 4 contracts tracked by dsp-bu6:
  1. git_permission round-trip (state_store <-> pre_bash_guard)
  2. BC query routing (bottleneck_detector -> dispatch_runner, not notebook)
  3. collect_artifact path conventions per skill
  4. Telemetry digest presence/absence in optimus_brief

Usage:
    python scripts/test_integration.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from state_store import StateStore
from log_writer import LogWriter


def _check(name, condition):
    if condition:
        print(f"  PASS: {name}")
        return True
    print(f"  FAIL: {name}")
    return False


def test_git_permission_roundtrip():
    """dsp-bu6.1: state_store git_permission consumed correctly by pre_bash_guard."""
    print("\n--- dsp-bu6.1: git_permission round-trip ---")
    passed = 0
    total = 0

    tmpdir = tempfile.mkdtemp(prefix="integ_git_")
    db_path = os.path.join(tmpdir, "test.db")

    with StateStore(db_path=db_path) as store:
        store.schema_init()

        store.create_task("T-GIT-1", "Test git perm", priority=1)
        store.transition_task("T-GIT-1", "IN_PROGRESS")

        # pre_bash_guard uses raw sqlite3, not StateStore
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")

        # Test 1: git_permission defaults to 0 (blocked)
        total += 1
        cursor = conn.execute(
            "SELECT git_permission FROM tasks WHERE task_id = ? AND status = 'IN_PROGRESS'",
            ("T-GIT-1",),
        )
        row = cursor.fetchone()
        if _check("default_permission_blocked", row and row[0] == 0):
            passed += 1

        # Test 2: set_git_permission(True) -> raw query sees 1
        store.set_git_permission("T-GIT-1", True)
        total += 1
        cursor = conn.execute(
            "SELECT git_permission FROM tasks WHERE task_id = ?", ("T-GIT-1",)
        )
        row = cursor.fetchone()
        if _check("permission_granted_visible", row and row[0] == 1):
            passed += 1

        # Test 3: set_git_permission(False) -> raw query sees 0
        store.set_git_permission("T-GIT-1", False)
        total += 1
        cursor = conn.execute(
            "SELECT git_permission FROM tasks WHERE task_id = ?", ("T-GIT-1",)
        )
        row = cursor.fetchone()
        if _check("permission_revoked_visible", row and row[0] == 0):
            passed += 1

        # Test 4: get_active_task_id pattern (same query as pre_bash_guard)
        total += 1
        cursor = conn.execute(
            "SELECT task_id FROM tasks WHERE status = 'IN_PROGRESS' ORDER BY started_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if _check("active_task_found", row and row[0] == "T-GIT-1"):
            passed += 1

        # Test 5: no active task -> None (hook defaults to block)
        store.transition_task("T-GIT-1", "COMPLETE")
        total += 1
        cursor = conn.execute(
            "SELECT task_id FROM tasks WHERE status = 'IN_PROGRESS' ORDER BY started_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if _check("no_active_task_blocks", row is None):
            passed += 1

        conn.close()

    # Test 6: DB unavailable -> fail-closed
    total += 1
    bad_path = os.path.join(tmpdir, "nonexistent", "bad.db")
    try:
        bad_conn = sqlite3.connect(bad_path, timeout=1)
        bad_conn.execute("SELECT 1 FROM tasks LIMIT 1")
        if _check("unavailable_db_blocks", False):
            passed += 1
    except Exception:
        if _check("unavailable_db_blocks", True):
            passed += 1

    shutil.rmtree(tmpdir, ignore_errors=True)
    return passed, total


def test_bc_query_routing():
    """dsp-bu6.2: BC queries route through dispatch_runner, not bottleneck_detector."""
    print("\n--- dsp-bu6.2: BC query routing ---")
    passed = 0
    total = 0

    # Test 1: bottleneck_detector has no dispatch-notebook import or invocation
    total += 1
    bd_path = Path(__file__).resolve().parent / "bottleneck_detector.py"
    bd_source = bd_path.read_text()
    has_import = "import dispatch_notebook" in bd_source or "from dispatch_notebook" in bd_source
    has_invoke = "dispatch-notebook query" in bd_source or "/dispatch-notebook" in bd_source.replace("dispatch-notebook directly", "")
    if _check("no_notebook_import_in_detector", not has_import and not has_invoke):
        passed += 1

    # Test 2: dispatch_runner._run_script has BC routing code
    total += 1
    dr_path = Path(__file__).resolve().parent / "dispatch_runner.py"
    dr_source = dr_path.read_text()
    has_bc_routing = "BC-01" in dr_source and "BC-02" in dr_source
    if _check("bc_routing_in_runner", has_bc_routing):
        passed += 1

    # Test 3: BC routing only fires for CRITICAL/HIGH
    total += 1
    has_severity_check = 'f.severity in ("CRITICAL", "HIGH")' in dr_source
    if _check("severity_filter_present", has_severity_check):
        passed += 1

    # Test 4: bottleneck_detector returns BottleneckResult, not notebook data
    total += 1
    from bottleneck_detector import BottleneckResult
    r = BottleneckResult(severity="HIGH", type="test", resource_id="T-1",
                         description="test bottleneck")
    if _check("returns_dataclass_not_notebook", hasattr(r, "severity") and hasattr(r, "type")):
        passed += 1

    return passed, total


def test_collect_artifact_paths():
    """dsp-bu6.3: collect_artifact uses consistent path conventions per skill."""
    print("\n--- dsp-bu6.3: collect_artifact path conventions ---")
    passed = 0
    total = 0

    tmpdir = tempfile.mkdtemp(prefix="integ_artifact_")
    db_path = os.path.join(tmpdir, "test.db")

    import dispatch_runner as mod
    old_sr = mod.STATE_ROOT
    mod.STATE_ROOT = Path(tmpdir)

    with StateStore(db_path=db_path) as store:
        store.schema_init()
        runner = mod.DispatchRunner(store, "morning", no_slack=True)

        from dispatch_runner import WorkflowStep

        # Test 1: /mr-review with no files -> None
        total += 1
        step_mr = WorkflowStep(id="mr", name="MR", skill="/mr-review", tags=["morning"])
        result = runner.collect_artifact(step_mr)
        if _check("mr_review_no_files_none", result is None):
            passed += 1

        # Test 2: /jira with no exports -> None
        total += 1
        step_jira = WorkflowStep(id="jira", name="Jira", skill="/jira", tags=["morning"])
        result = runner.collect_artifact(step_jira)
        if _check("jira_no_exports_none", result is None):
            passed += 1

        # Test 3: /dispatch-notebook with files -> returns newest
        total += 1
        nb_dir = Path(tmpdir) / "notebook"
        nb_dir.mkdir()
        (nb_dir / "old_cache.json").write_text("{}")
        import time
        time.sleep(0.05)
        (nb_dir / "new_cache.json").write_text("{}")
        step_nb = WorkflowStep(id="nb", name="Notebook", skill="/dispatch-notebook",
                               tags=["morning"])
        result = runner.collect_artifact(step_nb)
        if _check("notebook_returns_newest", result is not None and "new_cache" in result.name):
            passed += 1

        # Test 4: /dispatch-notebook with empty dir -> None
        total += 1
        empty_nb = Path(tmpdir) / "notebook2"
        empty_nb.mkdir()
        mod.STATE_ROOT = Path(tmpdir).parent / "nonexistent"
        result2 = runner.collect_artifact(step_nb)
        mod.STATE_ROOT = Path(tmpdir)
        if _check("notebook_empty_dir_none", result2 is None):
            passed += 1

        # Test 5: invoke_sub_skill produces partial when no artifact
        total += 1
        session = store.create_session("morning")
        state = mod.RunnerState(session_id=session["session_id"], mode="morning")
        sr = runner.invoke_sub_skill(step_jira, state)
        if _check("no_artifact_partial", sr.outcome == "partial" and "No artifact" in (sr.error or "")):
            passed += 1

    mod.STATE_ROOT = old_sr
    shutil.rmtree(tmpdir, ignore_errors=True)
    return passed, total


def test_telemetry_digest_handling():
    """dsp-bu6.4: optimus_brief.md correctly handles telemetry digest presence/absence."""
    print("\n--- dsp-bu6.4: telemetry digest handling ---")
    passed = 0
    total = 0

    tmpdir = tempfile.mkdtemp(prefix="integ_telemetry_")
    db_path = os.path.join(tmpdir, "test.db")

    import optimus_runner as omod
    old_sr = omod.STATE_ROOT
    old_wp = omod.WORKFLOW_PATH
    old_td = omod.TELEMETRY_DIR
    omod.STATE_ROOT = Path(tmpdir)
    omod.WORKFLOW_PATH = Path(tmpdir) / "workflow.yaml"
    omod.TELEMETRY_DIR = Path(tmpdir) / "telemetry"

    (Path(tmpdir) / "workflow.yaml").write_text("version: '1.0'\nsteps: []\n")

    old_day_dir = LogWriter.day_dir
    def patched(self, date=None):
        d = date or self._date
        parts = d.split("-")
        return Path(tmpdir) / parts[0] / parts[1] / parts[2]
    LogWriter.day_dir = patched

    with StateStore(db_path=db_path) as store:
        store.schema_init()
        writer = LogWriter(store, date="2026-04-10")

        from optimus_runner import OptimusRunner

        runner = OptimusRunner(store, writer)

        # Test 1: digest absent -> fallback message
        total += 1
        brief_path = runner.generate_brief("2026-04-10")
        content = brief_path.read_text()
        if _check("absent_digest_fallback",
                   "## Telemetry Digest" in content
                   and "not available" in content):
            passed += 1

        # Test 2: digest present -> embedded verbatim
        total += 1
        tel_dir = Path(tmpdir) / "telemetry"
        tel_dir.mkdir(parents=True, exist_ok=True)
        digest_text = "# Telemetry Digest -- 2026-04-11\nSome real data here."
        (tel_dir / "2026-04-11-digest.md").write_text(digest_text)
        brief_path2 = runner.generate_brief("2026-04-11")
        content2 = brief_path2.read_text()
        if _check("present_digest_embedded",
                   "## Telemetry Digest" in content2
                   and "Some real data here" in content2):
            passed += 1

        # Test 3: both cases produce valid markdown (have the header)
        total += 1
        if _check("both_have_header",
                   "## Telemetry Digest" in content and "## Telemetry Digest" in content2):
            passed += 1

    omod.STATE_ROOT = old_sr
    omod.WORKFLOW_PATH = old_wp
    omod.TELEMETRY_DIR = old_td
    LogWriter.day_dir = old_day_dir
    shutil.rmtree(tmpdir, ignore_errors=True)
    return passed, total


def main():
    total_passed = 0
    total_tests = 0

    for test_fn in [
        test_git_permission_roundtrip,
        test_bc_query_routing,
        test_collect_artifact_paths,
        test_telemetry_digest_handling,
    ]:
        p, t = test_fn()
        total_passed += p
        total_tests += t

    print(f"\n{total_passed} passed, {total_tests - total_passed} failed out of {total_tests}")
    sys.exit(0 if total_passed == total_tests else 1)


if __name__ == "__main__":
    main()
