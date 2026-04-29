# Dispatch Framework Architecture

Version: 1.0 | Updated: 2026-04-01 | Source: ecosystem.yaml, SKILL.md files, contract registry

---

## 1. Skill Architecture

The Dispatch Framework is a 5-skill ecosystem where each skill is an independent Claude Code skill with its own SKILL.md, scripts, config, and symlink. Skills communicate exclusively through filesystem artifacts and environment variables -- never through shared memory or direct function calls.

### Skill Inventory

| Skill | DSI Type | Role | Source Path | Symlink |
|-------|----------|------|------------|---------|
| jira | B (on-demand) | Data source | `agent-skills/jira/` | `~/.claude/skills/jira` |
| gitlab-mr-review | A (workflow step) | Data source | `agent-skills/gitlab-mr-review/` | `~/.claude/skills/gitlab-mr-review` |
| dispatch | A (workflow step) | Orchestrator | `agent-skills/dispatch/` | `~/.claude/skills/dispatch` |
| dispatch-manager | B (on-demand) | Meta-manager | `agent-skills/dispatch-manager/` | `~/.claude/skills/dispatch-manager` |
| dispatch-notebook | C (hybrid) | Intelligence layer | `agent-skills/dispatch-notebook/` | `~/.claude/skills/dispatch-notebook` |

### DSI Type Definitions

- **TYPE A (Workflow Step)**: Dispatch calls it during workflow execution. Produces machine-readable artifacts. Requires `references/step-snippet.yaml` and `references/artifact-schema.yaml`.
- **TYPE B (On-Demand Managed)**: Operator invokes directly. dispatch-manager handles versioning and backup. No artifact contract required.
- **TYPE C (Hybrid)**: Satisfies both TYPE A and TYPE B requirements. dispatch-notebook is the only TYPE C skill -- it runs as a workflow step (morning briefing, EOD update) and is also invoked directly for queries.

### Dependency Graph

```
dispatch-manager (B, meta)
  +-- dispatch (A, orchestrator)
  |     +-- jira (B, data source)
  |     +-- gitlab-mr-review (A, data source)
  |           +-- jira (linked issue context)
  +-- jira
  +-- gitlab-mr-review
  +-- [dispatch-notebook (C, intelligence)]
```

Processing order is leaf-first: jira -> gitlab-mr-review -> dispatch -> dispatch-notebook -> dispatch-manager.

---

## 2. Data Flow

Artifacts flow unidirectionally through the dependency graph. Each skill writes to a known filesystem location; downstream skills read from those locations.

### Artifact Pipeline

```
jira
  writes: ~/.zsh/jira/exports/jira_export_{timestamp}.{ext}
    |
    v
gitlab-mr-review
  reads: jira export (linked issue context)
  writes: ~/.zsh/review/{YYYY}/{MM}/{DD}/{branch}/review.md
    |
    v
dispatch
  reads: jira exports (referenced in step_log)
  reads: review.md (symlinked into tasks/{jira-id}/mr_review/)
  writes: ~/.zsh/dispatch/{YYYY}/{MM}/{DD}/session.yaml
  writes: ~/.zsh/dispatch/{YYYY}/{MM}/{DD}/task.yaml
  writes: ~/.zsh/dispatch/{YYYY}/{MM}/{DD}/optimus_report.md
    |
    v
dispatch-notebook
  reads: optimus reports, session files, framework docs
  writes: NotebookLM sources (via nlm CLI)
  writes: ~/.zsh/dispatch/notebook/query_cache/{YYYYMMDD}/{id}.md
    |
    v
dispatch-manager
  reads: ~/.zsh/dispatch/ (all state)
  writes: changelog, contract_registry_updates
```

### Artifact Types

