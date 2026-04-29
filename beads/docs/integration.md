# beads Integration


## Subcommand Details

### /beads init

Initialize the framework board. Creates 5 epics and seeds all known
stub issues from the current ecosystem state. Idempotent: checks existing
issues via `br search` before creating to avoid duplicates.

Steps:
1. Run check_env.py (skip init check since we're initializing)
2. Run board_scanner.py to discover ecosystem state
3. Create the 5 framework epics (if not present)
4. Create child stub issues under each epic (if not present)
5. Create infrastructure improvement issues (if not present)
6. Run `br sync --flush-only`
7. Display board summary

### /beads ready

Show unblocked framework work sorted by priority:
```bash
br ready
```

### /beads status

Board overview with counts by status, priority, and epic:
```bash
br stats
br count --by priority -s open
br epic status
```

### /beads board

Full board grouped by epic:
```bash
br epic status
br list --all --limit 0
```

### /beads audit

Invoke the Beads Auditor agent. The auditor:
1. Scans the ecosystem (reads SKILL.md files, detects stubs)
2. Compares against the current board
3. Creates missing issues, closes implemented stubs, escalates priorities
4. Syncs and produces audit report at ~/.zsh/dispatch/auditor/

### /beads sync

Run br sync --flush-only to export board state to issues.jsonl:
```bash
cd ~/.zsh/dispatch && br sync --flush-only
```

### /beads create <title>

Guided issue creation. Prompts for:
- Type: task, bug, epic
- Priority: P0-P4
- Labels: scope, kind, source (required minimum)
- Parent epic (optional)
- Description

Then runs: `br create '<title>' -t <type> -p <priority> -l '<labels>'`

### /beads close <id>

Close an issue with a required reason:
```bash
br close <id> -r '<reason>'
```

### /beads defer <id>

Defer an issue. Prompts for reason and optional target date:
```bash
br defer <id> -r '<reason>'
```

### /beads show <id>

Show full issue detail:
```bash
br show <id>
```

### /beads find <query>

Full-text search across all issues:
```bash
br search '<query>'
```

### /beads list [filters]

Filtered list — proxies directly to br list with any flags:
```bash
br list [filters]
```


## Label Taxonomy

Labels use namespaced convention: `<namespace>:<value>`

**scope:** dispatch, dispatch-manager, jira, mr-review, notebook, beads, ecosystem, optimus, auditor
**layer:** script, skill-md, config, contracts, agent, workflow, db, hook
**source:** optimus, audit, operator, scaffold
**kind:** stub, bug, improvement, refactor, new-feature, debt, config, docs
**phase:** stub, in-design, in-progress, review, complete
**effort:** xs, small, medium, large

Every issue must have at minimum: one scope:, one kind:, one source: label.
Stub issues also require: one layer: and one phase: label.


## /dispatch Integration

dispatch's interaction with beads is intentionally minimal:

**Morning Boot:** After priority queue, append:
  `Framework board: <n> P0, <n> P1 issues open. /beads ready to review.`
  Implementation: `br count --by priority -s open` — skip silently on failure.

**EOD:** Final step runs `br sync --flush-only`. On failure: log and Slack notify.

**Pre-Commit Hook:** Warn if `git commit` in ~/.zsh/dispatch/ without prior
`br sync --flush-only` in the current session. Warning only, does not block.


## /dispatch-manager Integration

dispatch-manager is the primary writer to the beads board:

**New Skill Registration:** Create epic + scan for stubs + create stub issues.
**Skill Upgrade:** Close implemented stubs, update phase labels.
**Optimus Finding Implementation:** Close beads issue by external-ref.
**New Optimus Finding:** Create issue (HIGH/CRITICAL only) with external-ref.
**Rollback:** Create bug issue, reopen closed stubs if reverted.
**DSI Validation Failure:** Create bug issue for the violation.


## JSONL Sync Policy

issues.jsonl is version-controlled alongside dispatch framework files.
The EOD workflow runs `br sync --flush-only` automatically.
The pre-bash hook warns on git commit without prior sync.
