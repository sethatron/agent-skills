# Required Changes in /dispatch-manager for Notebook Integration

All changes below are applied by `/dispatch-notebook init`.
If automatic application fails, apply manually using these instructions.

NOTE: skill_author.py, optimus_manager.py, and change_manager.py are
currently stubs (all methods raise NotImplementedError). Sections marked
[STUB TARGET] describe design specifications for when implemented.

dispatch-manager NEVER calls nlm directly. All notebook operations route
through /dispatch-notebook push or /dispatch-notebook query CLI.

## 1. ecosystem.yaml — Add dispatch-notebook Entry

Append under the `skills:` key in
`/Users/sethallen/agent-skills/dispatch-manager/config/ecosystem.yaml`:

```yaml
  dispatch-notebook:
    path: /Users/sethallen/agent-skills/dispatch-notebook
    symlink: ~/.claude/skills/dispatch-notebook
    config: config/notebook.yaml
    dsi_type: C
    dependencies:
      - dispatch
    produces:
      - update_log
      - morning_briefing
    consumed_by:
      - dispatch
      - dispatch-manager
```

## 2. registry.yaml — Add notebook_artifact Contract

Append under the `contracts:` key in
`/Users/sethallen/agent-skills/dispatch-manager/contracts/registry.yaml`:

```yaml
  notebook_artifact:
    description: "Artifact frontmatter for dispatch-notebook update_log.yaml"
    schema_version: "1.0"
    discovered_at: "2026-04-01"
    drift_notes: "No drift detected"
    required_fields:
      - skill_name
      - skill_version
      - produced_at
      - artifact_path
      - status
    custom_fields:
      - update_id
      - notebook_alias
      - sources_added
      - sources_deleted
      - sources_unchanged
      - sources_errored
      - tier_summary
      - duration_seconds
      - queries_executed
      - briefing_path
      - errors
    immutable_fields:
      - skill_name
      - skill_version
      - produced_at
      - artifact_path
      - status
      - update_id
      - notebook_alias
    extensible: true
    producer: dispatch-notebook
    consumers:
      - dispatch
```

## 3. skill_author.py — Pre-Interview Notebook Brief [STUB TARGET]

When implemented, add `run_sc_queries()` before Phase 1 prompt in
`run_interview()`:

```python
def run_sc_queries(self) -> dict | None:
    """Query NotebookLM for skill creation context."""
    try:
        # Route through dispatch-notebook CLI, not nlm directly
        # Execute SC-01, SC-02, SC-03 queries
        # Return dict with dsi_failures, integration_pitfalls, existing_patterns
    except Exception:
        return None  # Non-blocking
```

Display before Phase 1 interview:
```
[NOTEBOOK] Intelligence Brief — New Skill Context
Common DSI failures:  <SC-01, 3 bullets>
Integration pitfalls: <SC-02, 3 bullets>
Useful patterns:      <SC-03, 3 bullets>
Proceeding to interview...
```

On failure: log, display "Notebook unavailable", continue. Never blocks.

## 4. optimus_manager.py — Pre-Implementation Research [STUB TARGET]

When implemented, add to `build_implementation_plan()`:

```python
def run_pi_queries(self, finding: dict) -> dict | None:
    """Query NotebookLM for prior implementation context."""
    # Execute PI-01 with category=finding["category"]
    # Execute PI-02 with finding_title=finding["title"]
    # Return dict with prior_attempts, best_practices
```

Append to implementation plan before confirmation:
```
[NOTEBOOK] Research — Finding: <id>
Prior attempts:  <PI-01 summary>
Best practices:  <PI-02 summary>
```

Also add `push_to_notebook(resolved_findings_path)` after `mark_implemented()`:
- Path: `~/.zsh/dispatch/optimus/resolved_findings.md`
- Fire-and-forget. On failure: log "notebook sync pending".

## 5. change_manager.py — Post-Change Source Refresh [STUB TARGET]

When implemented, add notebook push calls at these protocol steps:

**Step 4 (post-ecosystem registration):**
```python
# After register_skill() succeeds:
push_to_notebook(f"{skill_dir}/SKILL.md")
```

**Step 6 (post-apply, for all skill file changes):**
```python
# After apply() succeeds:
push_to_notebook(f"{skill_dir}/SKILL.md")
# If contract was updated:
push_to_notebook(f"{dispatch_manager_dir}/contracts/registry.yaml")
```

**Rollback Step 4 (post-restore):**
```python
# After restore_backup() succeeds:
push_to_notebook(f"{skill_dir}/SKILL.md")
```

All pushes are fire-and-forget. On failure: log "notebook sync pending"
to CHANGELOG.md and continue. Pending syncs visible in
`/dispatch-notebook status` and retried on next `/dispatch-notebook update`.
