# Required Changes in /dispatch-manager for Beads Integration

Applied by `/beads init` or `/dispatch-manager edit config`.
If automatic application fails, apply manually using these instructions.

## 1. ecosystem.yaml -- Add beads Entry

Append under the `skills:` key:

```yaml
  beads:
    path: /Users/sethallen/agent-skills/beads
    symlink: ~/.claude/skills/beads
    config: config/beads.yaml
    dsi_type: B
    dependencies:
      - dispatch
    produces:
      - board_state
      - audit_report
    consumed_by:
      - dispatch
      - dispatch-manager
```

## 2. registry.yaml -- Add beads_board Contract

Append under the `contracts:` key:

```yaml
  beads_board:
    description: "Beads board state exported via br sync --flush-only"
    schema_version: "1.0"
    discovered_at: "2026-04-01"
    drift_notes: "No drift detected"
    required_fields:
      - id
      - title
      - status
      - priority
      - type
    custom_fields:
      - labels
      - parent
      - external_ref
      - created_at
      - closed_at
      - close_reason
    immutable_fields:
      - id
      - created_at
    extensible: true
    producer: beads
    consumers:
      - dispatch
      - dispatch-manager
```

## 3. change_manager.py -- Board Integration [STUB TARGET]

When change_manager.py is implemented, add these functions:

### create_skill_epic(slug, skill_dir)

Called after Step 4 of new skill registration:

```python
def create_skill_epic(slug: str, skill_dir: Path):
    """Create epic and stub issues for a newly registered skill."""
    # 1. Create epic
    subprocess.run(['br', 'create', f'[ENG] {slug}', '-t', 'epic', '-p', '2',
                    '-l', f'scope:{slug},source:scaffold'],
                   cwd=DISPATCH_DIR)
    # 2. Scan scripts/ for stubs
    # 3. Create stub issue for each
    # 4. br sync --flush-only
```

### close_stub_issues(slug, implemented_scripts)

Called after Step 6 of upgrade protocol:

```python
def close_stub_issues(slug: str, implemented_scripts: list[str]):
    """Close beads issues for scripts that were implemented in an upgrade."""
    for script in implemented_scripts:
        # Find issue by title match
        # br close <id> -r 'Implemented in upgrade v<version>'
```

### create_rollback_bug(skill, from_ver, to_ver, reason)

Called after Rollback Step 4:

```python
def create_rollback_bug(skill: str, from_ver: str, to_ver: str, reason: str):
    """Create bug issue for a rollback event."""
    subprocess.run(['br', 'create', f'Rollback: {skill} reverted to v{to_ver}',
                    '-t', 'bug', '-p', '1',
                    '-l', f'scope:{skill},source:operator,kind:bug',
                    '--description', f'Rolled back from v{from_ver} to v{to_ver}. Reason: {reason}'],
                   cwd=DISPATCH_DIR)
```

## 4. optimus_manager.py -- Finding Sync [STUB TARGET]

When optimus_manager.py is implemented, add:

### sync_finding_to_beads(finding)

Called in process_new_findings() for HIGH/CRITICAL:

```python
def sync_finding_to_beads(finding: dict):
    """Create beads issue for a new Optimus finding."""
    priority_map = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    p = priority_map.get(finding['severity'], 2)
    subprocess.run(['br', 'create', finding['title'], '-t', 'task', '-p', str(p),
                    '-l', f"scope:{finding['affected_skill']},source:optimus,kind:improvement",
                    '--external-ref', finding['id'],
                    '--description', finding['description']],
                   cwd=DISPATCH_DIR)
```

### close_finding_in_beads(finding_id, summary)

Called after mark_implemented():

```python
def close_finding_in_beads(finding_id: str, summary: str):
    """Close beads issue matching an Optimus finding."""
    # Search by external-ref
    # br close <id> -r f'Implemented: {summary}'
```

## 5. dsi_validator.py -- Violation Reporting [STUB TARGET]

When DSI validation finds a failure, add:

```python
def report_violation_to_beads(skill: str, requirement: str):
    """Create bug issue for a DSI validation failure."""
    # Check if open issue exists for this skill + requirement
    # If not: br create 'DSI violation: {skill} fails {requirement}'
    #         -t bug -p 1 -l 'scope:{skill},source:audit,kind:bug,layer:skill-md'
```