| Artifact | Producer | Consumer(s) | Format | Path Pattern |
|----------|----------|-------------|--------|-------------|
| jira_export | jira | dispatch, gitlab-mr-review | JSON/YAML | `~/.zsh/jira/exports/jira_export_{timestamp}.{ext}` |
| review_md | gitlab-mr-review | dispatch | Markdown + YAML frontmatter | `~/.zsh/review/{YYYY}/{MM}/{DD}/{branch}/review.md` |
| session_yaml | dispatch | dispatch-manager, dispatch-notebook | YAML | `~/.zsh/dispatch/{YYYY}/{MM}/{DD}/session.yaml` |
| task_yaml | dispatch | dispatch-manager | YAML | `~/.zsh/dispatch/{YYYY}/{MM}/{DD}/task.yaml` |
| optimus_report | dispatch (Optimus agent) | dispatch-manager, dispatch-notebook | Markdown | `~/.zsh/dispatch/{YYYY}/{MM}/{DD}/optimus_report.md` |
| morning_briefing | dispatch-notebook | dispatch | Markdown (cached) | `~/.zsh/dispatch/notebook/query_cache/{YYYYMMDD}/MB-*.md` |

---

## 3. State Stores

### Primary State Locations

| Store | Type | Owner | Purpose |
|-------|------|-------|---------|
| `~/.zsh/dispatch/dispatch.db` | SQLite (WAL mode) | dispatch | Tasks, sessions, step_log, bash_log, notifications, optimus_runs, bottlenecks |
| `~/.zsh/dispatch/workflow.yaml` | YAML | dispatch (operator-editable) | Workflow step definitions, human gates, schedule, operator config |
| `~/.zsh/dispatch/notebook/source_inventory.yaml` | YAML | dispatch-notebook | NotebookLM source tracking: IDs, tiers, hashes, expiry dates |
| `dispatch-manager/contracts/registry.yaml` | YAML | dispatch-manager | Integration contract definitions |
| `dispatch-manager/config/ecosystem.yaml` | YAML | dispatch-manager | Skill dependency graph and metadata |
| `dispatch-manager/config/manager.yaml` | YAML | dispatch-manager | Manager operational config (backup retention, validation flags) |
| `dispatch-notebook/config/notebook.yaml` | YAML | dispatch-notebook | Tier limits, retention periods, cache TTL |

### Filesystem Directory Structure

```
~/.zsh/dispatch/
+-- dispatch.db                          (SQLite, WAL)
+-- workflow.yaml                        (workflow definition)
+-- cron/                                (cron configs)
+-- optimus/                             (Optimus knowledge base)
|   +-- knowledge.md
|   +-- resolved_findings.md
|   +-- pattern_library.yaml
|   +-- pending_improvements.yaml
+-- notebook/                            (NotebookLM state)
|   +-- notebook_id                      (NotebookLM notebook ID)
|   +-- source_inventory.yaml
|   +-- query_cache/{YYYYMMDD}/{id}.md
+-- {YYYY}/{MM}/{DD}/                    (daily artifacts)
    +-- session.yaml
    +-- task.yaml
    +-- carry_forward.yaml
    +-- bottlenecks.yaml
    +-- optimus_brief.md
    +-- optimus_report.md
    +-- slack_log.yaml
    +-- tasks/{jira-id}/
        +-- task_log.md
        +-- bash_commands.log
        +-- file_changes.log
        +-- mr_review/                   (symlinks to review.md)
```

### dispatch.db Schema (Tables)

tasks, sessions, step_log, bash_log, notifications, optimus_runs, bottlenecks. Schema managed by `scripts/state_store.py`. Human-readable artifacts derived from DB and written to the dated directory structure.

---

## 4. Integration Contracts

All cross-skill communication is governed by contracts registered in `dispatch-manager/contracts/registry.yaml`. Three contracts bind the core ecosystem; additional contracts are appended when TYPE A/C skills are registered.

### Contract Registry

