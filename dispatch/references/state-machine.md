# Task State Machine

## States

| State | Description |
|-------|-------------|
| PENDING | Task created, not yet started |
| IN_PROGRESS | Operator actively working on task |
| BLOCKED | Work paused due to external dependency |
| IN_REVIEW | MR submitted, awaiting review |
| COMPLETE | Task finished |
| DEFERRED | Carried forward to next day |
| ABANDONED | Dropped (requires reason) |

## Transitions

```
PENDING ──────→ IN_PROGRESS     /dispatch task start <id>
IN_PROGRESS ──→ BLOCKED         /dispatch task block <id> --reason "..."
BLOCKED ──────→ IN_PROGRESS     /dispatch task unblock <id>
IN_PROGRESS ──→ IN_REVIEW       /dispatch task submit <id>
IN_REVIEW ────→ COMPLETE        /dispatch task close <id>
any ──────────→ DEFERRED        /dispatch task defer <id>
any ──────────→ ABANDONED       /dispatch task abandon <id> --reason "..."
```

## Rules

- All transitions logged to step_log with timestamp, previous_status, new_status
- All transitions send Slack notification unless --quiet
- DEFERRED/IN_PROGRESS at EOD auto-carried to next business day
- COMPLETE triggers Optimus check (all tasks done? run now : queue for EOD)
- ABANDONED requires --reason (never silently dropped)

## Git Permission

- Per-task, per-day flag (never global)
- Default: false (git add/commit/push blocked by hook)
- Grant: `/dispatch task git-allow <jira-id>`
- Revoke: `/dispatch task git-revoke <jira-id>`
- Checked by pre_bash_guard.py hook before every git write command
