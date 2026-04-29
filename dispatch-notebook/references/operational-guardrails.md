# Dispatch Framework -- Operational Guardrails Compendium

This document consolidates the operational guardrails from all five skills in the Dispatch Framework: dispatch, jira, gitlab-mr-review, dispatch-manager, and dispatch-notebook. It serves as the single authoritative reference for what each skill is prohibited from doing, what requires operator confirmation, and how failures and cross-skill boundaries are enforced. Sourced directly from each skill's SKILL.md guardrails block.

---

## 1. Dispatch (`/dispatch`)

### Git Prohibitions
- `git add`, `git commit`, `git push` blocked by hook unless the task has `git_permission: true` in `dispatch.db`
- `git_permission` is per-task, per-day -- never global
- Permission granted only via `/dispatch task git-allow <jira-id>`
- Pre-bash hook (`pre_bash_guard.py`) checks dispatch.db before every git write command

### Read/Write Constraints
- Jira access is READ-ONLY from dispatch. `JIRA_CALLER=dispatch` is always set when invoking the jira skill. Dispatch cannot approve Jira write operations. Write operations require the operator to invoke `/jira` directly.
- GitLab access is READ-ONLY from dispatch. `/mr-review` is invoked in read-only mode. No GitLab comments, approvals, or merges originate from dispatch.
- Optimus is ANALYSIS ONLY. Produces reports and recommendations. Does not modify `workflow.yaml`, `dispatch.db`, or crontab. Operator implements all Optimus recommendations manually.

### Confirmation Requirements
- Cron: no cron entry is installed without explicit `/dispatch cron approve`. All cron jobs tracked in `dispatch.db` with approval timestamp.
- Human gates defined in `workflow.yaml` pause after specified steps for operator confirmation.

### Auth & Failure Handling
- Step failure: log, Slack notify, mark FAILED, continue (unless `blocking: true`)
- Sub-skill failure: record, skip artifact collection, surface clear error
- Slack MCP down: queue messages, flush on reconnect, write fallback log
- DB corruption: integrity check, backup, re-init, recover from filesystem
- After 3 consecutive step failures: auto-disable step

### Cross-Skill Boundaries
- Sets `JIRA_CALLER=dispatch` on every jira invocation, forcing read-only mode
- Invokes `/mr-review` in read-only mode -- no write operations forwarded
- Sub-skill invocations generate handoff context and collect artifacts; dispatch never writes through sub-skills

---

## 2. Jira (`/jira`)

### Git Prohibitions
- Not explicitly listed (jira skill does not interact with git)

### Read/Write Constraints
- Default mode: READ-ONLY. Write operations are the exception, not the feature.
- Prohibited with no exceptions under any invocation mode:
  - `jiratui issues delete` (irreversible)
  - Write ops when `JIRA_CALLER != operator` (cross-skill callers always read-only)
  - Write ops inferred from context without explicit operator instruction
  - Confirmation prompts presented on behalf of a cross-skill caller
  - Writing to or modifying the jiratui config file
  - Caching or logging credentials or API keys

### Confirmation Requirements
- All write operations are operator-direct and confirmed only:
  - `/jira create` -- confirm full field set before POST
  - `/jira update` -- confirm before/after diff before PATCH
  - `/jira comment add` -- confirm full text before submit
  - `/jira comment delete` -- double confirmation required (type the issue key)
- A write is operator-direct if and only if: (1) originates from the human operator, (2) operator explicitly named a write subcommand or unambiguously expressed write intent, (3) operator confirmed via interactive prompt before any API call
- No implied writes. Observations about ticket state, review recommendations, linked issue context from sibling skills never trigger writes. Ambiguity resolves to clarification, never execution.

### Auth & Failure Handling
- `jiratui` non-zero exit: surface full stderr, suggest `--verbose` rerun
- API 401/403: surface token expiry guidance with regeneration URL
- API 429: back off with exponential delay, retry
- Network timeout: surface error, suggest `--no-cache` retry
- JQL parse error: surface Jira's error message, suggest correction