| Contract ID | Type | Producer | Consumer(s) | Mechanism |
|-------------|------|----------|-------------|-----------|
| jira_caller | Env var protocol | gitlab-mr-review, dispatch | jira | `JIRA_CALLER` environment variable |
| review_md_frontmatter | Schema contract | gitlab-mr-review | dispatch | 23-field YAML frontmatter in review.md |
| artifact_paths | Filesystem convention | jira, gitlab-mr-review, dispatch | dispatch, dispatch-manager | Directory path patterns |
| notebook_artifact | Artifact frontmatter | dispatch-notebook | dispatch | Standard 5-field artifact schema + custom fields |

### jira_caller Contract

- Variable: `JIRA_CALLER`
- Sentinel (operator): `"operator"` (unset or direct invocation)
- Known callers: `gitlab-mr-review`, `dispatch`
- When set: FORCED_READ_ONLY_MODE on jira skill
- When unset: standard mode with deprecation warning
- Error on write attempt: `WRITE_BLOCKED_CROSS_SKILL`

### review_md_frontmatter Contract

23 immutable fields in the YAML frontmatter of every review.md:

mr_id, mr_iid, mr_url, project, title, author, source_branch, target_branch, state, pipeline_status, pipeline_url, has_conflicts, approvals_required, approvals_given, approved_by, verdict_critical, verdict_major, verdict_minor, verdict_suggestion, linked_issues, review_timestamp, review_path, previous_review_path, skill_version.

The contract is extensible (new fields may be appended) but existing fields may never be renamed, retyped, or removed.

### artifact_paths Contract

| Path Pattern | Producer | Consumer |
|-------------|----------|----------|
| `~/.zsh/review/{YYYY}/{MM}/{DD}/{branch}/review.md` | gitlab-mr-review | dispatch |
| `~/.zsh/jira/exports/jira_export_{timestamp}.{ext}` | jira | dispatch |
| `~/.zsh/dispatch/` | dispatch | dispatch-manager |

### Contract Mutation Rules

- **Immutable fields** can never be renamed, retyped, or removed.
- **Permitted**: append new fields to extensible contracts, add new contracts for new TYPE A/C skills, add new callers to jira_caller.known_callers.
- **Blocked**: rename/retype/remove any field in any existing contract, remove a contract while its producer is still registered.

---

## 5. DSI Compliance Model

The Dispatch Skill Interface (DSI) is a 10-requirement specification enforced by `scripts/dsi_validator.py`. Every skill in the ecosystem must pass validation against its declared DSI type.

### DSI Requirements

| ID | Requirement | Severity | Applies To |
|----|------------|----------|-----------|
| DSI-01 | `version: "X.Y.Z"` in SKILL.md frontmatter | FAIL | A, B, C |
| DSI-02 | Operational guardrails block in SKILL.md | FAIL | A, B, C |
| DSI-03 | `scripts/check_env.py` exists with `--json` support | FAIL | A, B, C |
| DSI-04 | Caller identification (JIRA_CALLER, etc.) when invoking managed skills | FAIL | A, B, C |
| DSI-05 | Git write operations guarded (dispatch.db check or blanket prohibition) | FAIL | A, B, C |
| DSI-06 | Symlink at `~/.claude/skills/<slug>` | WARN | A, B, C |
| DSI-07 | `references/step-snippet.yaml` with valid step definition | FAIL | A, C |
| DSI-08 | `references/artifact-schema.yaml` with 5 required fields | FAIL | A, C |
| DSI-09 | Idempotency declaration in SKILL.md | WARN | A, B, C |
| DSI-10 | Failure mode documentation | WARN | A, B, C |

FAIL-severity requirements block skill registration. WARN-severity issues are reported but do not block.

### Artifact Schema Required Fields

Every TYPE A/C artifact must include: `skill_name`, `skill_version`, `produced_at` (ISO 8601 UTC), `artifact_path` (absolute), `status` (success | partial | failed).

---

## 6. Workflow Engine

### Daily Lifecycle

