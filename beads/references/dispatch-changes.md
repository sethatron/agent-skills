# Required Changes in /dispatch for Beads Integration

Applied by `/beads init` or `/dispatch-manager edit config`.
If automatic application fails, apply manually using these instructions.

## 1. workflow.yaml -- Add beads_sync Step

Add as the LAST step in the EOD workflow (after all other steps):

```yaml
  - id: beads_sync
    name: "Sync Beads Board"
    command: "br sync --flush-only"
    cwd: "~/.zsh/dispatch"
    on_blocker: notify_slack
    timeout_minutes: 1
    tags: [beads, eod, sync]
    enabled: true
```

Position: always the final EOD step, after optimus_nightly and notebook_update.

## 2. dispatch_runner.py -- Morning Board Summary [STUB TARGET]

When dispatch_runner.py is implemented, add `post_morning_hook()`:

```python
def post_morning_hook():
    """Append framework board summary after priority queue."""
    try:
        result = subprocess.run(
            ['br', 'count', '--by', 'priority', '-s', 'open'],
            cwd=DISPATCH_DIR, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            # Parse P0 and P1 counts from output
            # Append: "Framework board: <n> P0, <n> P1 issues open. /beads ready to review."
    except Exception:
        pass  # Skip silently on failure
```

## 3. hooks/pre_bash_guard.py -- br sync Tracking [STUB TARGET]

When the dispatch pre-bash hook is implemented, add br sync tracking:

Track `br_sync_run` (bool) in session state:
- Set to True when `br sync --flush-only` is observed in a Bash tool call
- On `git commit` in `~/.zsh/dispatch/` without `br_sync_run=True`:
  print warning: "Warning: br sync --flush-only has not been run this session."
- Warning only -- do not block the commit