### Cross-Skill Boundaries
- `JIRA_CALLER` environment variable checked at startup
- Unset or `operator`: standard mode (reads + confirmed writes permitted)
- Any other value (`gitlab-mr-review`, `dispatch`): FORCED READ-ONLY MODE
- In forced read-only mode, all write subcommands rejected immediately with `WRITE_BLOCKED_CROSS_SKILL` error. No confirmation prompt presented. Calling skill surfaces the error as-is.
- Credentials never interchanged (GitLab uses `GITLAB_TOKEN`; Jira uses jiratui config)

---

## 3. GitLab MR Review (`/mr-review`)

### Git Prohibitions
- `git add`, `git commit`, `git push` (any variant) -- prohibited, no exceptions
- Committing and pushing changes are operator-only actions

### Read/Write Constraints
- Any write operation to GitLab is prohibited: comments, approvals, edits, merges
- Posting under any identity (user, bot, anonymous) is prohibited
- Permitted git operations: clone, checkout, fetch, diff, log (all read-only)
- Clones target the review output directory, never inside existing repos
- Review branch naming: `<source-branch>-review` (never pushed)

### Confirmation Requirements
- Responding to or resolving MR comments: operator-only
- Approving, merging, or closing MRs: operator-only

### Auth & Failure Handling
- API unavailable: use cache if available, clear error if not
- Cache corrupted: delete and re-fetch with operator confirmation
- Clone fails: document in review.md, continue with API data only
- Rate limit: exponential backoff, surface wait time

### Cross-Skill Boundaries
- Invokes jira skill with `JIRA_CALLER=gitlab-mr-review` to fetch linked issue context
- This is always read-only -- jira enters FORCED READ-ONLY MODE and rejects any write attempt
- No shared library dependency between sibling skills

---

## 4. Dispatch Manager (`/dispatch-manager`)

### Git Prohibitions
- Cannot remove `git add`/`commit`/`push` blocks from any managed skill
- Guardrail integrity enforcement prevents weakening git prohibitions

### Read/Write Constraints
- Manages ONLY skills registered in `config/ecosystem.yaml`. Declines all requests to modify unrelated skills.
- Immutable contract fields cannot be renamed, retyped, or removed. Blocked before confirmation, before backup, before execution.
- Cannot weaken the guardrails of any managed skill:
  - Cannot enable cross-skill Jira writes
  - Cannot remove git add/commit/push blocks
  - Cannot enable Optimus to modify skill files directly
  - Cannot disable DSI compliance checks
- Write operations complete fully or roll back fully. No partial apply (atomicity).

### Confirmation Requirements
- All write operations require operator confirmation (add step, edit step, remove step, add teammate, implement optimus finding, rollback, upgrade, contract update, etc.)
- Self-modification requires double confirmation: operator must type `self-modify`
- Self-modification always backed up and never combined with contract changes
- Skill creation via `/dispatch-manager new skill` always runs DSI validation before registration. FAILs block registration. WARNs require confirmation.

### Auth & Failure Handling
- Managed skill missing: report in status, skip in validation
- Broken symlink: report with fix command
- Registry parse error: surface error, suggest recovery
- DSI validation FAIL: block registration, surface report
- Contract drift: report drift details, suggest resolution
- Backup dir unwritable: block all write operations
- Self-modification error: rollback from pre-modification backup

### Cross-Skill Boundaries
- Scope limited to skills registered in `config/ecosystem.yaml`
- Processing order: leaf-first (jira -> gitlab-mr-review -> dispatch -> dispatch-manager)
- Cannot weaken guardrails of any downstream skill

---

## 5. Dispatch Notebook (`/dispatch-notebook`)

### Git Prohibitions
- `git add`, `git commit`, `git push` are PROHIBITED -- no exceptions

