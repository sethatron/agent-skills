---
name: jira
version: "1.0.0"
dsi_type: "A"
description: >-
  Use this skill whenever the user mentions Jira, ticket IDs (DSP-1234,
  PLAT-567), asks to "look up ticket", "what's the status of", "search Jira",
  "current sprint", "my open issues", "check my tickets", "what's in the
  sprint", "Jira status", "look up KEY", "show my open Jira tickets", "what
  issues are assigned to me", "export Jira issues", or invokes /jira with any
  subcommand. Also trigger on write-intent phrases like "create a ticket",
  "update the status", "move KEY to Done", "add a comment to KEY" — these
  route through operator-direct confirmation (Section 1A). Trigger on natural
  language like "what am I working on?", "what's blocking the sprint?", "what
  did we close last week?", "search for query in Jira".
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
  workflow: docs/workflow.md
---

┌────────────────────────────── OPERATIONAL GUARDRAILS ──────────────────────────────┐
│  DEFAULT MODE: READ-ONLY                                                           │
│    This skill is a read-only Jira intelligence tool by default.                    │
│    Write operations are the exception, not the feature.                            │
│                                                                                    │
│  PROHIBITED — NO EXCEPTIONS, UNDER ANY INVOCATION MODE                            │
│    - jiratui issues delete  (irreversible — use the Jira web UI)                   │
│    - Write ops when JIRA_CALLER != operator (cross-skill = read-only always)       │
│    - Write ops inferred from context without explicit operator instruction          │
│    - Confirmation prompts presented on behalf of a cross-skill caller              │
│    - Writing to or modifying the jiratui config file                               │
│    - Caching or logging credentials or API keys                                    │
│                                                                                    │
│  OPERATOR-DIRECT AND CONFIRMED ONLY (full rules: Section 1A)                       │
│    - /jira create    (confirm full field set before POST)                          │
│    - /jira update    (confirm before/after diff before PATCH)                      │
│    - /jira comment add    (confirm full text before submit)                        │
│    - /jira comment delete  (double confirmation required)                          │
└────────────────────────────────────────────────────────────────────────────────────┘

## Environment Pre-Validation

Run `scripts/check_env.py` first on every invocation. It validates:
1. jiratui installed and on PATH
2. jiratui config exists at `$XDG_CONFIG_HOME/jiratui/config.yaml` or `~/.config/jiratui/config.yaml`
3. Config has required fields: `jira_api_username`, `jira_api_token`, `jira_api_base_url`
4. Jira instance reachable (GET /rest/api/3/myself)
5. API token valid (not 401/403)
6. Python packages: requests, pyyaml, jinja2
7. Cache and export directories writable

```bash
python scripts/check_env.py [--verbose] [--json]
```

## Subcommands

### /jira search <query>

If `<query>` is valid JQL, pass directly. If natural language, translate via
`scripts/jql_translator.py` and surface the translated JQL:
```
[TRANSLATED JQL] project = PROJ AND status = "In Progress" ORDER BY updated DESC
Explanation: In-progress issues in project PROJ, most recently updated first.
Proceed? [Y/n]
```

Results displayed as Markdown table:

| Key | Summary | Status | Assignee | Updated |
|-----|---------|--------|----------|---------|

Max results: `config.max_results_per_query` (default 100). Pagination handled transparently.

### /jira issue <issue-key>

Full issue detail: summary, description (ADF→Markdown), status, priority, assignee,
reporter, labels, components, fix versions, sprint, story points, created, updated, due date.
Plus: linked issues, subtasks, attachments (listed, not downloaded), latest 5 comments.
Acceptance criteria surfaced in a labeled block if present.

Full comments: `/jira issue <key> comments`

### /jira my-issues [--status <status>] [--project <key>]

JQL: `assignee = currentUser() AND status in (<statuses>)`
Uses `config.my_issues_default_status` unless `--status` passed. Groups by status.

### /jira sprint [--project <key>] [--board <n>]

Active sprint for configured/specified board. Issues grouped by status column
(To Do / In Progress / In Review / Done). Story point totals per column.

### /jira users search <query>

Search Jira users by name or email via jiratui.

### /jira open <issue-key>

Opens `https://<base_url>/browse/<issue-key>` in default browser.

### /jira export <jql> [--format md|json|csv] [--output <path>]

Default format: md. Default path: `config.export_default_path`.
Filename: `jira_export_YYYYMMDD_HHMMSS.{ext}`. All pages accumulated before write.
Surfaces path and row count on completion. Written to disk only — not printed.

### /jira mentions [--days N]

Find recent Jira comments where someone @mentioned the operator. Default: 7 days.
Searches by account ID in ADF mention nodes and plain-text references.
Returns a Markdown table with issue, author, date, and comment excerpt.

Invoked automatically by the dispatch `jira_mentions` morning step. Uses a cached
account ID (24h TTL) to avoid repeated `/myself` lookups.

```bash
python scripts/mentions.py --days 7 --format md
python scripts/mentions.py --days 14 --format json --output /tmp/mentions.json
```

### /jira create [WRITE — operator-direct only, Section 1A]

**Required**: `--project`, `--type`, `--summary`
**Optional**: `--description`, `--priority`, `--assignee`, `--labels`, `--epic`,
`--story-points`, `--due-date`

Before creating:
1. Validate `--type` against project's available issue types
2. Validate `--priority` if supplied
3. Validate `--assignee` via user search if supplied
4. Present confirmation:
```
Operation:  create
Target:     PROJ
Change:     Type=Story, Summary="...", Priority=High, Assignee=...
Reversible: Partial (can update, cannot un-create)
Confirm? [Y/n]
```
5. POST /rest/api/3/issue on confirmation
6. Surface created issue key and URL
7. Invalidate cache for project

### /jira update <issue-key> [WRITE — operator-direct only, Section 1A]

At least one flag required: `--status`, `--assignee`, `--summary`, `--labels`, `--priority`

- `--status`: Fetch transitions, validate target is reachable from current state
- `--assignee`: Validate user exists
- `--labels`: Display current labels, confirm replacement (not append)

All updates require before/after confirmation summary.

### /jira comment add <issue-key> <text> [WRITE — operator-direct only, Section 1A]

```
Posting comment to PLAT-1234:
"<text>"
Confirm? [Y/n]
```
Surfaces comment ID on success.

### /jira comment delete <issue-key> <comment-id> [WRITE — operator-direct only, Section 1A]

**Double confirmation required**:
```
Are you sure you want to delete comment <id> from <key>? [y/N]
Type the issue key to confirm deletion: <operator types key>
```
Irreversible — this guardrail is non-negotiable.

## References

- `references/jiratui-docs/` — Cloned jiratui docs (fetched at first run if absent)
- `tests/fixtures/` — Mock API responses for testing

## Cross-Skill Error Response

When `JIRA_CALLER` is set to any value other than `operator`, all write subcommands
are rejected with:

```json
{
  "error": "WRITE_BLOCKED_CROSS_SKILL",
  "subcommand": "<attempted subcommand>",
  "caller": "<JIRA_CALLER value>",
  "message": "Write operations require direct operator invocation."
}
```

Known callers: `dispatch`, `gitlab-mr-review`. Both enter FORCED READ-ONLY MODE.

## Docs

See docs/ for detailed specifications:

- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)
- **Integration contracts**: [docs/integration.md](docs/integration.md)
- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)
- **Quality grades**: [docs/quality.md](docs/quality.md)
- **Workflow hooks**: [docs/workflow.md](docs/workflow.md)
