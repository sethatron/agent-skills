---
name: beads
version: "1.0.0"
dsi_type: "B"
description: >-
  Use this skill when the user says "check the framework backlog", "what stubs
  are left", "what's blocking framework work", "show framework issues", "what
  optimus findings are open", "close that framework issue", "what's the
  dispatch board look like", "show me P0 framework issues", "audit the beads
  board", "sync beads", "framework status", "beads status", "beads ready",
  "beads board", "beads audit", "beads sync", "beads init", "create a
  framework issue", "close framework issue", "defer that issue", "find
  framework issues about", "list stubs", or invokes /beads with any
  subcommand.
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
---

+------------------------------------------------------------------------+
| BEADS GUARDRAILS                                                       |
|                                                                        |
| PROJECT DIR: All br commands run from ~/.zsh/dispatch/ only.          |
|   Never run br from a skill subdirectory or from ~/.claude/skills/.   |
|                                                                        |
| NO GIT: br never runs git commands. Always run br sync --flush-only   |
|   before any git commit in the dispatch directory.                     |
|                                                                        |
| LABEL TAXONOMY: All issues created by this skill or the auditor must  |
|   have at minimum: one scope: label, one kind: label, one source:     |
|   label. Stub issues also require layer: and phase: labels.           |
|                                                                        |
| AUDITOR SCOPE: The Beads Auditor reads the ecosystem and updates the  |
|   board. It never modifies skill files, never runs git, and always    |
|   runs br sync --flush-only at the end of each audit.                 |
|                                                                        |
| JIRA SEPARATION: Beads tracks dispatch framework work. Jira tracks    |
|   external project work. Do not create Jira issues for framework      |
|   improvements, and do not create beads issues for client work.       |
|   This skill does NOT invoke /jira or set JIRA_CALLER.               |
|                                                                        |
| GIT: git add / git commit / git push are PROHIBITED -- no exceptions. |
+------------------------------------------------------------------------+

## Environment Pre-Validation

Run `scripts/check_env.py` first on every invocation:

```bash
python scripts/check_env.py [--verbose] [--json] [--skip-init-check]
```

Validates: br on PATH, project directory, .beads/ initialized, br works,
database readable, br version >= 0.1.14.

## Role in the Dispatch Framework

Beads is the dispatch framework's internal project management system.
It is the canonical, version-controlled backlog for all framework work.

**What beads tracks:**
- Every stub script not yet implemented
- Every Optimus finding that becomes a framework improvement
- Every new skill in planning or development
- Every framework bug, refactor, or infrastructure change

**What beads does NOT replace:**
- Jira (external project work for Abacus Insights)
- dispatch.db (live session state)
- Optimus report files (canonical output; beads consumes them)

**What beads replaces:**
- pending_improvements.yaml -> beads issues with source:optimus
- resolved_findings.md -> closed beads issues with closing reason
- Informal stub tracking in comments and conversation

**Relationship to other skills:**
- /dispatch: reads board at morning boot (P0/P1 count), syncs at EOD
- /dispatch-manager: primary writer (creates epics, stub issues, closes on implementation)
- /jira, /gitlab-mr-review: no relationship (different scope)
- /dispatch-notebook: receives resolved findings from closed beads issues

## Subcommands

### Read Operations

| Command | Description |
|---------|-------------|
| `/beads ready` | Unblocked framework work, sorted by priority |
| `/beads status` | Board overview: counts by status, priority, epic |
| `/beads board` | Full board grouped by epic |
| `/beads show <id>` | Full issue detail |
| `/beads find <query>` | Full-text search |
| `/beads list [filters]` | Filtered list (proxies to br list) |

### Write Operations

| Command | Description |
|---------|-------------|
| `/beads init` | Initialize framework board (epics + stub issues) |
| `/beads audit` | Invoke the Beads Auditor agent |
| `/beads sync` | Run br sync --flush-only |
| `/beads create <title>` | Create issue (guided, with label prompts) |
| `/beads close <id>` | Close issue with required reason |
| `/beads defer <id>` | Defer issue to a future date |

## Scripts

| Script | Purpose | Implemented |
|--------|---------|-------------|
| `check_env.py` | Environment validation | Full |
| `board_scanner.py` | Ecosystem scan + stub detection | Full |
| `label_enforcer.py` | Label taxonomy compliance | Stub |
| `sync_runner.py` | br sync wrapper and hooks | Stub |

## References

- `references/label-taxonomy.md` -- printable label reference
- `references/epic-structure.md` -- framework epic definitions and child map
- `references/dispatch-changes.md` -- required changes to /dispatch
- `references/dispatch-manager-changes.md` -- required changes to /dispatch-manager

## Docs

See docs/ for detailed specifications:

- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)
- **Integration contracts**: [docs/integration.md](docs/integration.md)
- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)
- **Quality grades**: [docs/quality.md](docs/quality.md)
