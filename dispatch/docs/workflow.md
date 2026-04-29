# dispatch Workflow Integration


## Workflow Engine

Workflow defined in `~/.zsh/dispatch/workflow.yaml`. The SKILL.md does not
hardcode steps — it reads them from this file on every invocation.

Steps with `skill:` invoke sub-skills (/mr-review, /jira).
Steps with `runner:` invoke Python scripts directly.
All steps are idempotent — re-running on same day detects completed checkpoint and skips.

Adding a new step requires only editing workflow.yaml. No SKILL.md changes needed.

### Sub-Skill Invocation

When invoking /mr-review or /jira:
1. Generate handoff context (task state, output dir)
2. Surface invocation block to operator
3. Sub-skill runs in same session
4. Collect artifact (review.md frontmatter or jira export)
5. Record outcome in step_log, symlink artifact into task dir

`JIRA_CALLER=dispatch` enforces FORCED READ-ONLY MODE on /jira.

### Human Gates

Defined in workflow.yaml. Pause after specified steps for operator confirmation.


## Task State Machine

```
PENDING → IN_PROGRESS → [BLOCKED] → IN_REVIEW → COMPLETE
                      → DEFERRED
                      → ABANDONED
```

All transitions logged. All transitions send Slack notification (unless --quiet).
See `references/state-machine.md` for full rules.

### Git Permission Gate

Default: false. Per-task, per-day.
Grant: `/dispatch task git-allow <jira-id>`
Hook `pre_bash_guard.py` checks dispatch.db before every git write command.

### Multi-Day Carry-Forward

DEFERRED/IN_PROGRESS tasks at EOD written to next day's `carry_forward.yaml`.
Morning boot reads carry-forward and recreates tasks with status preserved.


## Bottleneck Detection

`scripts/bottleneck_detector.py` evaluates blocking conditions:

**CRITICAL** (immediate Slack): MR review > 4h, unresponded Jira comment > 2h, stale pipeline failure > 1h
**HIGH** (next pause): MR 0 reviews > 24h, IN_REVIEW > 8h, blocking Jira ticket
**MEDIUM** (EOD summary): > 5 outstanding reviews, > 3 WIP tickets, task deferred > 2x


## Priority and Triage

At session start, generates prioritized work queue:
- **P1 CRITICAL**: Failing pipeline, blocked teammate, stale review > 4h
- **P2 HIGH**: Review comments to respond, unread @mentions, MR > 24h
- **P3 NORMAL**: Draft MRs, TO DO tickets, CC'd tickets
- **P4 LOW**: Informational comments, MRs with active reviews


## Period Reviews

- **Daily** (`/dispatch review day`): task disposition, bottlenecks, step performance, carry-forward
- **Weekly** (`/dispatch review week`): trends, recurring blockers, MR throughput, Jira velocity
- **Monthly** (`/dispatch review month`): month-over-month delta, improvement adoption, workflow evolution