```
Morning Boot
  +-- Load carry_forward.yaml (deferred/in-progress from prior day)
  +-- Run workflow steps (defined in workflow.yaml)
  |     +-- morning_briefing_load (dispatch-notebook briefing)
  |     +-- jira_sync (fetch current sprint)
  |     +-- mr_review (scan open MRs)
  |     +-- bottleneck_scan
  |     +-- priority_queue (generate P1-P4 triage)
  +-- Human gates (pause for operator confirmation)
  +-- Task execution (operator works tasks via /dispatch task commands)
  +-- EOD Summary
  |     +-- bottleneck report
  |     +-- task disposition
  |     +-- carry_forward.yaml generation
  +-- Optimus nightly cycle
  |     +-- Receives optimus_brief.md
  |     +-- Produces optimus_report.md
  |     +-- Runs in isolated subprocess (own context window)
  +-- notebook_update (dispatch-notebook EOD step)
        +-- Push updated sources to NotebookLM
        +-- Generate next morning's briefing
```

### Workflow.yaml Structure

Top-level fields: `version`, `operator` (credentials, timezone), `defaults` (git_permission, require_human_gate, slack_notify_on).

Steps are defined as a list under `steps:`. Each step has: `id`, `name`, `skill` (mutually exclusive with `runner`), `args`, `description`, `on_blocker`, `timeout_minutes`, `tags`, `enabled`, `blocking`.

Human gates: `after` (step ID), `message` (prompt text).

Schedule: cron expressions with `approval_required` flag. No cron entry is installed without explicit `/dispatch cron approve`.

### Task State Machine

```
PENDING -> IN_PROGRESS -> BLOCKED -> IN_PROGRESS (unblock)
                       -> IN_REVIEW -> COMPLETE
                       -> DEFERRED
                       -> ABANDONED (requires --reason)
```

All transitions logged to step_log with timestamp. All transitions send Slack notification. DEFERRED/IN_PROGRESS at EOD auto-carried to next business day. COMPLETE triggers Optimus check.

### Bottleneck Detection

- **CRITICAL** (immediate Slack): MR review > 4h, unresponded Jira comment > 2h, stale pipeline failure > 1h
- **HIGH** (next pause): MR 0 reviews > 24h, IN_REVIEW > 8h, blocking Jira ticket
- **MEDIUM** (EOD summary): > 5 outstanding reviews, > 3 WIP tickets, task deferred > 2x

### Optimus Agent

Runs as `claude -p` subprocess with isolated context. Receives `optimus_brief.md`, produces `optimus_report.md`. Maintains persistent knowledge base at `~/.zsh/dispatch/optimus/` (knowledge.md, resolved_findings.md, pattern_library.yaml, pending_improvements.yaml). Optimus produces recommendations only -- it never modifies workflow.yaml, dispatch.db, or crontab.

---

## 7. NotebookLM Layer

dispatch-notebook provides persistent intelligence by maintaining a single NotebookLM notebook ("Dispatch Framework Intelligence", alias: `dispatch`) as a cross-document synthesis engine.

### Architectural Split

- **Claude Code** handles: executing nlm CLI commands, reading live filesystem state, deciding what/when to push, transforming content, routing query responses, source lifecycle, all scripting.
- **NotebookLM** handles: synthesizing patterns across 30+ documents, answering grounded questions with citations, generating summaries that would overwhelm context windows, cross-referencing architecture docs against operational data.

### 3-Tier Source Management

| Tier | Label | Purpose | Retention | Max Sources |
|------|-------|---------|-----------|-------------|
| TIER 1 | Framework Core | SKILL.md files, DSI spec, contracts, schemas, architecture docs | Permanent (hash-based update) | 15 |
| TIER 2 | Optimus Intelligence | Daily Optimus reports, resolved findings, pattern library, pending improvements | 30-day rolling | 20 |
| TIER 3 | Recent Activity | Daily session summaries, bottleneck reports, weekly reports (14-day retention) | 7-day rolling | 12 |

