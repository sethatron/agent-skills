---
name: dispatch
version: "1.0.0"
dsi_type: "A"
description: >-
  Use this skill when the user says "start my day", "what do I need to work
  on", "what's blocking me", "what am I forgetting", "run my morning standup",
  "close out <jira-id>", "start working on <jira-id>", "how was my week",
  "send a dispatch update", "run the optimizer", or invokes /dispatch with any
  subcommand. Trigger on: "dispatch status", "task start", "task close", "task
  defer", "run optimus", "daily review", "weekly review", "monthly review",
  "generate cron", "dispatch scaffold", "priority queue", "what should I do
  next", "morning workflow", "end of day summary", "carry forward tasks".
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
  workflow: docs/workflow.md
---

┌────────────────────────── DISPATCH GUARDRAILS ─────────────────────────────┐
│  GIT — NEVER WITHOUT EXPLICIT TASK-LEVEL PERMISSION                        │
│    - git add / git commit / git push blocked by hook unless                 │
│      task has git_permission: true in dispatch.db                           │
│    - git_permission is per-task, per-day — never global                    │
│    - Grant with: /dispatch task git-allow <jira-id>                        │
│                                                                            │
│  JIRA — READ-ONLY FROM DISPATCH                                            │
│    - JIRA_CALLER=dispatch always set when invoking /jira skill             │
│    - Dispatch cannot approve Jira write operations                          │
│    - Write operations require the operator to invoke /jira directly        │
│                                                                            │
│  GITLAB — READ-ONLY FROM DISPATCH                                          │
│    - Dispatch invokes /mr-review in read-only mode                         │
│    - No GitLab comments, approvals, or merges from dispatch                │
│                                                                            │
│  CRON — OPERATOR APPROVAL REQUIRED                                         │
│    - No cron entry is installed without explicit /dispatch cron approve    │
│    - All cron jobs tracked in dispatch.db with approval timestamp          │
│                                                                            │
│  OPTIMUS — ANALYSIS ONLY                                                   │
│    - Optimus produces reports and recommendations only                     │
│    - Optimus does not modify workflow.yaml, dispatch.db, or crontab        │
│    - Operator implements all Optimus recommendations manually              │
└────────────────────────────────────────────────────────────────────────────┘

## Environment Pre-Validation

Run `scripts/check_env.py` first on every invocation:

```bash
python scripts/check_env.py [--verbose] [--json] [--fix]
```

Validates: Python 3.10+, packages, SQLite DB, directories, workflow.yaml,
Slack MCP, sibling skills (/mr-review, /jira), claude binary, hooks dir,
git binary.

## Subcommands

| Command | Description |
|---------|-------------|
| `/dispatch` | Full morning workflow |
| `/dispatch status` | Current day summary (no execution) |
| `/dispatch task start <id>` | Begin tracking a task |
| `/dispatch task close <id>` | Mark task complete, trigger Optimus |
| `/dispatch task defer <id>` | Carry task to next day |
| `/dispatch task block <id> --reason "..."` | Mark task blocked |
| `/dispatch task unblock <id>` | Resume blocked task |
| `/dispatch task submit <id>` | Move to IN_REVIEW |
| `/dispatch task git-allow <id>` | Grant git permission |
| `/dispatch task abandon <id> --reason "..."` | Drop task |
| `/dispatch step <step-name>` | Run single workflow step |
| `/dispatch slack <message>` | Send to #dispatch |
| `/dispatch optimus` | Force Optimus run |
| `/dispatch optimus --period=week` | Optimus across current week |
| `/dispatch review day` | Daily summary report |
| `/dispatch review week` | Weekly summary report |
| `/dispatch review month` | Monthly summary report |
| `/dispatch cron generate` | Generate cron config |
| `/dispatch cron approve <id>` | Approve a cron entry |
| `/dispatch scaffold` | Generate full directory structure |
| `/dispatch config` | Open workflow.yaml |

## Automatic Task Tracking

ANY work on a Jira ticket MUST be tracked as a dispatch task. This is not
optional — untracked work is invisible to Optimus, carry-forward, and EOD
summaries.

**Rule:** When the operator mentions a Jira ticket in the context of doing
work (investigating, implementing, reviewing, etc.), immediately run:

```bash
python scripts/state_store.py create_task <JIRA-ID> --title "<summary>" --status IN_PROGRESS
```

