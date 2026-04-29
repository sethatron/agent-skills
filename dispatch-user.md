# Dispatch Framework — Operator Reference

**Operator:** @zettatron  
**Stack:** /dispatch · /dispatch-manager · /jira · /gitlab-mr-review · /dispatch-notebook

---

## The System at a Glance

The dispatch framework is a Claude Code-based DevOps orchestration platform. Five skills work as a coordinated system, each with a single responsibility:

| Skill | Role | You interact with it when... |
|---|---|---|
| `/dispatch` | Daily workflow orchestrator | Starting your day, managing tasks, running steps |
| `/dispatch-manager` | Ecosystem manager | Creating skills, implementing Optimus findings, rollbacks |
| `/jira` | Jira intelligence layer | Querying issues, exports — read-only by default |
| `/gitlab-mr-review` | MR review engine | Reviewing MRs for yourself or the team |
| `/dispatch-notebook` | NotebookLM integration | Querying framework history, checking notebook health |

**NotebookLM** runs underneath as the long-term memory layer. You rarely invoke it directly — it surfaces automatically at defined workflow moments (morning briefing, bottleneck detection, task start, weekly review).

**Optimus** is the nightly analysis agent. It runs as an isolated subprocess, produces a structured findings report, and never writes to your codebase. Its findings live in dispatch until you act on them via `/dispatch-manager implement optimus`.

---

## The Daily Cycle

### Morning

Start a Claude Code session and run:

```
/dispatch morning
```

This fires the morning workflow in sequence:

1. **NotebookLM briefing loads** — compressed summary of recurring bottlenecks, pending improvements, and the week's priorities injected into context. The priorities section is displayed to you directly.
2. **Your personal MRs reviewed** — any open MRs authored by you are fetched and reviewed.
3. **Team MRs scanned** — team MRs requiring attention are surfaced.
4. **Jira mentions pulled** — any Jira issues mentioning you or your branches.
5. **Bottleneck scan** — dispatch checks for pipeline failures, blocked tasks, overdue items.

After the workflow completes, dispatch presents your priority queue for the day. Review it, adjust if needed, then start working tasks with `/dispatch task start <jira-id>`.

### Workday

Tasks are the unit of work. Each task maps to a Jira issue.

```bash
/dispatch task start ENG-1234          # start a task; TC-01 notebook query fires if tagged
/dispatch task done ENG-1234           # close and log
/dispatch task defer ENG-1234 "reason" # defer with reason (tracked for Optimus)
/dispatch task list                    # all active tasks this session
/dispatch task git-allow ENG-1234      # grant git write permission for this task today
```

When you start a task, dispatch checks the notebook for relevant patterns on that task's tags and shows a brief context block. If no tags match or the query fails, it skips silently.

MR review on demand:

```bash
/mr-review                             # review all your open MRs
/mr-review team                        # review team MRs
/mr-review https://gitlab.com/...      # review a specific MR by URL
/mr-review ENG-1234                    # review MR linked to a Jira issue
/mr-review --force-refresh             # bypass 6-hour cache and re-fetch
```

Jira on demand:

```bash
/jira ENG-1234                         # fetch issue detail
/jira search "label:platform sprint:active"
/jira export ENG-1234 --format md      # export to markdown
/jira export ENG-1234 --format csv
```

> Jira write operations (create, comment, update) are operator-direct only. You must explicitly state the intent and confirm. Cross-skill calls from dispatch or MR review are always read-only.

### End of Day

```
/dispatch eod
```

This fires the EOD workflow:

1. Closes or defers any in-progress tasks with prompts.
2. Generates the EOD session summary.
3. **Optimus runs** — nightly analysis of the full session: tasks, MRs, bottlenecks, patterns.
4. **Notebook updates** — Optimus report and session data pushed to NotebookLM.
5. **Morning briefing generated** — five NotebookLM queries run and cached for tomorrow.
6. Slack summary posted to `#dispatch`.

You do not need to stay in the session while EOD runs. Optimus and the notebook update run as background steps.

---

## Bottleneck Alerts

When the bottleneck scan detects a **CRITICAL** or **HIGH** severity item, it shows:

```
[BOTTLENECK] Pipeline failing on main for >2 hours
[NOTEBOOK] Prior resolution: This pattern appeared 2026-03-14 and 2026-03-22.
           Both were resolved by rerunning the affected job after a runner
           cache flush. Resolution took ~25 minutes each time.
[NOTEBOOK] Prevention: Optimus recommended pinning the runner image version
           in .gitlab-ci.yml (finding ENG-F-014, PENDING).
```

The notebook context is pulled from the 24-hour query cache if available. If NotebookLM is unreachable, the bottleneck alert still shows — the notebook context block is omitted, not the alert.

---

## Weekly Review

```
/dispatch review week
```

Runs before generating `weekly_report.md`. NotebookLM synthesizes the past 7 days of session summaries and Optimus reports first, inserting its synthesis as the opening section of the report. The rest of the report is computed locally from `dispatch.db`.

---

## Ecosystem Management (/dispatch-manager)

This skill manages the framework itself. You use it when you want to evolve the platform, not when you're doing day-to-day DevOps work.

### Adding a New Skill

```
/dispatch-manager new skill
```

Before the interview starts, dispatch-manager queries the notebook for common DSI failures, integration pitfalls, and useful existing patterns. This brief is displayed before you answer Phase 1 questions. The interview then walks you through a 6-phase guided process that produces a full specification, runs `/skill-creator`, validates DSI compliance, registers the skill, and integrates it into `workflow.yaml`.

### Implementing an Optimus Finding

```
/dispatch-manager optimus list              # see all pending findings
/dispatch-manager implement optimus <id>   # implement a specific finding
```