Total maximum: 47 sources (3 under NotebookLM's 50-source hard limit).

### Source Inventory

`~/.zsh/dispatch/notebook/source_inventory.yaml` tracks per source: nlm_source_id, title, tier, origin_path, content_hash (SHA-256), uploaded_at, expires_at (null for TIER 1), last_verified.

Content hash computed before every upload. Hash match = skip upload. This makes all update operations idempotent within a day.

### Source Content Preparation

All sources rendered to annotated prose markdown before upload via `scripts/source_renderer.py`:
- SKILL.md files: verbatim with prepended header (version, path, type)
- YAML files: annotated markdown with field explanations
- Optimus reports: as-is with normalized header (period, counts)
- Session summaries: prose narrative from session.yaml fields

### Update Sequence (9 steps)

1. Auth check (`nlm login --check`). Abort on failure.
2. Inventory reconciliation vs live source list.
3. TIER 2 update: render, hash, replace changed Optimus sources.
4. TIER 3 update: same for last 7 days of session files.
5. TIER 1 update: hash each framework doc, replace if changed.
6. Prune expired sources (expires_at < now).
7. Generate morning briefing (all MB queries).
8. Slack notification.
9. Write entry to update_log.yaml.

### Query Library

Six query sets, each with specific trigger points:

| Set | Queries | Trigger |
|-----|---------|---------|
| Morning Briefing (MB) | MB-01..05 | Post-Optimus EOD |
| Skill Creation (SC) | SC-01..03 | Before new skill interview |
| Pre-Implementation (PI) | PI-01..02 | Before implementing Optimus finding |
| Bottleneck Context (BC) | BC-01..02 | Post-bottleneck_scan (CRIT/HIGH) |
| Task Context (TC) | TC-01 | /dispatch task start (if tags match) |
| Weekly Synthesis (WS) | WS-01 | /dispatch review week |

Responses cached at `~/.zsh/dispatch/notebook/query_cache/{YYYYMMDD}/{id}.md`. Cache TTL: 20 hours. Pruned after 7 days.

### Notebook Configuration

From `dispatch-notebook/config/notebook.yaml`:

| Parameter | Value |
|-----------|-------|
| tier1_days | null (permanent) |
| tier2_days | 30 |
| tier3_days | 7 |
| weekly_report_days | 14 |
| total_max | 47 |
| default_timeout_seconds | 180 |
| cache_hours | 20 |
| staleness_warning_hours | 48 |
| max_context_bullets | 5 |

### Integration Touchpoints

**With /dispatch**: morning briefing injected at session start, bottleneck context appended for CRIT/HIGH alerts, task context on task start, briefing re-injected after /compact, weekly synthesis in weekly report, EOD notebook_update step.

**With /dispatch-manager**: pre-skill-creation brief, pre-implementation research, post-registration SKILL.md push to TIER 1, post-upgrade source refresh, post-contract-update registry push, post-finding-implementation resolved_findings push.

All pushes are fire-and-forget. On failure: log "notebook sync pending", continue.

---

## 8. Guardrail Summary

Every skill enforces operational guardrails declared in a box-drawing block at the top of its SKILL.md (DSI-02). Key cross-cutting guardrails:

| Guardrail | Enforced By | Mechanism |
|-----------|-------------|-----------|
| No unauthorized git writes | dispatch | Per-task git_permission in dispatch.db, pre_bash_guard.py hook |
| Jira read-only from sub-skills | jira | JIRA_CALLER env var triggers FORCED_READ_ONLY_MODE |
| No cron without approval | dispatch | approval_required + approved flags in workflow.yaml |
| Optimus is analysis-only | dispatch | Optimus subprocess has no write access to workflow.yaml or dispatch.db |
| NotebookLM is read-only intelligence | dispatch-notebook | Queries only; Claude Code makes all decisions |
| No live state in notebook | dispatch-notebook | Only files that change at most daily are uploaded |
| Source limit enforcement | dispatch-notebook | Hard cap at 47 sources; prune before upload |