Or invoke `/dispatch task start <JIRA-ID>` if running within a dispatch session.

This applies to:
- Investigation work (`/dispatch investigate DSP-XXXX`)
- Implementation work on any ticket
- MR reviews tied to a specific ticket
- Any operator request that references a Jira ID

**At completion**, close the task:
```bash
/dispatch task close <JIRA-ID>
```

Or defer if not finished:
```bash
/dispatch task defer <JIRA-ID>
```

Tasks left IN_PROGRESS at EOD are automatically carried forward to the
next morning session.

## Knowledge Capture

When the operator provides or you discover an operational fact during any
work, record it immediately:

```bash
python scripts/state_store.py knowledge record \
  --category <category> --key <key> --value <value> \
  --ticket <JIRA-ID> --confidence <observed|operator_confirmed>
```

Categories: `environment`, `secret`, `repo_relationship`, `pattern`,
`decision`, `deployment`, `tooling`, `naming_convention`.

Examples of facts to capture:
- AWS profile → account ID mappings
- KUBECONFIG paths per environment
- Secret names and ARNs
- Cross-repo dependencies discovered during investigation
- Design decisions and their rationale
- Tooling preferences (e.g., SSH vs HTTPS for git)

## Git Conventions

All repo operations MUST follow these rules:
1. **Always clone via SSH**: `git@gitlab.com:GROUP/PROJECT.git` (never HTTPS)
2. **Branch naming**: `git checkout -b {JIRA-ID}` (e.g., `DSP-6758`)
3. **Clone location**: per-ticket workspace (see "Workspace isolation" below)

## Workspace isolation (HARD RULE)

Each Jira ticket gets its own fully isolated workspace directory. Never
share repo clones across tickets, even when both tickets touch the same
repo, unless the fix is *literally identical* (one MR closes both
tickets).

**Rule**: when starting work on `<JIRA-ID>`, clones MUST live under the
ticket's workspace dir, e.g.:

```
/Users/sethallen/DSP/Interrupt/<period>/<JIRA-ID>/
├── <repo-1>/           # branch <JIRA-ID>
├── <repo-2>/           # branch <JIRA-ID>
└── _artifacts/
```

**Forbidden**: branching `<JIRA-ID-B>` inside a clone that lives under
`<JIRA-ID-A>/`. This pollutes A's workspace with B's changes, makes B
hard to ship without dragging in A's state, and breaks the user's
mental model that "DSP-XXXX/" only contains things relevant to
DSP-XXXX. If you find yourself about to do this, stop and re-clone
into the correct ticket dir.

**The only exception**: if two tickets are being closed by a *single
identical fix* in a *single MR*, one shared clone is acceptable. The
branch name should reference both tickets (e.g.,
`DSP-8088-DSP-8079`). Confirm with the operator before bundling.

**Recovery**: if you discover you've already polluted a ticket's
workspace with another ticket's branch, the cleanup is:
1. `git restore <files>` and `git checkout <original-branch>` in the
   polluted clone
2. `git branch -D <wrong-ticket-branch>` in that clone
3. Fresh `git clone` into the correct ticket workspace
4. Re-apply the change there

## Scripts

| Script | Purpose | Implemented |
|--------|---------|-------------|
| `check_env.py` | Environment validation | Full |
| `dispatch_runner.py` | Workflow execution loop | Full |
| `state_store.py` | SQLite CRUD + schema + task CLI | Full |
| `slack_notifier.py` | Slack MCP + templates | Full |
| `optimus_runner.py` | Optimus subprocess | Partial |
| `log_writer.py` | YAML/MD artifact writer | Full |
| `cron_manager.py` | Cron lifecycle | Full |
| `bottleneck_detector.py` | Condition evaluation | Full |
| `morning_dashboard.py` | Morning dashboard MD renderer | Full |

## Morning Dashboard (canonical format)

Every morning workflow MUST end with a render of the structured dashboard to
`~/.zsh/dispatch/dashboards/YYYY-MM-DD.md`. This is the canonical deliverable
of the morning routine — all other artifacts feed into it.

```bash
python scripts/morning_dashboard.py render [--date YYYY-MM-DD] [--output PATH]
```