### Read/Write Constraints
- CLI ONLY: all NotebookLM operations use the `nlm` CLI exclusively. The `notebooklm-mcp` MCP server must NEVER be used by this skill.
- Read-only intelligence: NotebookLM is queried for synthesized insight only. It does not make decisions. The agent makes all decisions.
- No live state: never upload files that change faster than daily (dispatch.db, in-progress task files, live MR diffs)
- Source limit: never exceed 47 sources. Prune before upload if needed. Error and abort if still over 47 after prune attempt.
- Source updates are non-destructive: old source deleted only after new one uploads successfully, never the other way around.

### Confirmation Requirements
- `init` and `reset` require explicit operator confirmation
- Source updates do not require confirmation (non-destructive by design)

### Auth & Failure Handling
- Auth failure: never silently skip. Surface error with re-auth instructions. Notify operator via Slack on failed update.
- Auth expired: surface re-auth prompt, abort operation
- Source limit (47): run prune, retry. Abort if still over.
- `nlm` timeout: log, surface to operator. Never silently skip.
- Network error: retry once after 10s, then raise
- Query failure: log error, continue without notebook context
- Briefing stale (>48h): inject warning, suggest update, continue
- Notebook not initialized: prompt `/dispatch-notebook init`
- Source upload failure: log, mark pending in inventory, retry on next update

### Cross-Skill Boundaries
- Integrates with `/dispatch` for morning briefings and EOD updates (two workflow steps)
- Integrates with `/dispatch-manager` for post-registration source pushes, post-upgrade refreshes, post-contract-update registry pushes, post-finding-implementation pushes, and post-rollback pushes
- All pushes from sibling skills are fire-and-forget. On failure: log "notebook sync pending"
- Anti-patterns enforced: never ask NotebookLM to make decisions, never query about live state, never upload sub-daily files

---

## Universal Rules

These guardrails apply across ALL skills in the Dispatch Framework without exception.

### Git Prohibition
Every skill either explicitly prohibits `git add`/`git commit`/`git push` or inherits the prohibition through dispatch's hook-based enforcement. No skill may perform git write operations without per-task, per-day permission granted by the operator via `/dispatch task git-allow`. The dispatch-manager cannot weaken or remove this prohibition for any managed skill.

### Read-Only Cross-Skill Invocations
When one skill invokes another, the invocation is always read-only. The `JIRA_CALLER` protocol enforces this for Jira: any non-operator caller triggers FORCED READ-ONLY MODE. GitLab MR review is invoked in read-only mode by dispatch. No skill can approve or execute writes on behalf of another skill.

### Operator Confirmation for Destructive/Write Operations
All write operations across the framework require explicit operator confirmation before execution. Double confirmation is required for irreversible operations (Jira comment delete, dispatch-manager self-modification). Confirmation prompts are never presented on behalf of a cross-skill caller.

### No Implied Writes
Across all skills, write operations are never inferred from context, observations, or recommendations. Ambiguity always resolves to clarification, never execution.

### Credential Isolation
Each skill sources credentials independently. Jira uses jiratui config. GitLab uses `GITLAB_TOKEN`. NotebookLM uses `nlm` CLI auth. Credentials are never cached, logged, interchanged, or shared between skills.

### Failure Surfacing
No skill silently swallows errors. All failures are surfaced to the operator with actionable context (error details, retry suggestions, auth re-generation URLs). Slack notifications supplement but do not replace direct operator surfacing.

### Optimus Is Advisory Only
Optimus produces analysis, reports, and recommendations. It never modifies skill files, workflow configuration, databases, or crontabs directly. The operator (or dispatch-manager under confirmation) implements all Optimus findings.

### Guardrail Integrity
The dispatch-manager explicitly enforces that no managed skill's guardrails can be weakened. This includes git blocks, cross-skill write blocks, Optimus write blocks, and DSI compliance checks. This meta-guardrail protects the entire framework from guardrail erosion.
