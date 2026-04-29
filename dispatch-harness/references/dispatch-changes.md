# Dispatch Changes for dispatch-harness

These changes apply to `dispatch/scripts/dispatch_runner.py` and `session.yaml`.

**NOTE:** dispatch_runner.py is currently a stub (all functions raise NotImplementedError).
These changes are instructions for when it is implemented. Marked [STUB TARGET].

## 1. Checkpoint-Resume [STUB TARGET]

### 1a. session.yaml Schema Extension

Add `checkpoints` array to session.yaml:

```yaml
checkpoints:
  - step_id: morning_briefing_load
    completed_at: "2026-04-01T08:12:34-07:00"
    outcome: success   # success | partial | failed | skipped
    artifacts_produced:
      - ~/.zsh/dispatch/notebook/morning_briefing.md
    verify_result: pass  # pass | fail | skipped
```

### 1b. New Functions in dispatch_runner.py

```python
import fcntl

def write_checkpoint(session_path: Path, step_id: str, outcome: str,
                     artifacts: list[str], verify_result: str) -> None:
    """Atomically append to session.yaml checkpoints[] using file lock."""
    with open(session_path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = yaml.safe_load(f) or {}
        if "checkpoints" not in data:
            data["checkpoints"] = []
        data["checkpoints"].append({
            "step_id": step_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
            "artifacts_produced": artifacts,
            "verify_result": verify_result,
        })
        f.seek(0)
        yaml.dump(data, f, default_flow_style=False)
        f.truncate()
        fcntl.flock(f, fcntl.LOCK_UN)


def get_completed_step_ids(session_path: Path) -> list[str]:
    """Return step_ids with outcome in [success, partial, skipped]."""
    data = yaml.safe_load(session_path.read_text()) or {}
    return [
        cp["step_id"]
        for cp in data.get("checkpoints", [])
        if cp.get("outcome") in ("success", "partial", "skipped")
    ]


def should_skip_step(step_id: str, session_path: Path) -> bool:
    return step_id in get_completed_step_ids(session_path)
```

### 1c. Step Execution Loop Modification

In `run_morning_workflow()`, change the step loop:

```python
# BEFORE (current stub target):
for step in workflow_steps:
    result = execute_step(step)

# AFTER:
for step in workflow_steps:
    if should_skip_step(step["id"], session_path):
        print(f"  Skipping {step['id']} (already completed)")
        continue
    result = execute_step(step)
    write_checkpoint(
        session_path, step["id"], result.outcome,
        result.artifacts, result.verify_result
    )
```

### 1d. Restart Prompt Behavior

In `get_or_create_session()`:

```python
# On session restart within same calendar day:
existing = find_today_session()
if existing and existing.get("checkpoints"):
    completed = get_completed_step_ids(existing_path)
    next_step = find_next_step(workflow_steps, completed)
    # Prompt operator:
    # "Found incomplete session with N completed steps.
    #  Resume from <next_step_id>? [Y/n]"
    # Y: skip completed steps
    # N: start fresh (clear checkpoints)

    # A step with outcome=failed is NOT skipped on resume (retried).
    # A step with outcome=success or skipped IS skipped.
```

## 2. Telemetry Digest Trigger [STUB TARGET]

In `run_eod_workflow()`, BEFORE the Optimus invocation:

```python
# Generate telemetry digest for Optimus
digest_script = Path.home() / "agent-skills" / "dispatch-harness" / "scripts" / "telemetry_builder.py"
if digest_script.exists():
    try:
        subprocess.run(
            ["python3", str(digest_script)],
            timeout=60,
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Non-blocking; Optimus runs without digest
```

Insert this BEFORE `invoke_optimus()` or the Optimus cron trigger in `run_eod_workflow()`.