**Inputs** (produced by earlier workflow steps):
- `~/.zsh/review/YYYY/MM/DD/personal/mr_*/review.md` + `findings.json`
- `~/.zsh/review/YYYY/MM/DD/team/mr_*/review.md` + `findings.json`
- `~/.zsh/jira/exports/mentions_latest.md` **and** `mentions_latest.json` (jira-skill emits both)
- `~/.zsh/dispatch/briefings/YYYY-MM-DD.md` (dispatch-notebook output)
- `dispatch.db` (tasks, knowledge)

**Outputs**:
- `~/.zsh/dispatch/dashboards/YYYY-MM-DD.md` — full structured dashboard
- `~/.zsh/dispatch/dashboards/YYYY-MM-DD.oneline.txt` — one-line Slack summary

**Template**: `templates/reports/morning_dashboard.md.j2` (format version 1.1)

**Sections (fixed order)**:
1. One-line TL;DR summary (Slack-friendly)
2. Top priority callout + notebook-freshness warning
3. Status at a Glance (9 indicators)
4. Recommended Action Queue (ordered by ROI: unreplied mentions → P1 in-progress → critical findings → P1 pending)
5. Active Dispatch Tasks
6. Personal MR Queue
7. Team MR Queue (grouped by REQUEST_CHANGES / COMMENT / APPROVE / UNREVIEWED)
8. Critical & Major Findings (with file:line deep-links via `/-/blob/<branch>/<file>#L<n>`)
9. Jira Escalations (comment-level deep-links via `?focusedCommentId=<id>`)
10. Per-Ticket Rollup (ticket → dispatch status + MRs + findings + latest mention)
11. SLA Watchlist (unreplied @mentions, idle tasks, stale P1/P2 PENDING)
12. Sequencing & Cross-Ticket Risks (from notebook briefing)
13. Since Yesterday (knowledge entries from last 24h)
14. Artifacts (paths to all source files)
15. System Health

**SLA thresholds** (constants in `morning_dashboard.py`):
- `SLA_TASK_IDLE_DAYS = 7` — IN_PROGRESS tasks idle this long surface in SLA Watchlist
- `SLA_MENTION_STALE_HOURS = 48` — @mentions older than this count as unreplied
- `NOTEBOOK_STALE_HOURS = 72` — briefings citing older sources trigger a warning

**Do not deviate from this format.** The dashboard is wired into the workflow
as step `morning_dashboard_render` and is the single source of truth for
end-of-morning Slack cards, phone glances, and downstream Optimus analysis.

## References

- `references/workflow-schema.md` — full workflow.yaml documentation
- `references/state-machine.md` — task lifecycle diagram and rules
- `references/slack-templates.md` — template variable reference

## Consumed Artifacts

Dispatch reads frontmatter from artifacts produced by sub-skills:

- **review.md** (producer: gitlab-mr-review) — YAML frontmatter with 24 fields including
  `verdict_critical`, `verdict_major`, `pipeline_status`, `has_conflicts`. Used during
  morning workflow to summarize MR review status.
- **findings.json** (producer: gitlab-mr-review) — per-MR severity list with file/line;
  the dashboard renderer builds `…/-/blob/<branch>/<file>#L<line>` deep-links from these.
- **mentions_latest.md / mentions_latest.json** (producer: jira) — Jira @mention scan;
  the JSON sibling includes `comment_url` (`…/browse/KEY?focusedCommentId=<id>`) for deep
  linking from the dashboard's Jira Escalations section.
- **jira_export** (producer: jira) — Issue export at `~/.zsh/jira/exports/`.
- **update_log.yaml** (producer: dispatch-notebook) — Notebook update status and stats.
- **briefings/YYYY-MM-DD.md** (producer: dispatch-notebook) — morning intelligence
  briefing; renderer extracts the Sequencing / Cross-Ticket Risks subsection and
  computes freshness from cited dates (warning if oldest cited source > 72h).

## Produced Artifacts

- **dashboards/YYYY-MM-DD.md** — canonical morning dashboard (see "Morning Dashboard" above).
- **dashboards/YYYY-MM-DD.oneline.txt** — Slack-card summary.

## Docs

See docs/ for detailed specifications:

- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)
- **Integration contracts**: [docs/integration.md](docs/integration.md)
- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)
- **Quality grades**: [docs/quality.md](docs/quality.md)
- **Workflow hooks**: [docs/workflow.md](docs/workflow.md)
