# dispatch Architecture


## Architecture

This skill uses a two-layer architecture:

**Layer 1 — SKILL.md** (this file): Orchestration brain, workflow DSL, agent roles,
sub-skill contracts, notification schema. Loaded into Claude Code context.

**Layer 2 — Python scripts + state store**: Execution, persistence, hooks.
Durable across sessions. SQLite at `~/.zsh/dispatch/dispatch.db`.

This skill generates scaffolding on first run. It is not fully functional
without the generated scripts.


## State Store

SQLite at `~/.zsh/dispatch/dispatch.db` with WAL mode.

Tables: tasks, sessions, step_log, bash_log, notifications, optimus_runs, bottlenecks.

Schema managed by `scripts/state_store.py`. Init: `python scripts/state_store.py init`.

Human-readable artifacts derived from DB and written to filesystem (see Directory Structure).


## Directory Structure

```
~/.zsh/dispatch/
├── dispatch.db
├── workflow.yaml
├── cron/
├── optimus/                        (Optimus knowledge base)
│   ├── knowledge.md
│   ├── resolved_findings.md
│   ├── pattern_library.yaml
│   └── pending_improvements.yaml
└── {YYYY}/{MM}/{DD}/
    ├── session.yaml
    ├── task.yaml
    ├── carry_forward.yaml
    ├── bottlenecks.yaml
    ├── optimus_brief.md
    ├── optimus_report.md
    ├── slack_log.yaml
    └── tasks/{jira-id}/
        ├── task_log.md
        ├── bash_commands.log
        ├── file_changes.log
        └── mr_review/              (symlinks to review.md artifacts)
```


## Context Window Management

- Session start: load only session.yaml, task.yaml, carry_forward.yaml, workflow steps
- Sub-skill artifacts: summarized on load, full content on demand
- Compact at breakpoints: after each step, before sub-skills, before Optimus
- Optimus runs in isolated subprocess (no shared context)
- Large bash logs auto-summarized at 500 lines


## Hooks

Installed to `~/.claude/hooks/` during scaffold:
- `pre_bash_guard.py` — blocks unauthorized git ops, logs all commands
- `post_bash.py` — logs command, exit code, duration
- `post_write.py` — logs file writes
- `post_edit.py` — logs file edits with diff size