Before the implementation plan is confirmed, dispatch-manager pulls notebook context for prior attempts and best practices on that finding's category. You see:

```
[NOTEBOOK] Research -- Finding: ENG-F-014
Prior attempts:  No prior attempts documented for this category.
Best practices:  Optimus report 2026-03-01 recommended pinning at the
                 gitlab-runner level, not in the YAML file.
```

You confirm the plan, then dispatch-manager applies the changes using its 10-step write protocol (dry-run, validate, apply, version bump, symlink verify). After the finding is marked implemented, the resolved findings source in NotebookLM is updated automatically.

### Other ecosystem operations

```
/dispatch-manager validate               # full DSI compliance check on all skills
/dispatch-manager status                 # ecosystem health overview
/dispatch-manager upgrade <skill>        # upgrade a skill (with write protocol)
/dispatch-manager rollback <skill>       # restore prior version from backup
/dispatch-manager contract update        # update integration contracts
/dispatch-manager skill register <path>  # register an existing skill
```

All write operations go through the 10-step protocol. Dry-run output is shown before you confirm.

---

## NotebookLM Layer

The notebook runs in the background. You interact with it directly only to check health, ask ad-hoc questions, or force a refresh.

```bash
/dispatch-notebook status          # source counts, last update, auth status
/dispatch-notebook auth            # check nlm authentication
/dispatch-notebook briefing        # load or regenerate the morning briefing
/dispatch-notebook update          # run full update cycle manually
/dispatch-notebook query "<q>"     # ask the notebook a direct question
/dispatch-notebook sources         # list all sources with tier and age
```

**When to run `/dispatch-notebook update` manually:** if EOD failed mid-run, if you pushed new skill files and want the notebook current before a morning session, or if the morning briefing staleness warning appears.

**When to run `nlm login`:** the notebook update will notify you via Slack if authentication has expired. Re-run `nlm login` in your terminal and then retry `/dispatch-notebook update`. Session duration is ~20 minutes; the skill detects and surfaces expiry.

**What the notebook knows:** every SKILL.md in the ecosystem, the contract registry, the ecosystem map, the DSI specification, the last 20 Optimus reports (30 days), the last 7 days of session summaries and bottleneck records, and the cumulative resolved findings and pattern library.

**What the notebook does not know:** live session state, your current task list, today's open MRs, anything in `dispatch.db`. Never ask it questions about the current moment — ask dispatch instead.

---

## Context Compaction

Claude Code will compact the context window during long sessions. When this happens, dispatch automatically re-injects the morning briefing summary after the compact. Operational state re-hydrates from `dispatch.db`. The session continues normally. You do not need to do anything.

---

## Auth and Maintenance

| Task | Command |
|---|---|
| Check ecosystem health | `/dispatch-manager validate` |
| Check notebook health | `/dispatch-notebook status` |
| Re-authenticate NotebookLM | `nlm login` (in terminal) |
| View dispatch task log | `/dispatch task list` |
| View today's bottlenecks | `/dispatch status` |
| View notebook sources | `/dispatch-notebook sources` |
| Force MR cache refresh | `/mr-review --force-refresh` |
| View Optimus pending findings | `/dispatch-manager optimus list` |

---

## Permissions Model

**Git write access** is off by default for all tasks. Grant it per-task, per-day:

```
/dispatch task git-allow ENG-1234
```

This is logged and resets at session end.

**Jira writes** (create, update, comment) require: operator-direct invocation (not via another skill) + explicit stated intent + confirmation. The prompt will always ask you to confirm before any API call.

**Notebook sources** are updated by the system automatically at EOD. You can push individual files via `/dispatch-notebook push <path>` but the daily update handles everything else.

**Cron jobs** (morning boot 8am, EOD 5pm, Optimus 10pm) are defined in dispatch but require explicit operator approval before activation:

```
/dispatch cron approve <id>
```

---

## Quick Reference — What to Type When

| Situation | Command |
|---|---|
| Start the day | `/dispatch morning` |
| Start a task | `/dispatch task start ENG-1234` |
| Review your MRs | `/mr-review` |
| Review team MRs | `/mr-review team` |
| Look up a Jira issue | `/jira ENG-1234` |
| End the day | `/dispatch eod` |
| Ask the notebook a question | `/dispatch-notebook query "..."` |
| Implement an Optimus finding | `/dispatch-manager implement optimus <id>` |
| Add a new skill to the platform | `/dispatch-manager new skill` |
| Fix a broken skill | `/dispatch-manager rollback <skill>` |
| Check if everything is healthy | `/dispatch-manager validate` |
| Notebook auth expired | `nlm login` (terminal) |

---

## File Locations

```
~/.zsh/dispatch/
├── dispatch.db                         # primary state store
├── workflow.yaml                       # step definitions (edit via dispatch-manager)
├── {YYYY}/{MM}/{DD}/
│   ├── review/                         # MR review artifacts
│   ├── morning_briefing.md             # today's notebook briefing
│   ├── session.yaml                    # session log
│   ├── optimus_report.md               # Optimus nightly findings
│   └── weekly_report.md               # weekly synthesis (Fridays)
├── notebook/
│   ├── source_inventory.yaml           # NotebookLM source tracking
│   ├── update_log.yaml                 # notebook update history
│   └── query_cache/                    # cached NotebookLM responses
└── optimus/
    ├── resolved_findings.md            # cumulative resolved findings
    └── pending_improvements.yaml       # queue for /dispatch-manager

~/.claude/skills/                       # installed skill symlinks
~/.claude/agents/optimus.md             # Optimus agent definition
~/.claude/hooks/                        # PostToolUse and PreToolUse hooks
#dispatch (Slack C0AQC48GL1G)           # notification channel
```