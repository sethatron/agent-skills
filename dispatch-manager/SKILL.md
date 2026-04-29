---
name: dispatch-manager
version: "1.0.0"
dsi_type: "A"
description: >-
  Use this skill when the user wants to modify, extend, debug, or maintain the
  dispatch skill ecosystem. Trigger on: "add a new step to dispatch", "update
  my team roster", "add [name] to the review team", "remove [name] from the
  team", "implement this Optimus finding", "roll back the jira skill", "what
  version is the dispatch skill", "validate the skill contracts", "show me
  what changed in dispatch", "add a new bottleneck rule", "extend the
  workflow", "the dispatch skill is broken, help me fix it", "create a new
  dispatch skill", "build a skill that works with dispatch", "add a new skill
  to the framework", "I want to create a skill that runs as a dispatch step",
  "is this skill dispatch-compatible", "check if my skill will work with
  dispatch", "register this skill with dispatch", "make this skill
  dispatch-aware", "dispatch-manager status", "dispatch-manager validate",
  "dispatch-manager diff", "dispatch-manager contracts", "what should I do
  next with Optimus findings", "add a teammate", "remove a teammate", "show
  the ecosystem". Also trigger on /dispatch-manager with any subcommand.
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
  workflow: docs/workflow.md
---

┌────────────────────── DISPATCH-MANAGER GUARDRAILS ──────────────────────────┐
│  SCOPE                                                                       │
│    Manages ONLY skills registered in config/ecosystem.yaml.                  │
│    Declines all requests to modify unrelated skills.                         │
│                                                                              │
│  CONTRACTS                                                                   │
│    Immutable contract fields cannot be renamed, retyped, or removed.         │
│    Blocked before confirmation, before backup, before execution.             │
│                                                                              │
│  GUARDRAIL INTEGRITY                                                         │
│    Cannot weaken the guardrails of any managed skill:                        │
│      - Cannot enable cross-skill Jira writes                                 │
│      - Cannot remove git add/commit/push blocks                              │
│      - Cannot enable Optimus to modify skill files directly                  │
│      - Cannot disable DSI compliance checks                                  │
│                                                                              │
│  ATOMICITY                                                                   │
│    Write operations complete fully or roll back fully. No partial apply.     │
│                                                                              │
│  SELF-MODIFICATION                                                           │
│    Double confirmation required (type 'self-modify').                        │
│    Always backed up. Never combined with contract changes.                   │
│                                                                              │
│  SKILL CREATION                                                              │
│    /dispatch-manager new skill always runs DSI validation before             │
│    registration. FAILs block registration. WARNs require confirmation.       │
└──────────────────────────────────────────────────────────────────────────────┘

## Environment Pre-Validation

Run `scripts/check_env.py` first on every invocation:

```bash
python scripts/check_env.py [--verbose] [--json] [--fix]
```

Validates: Python 3.10+, packages, managed skill paths, symlinks,
registry.yaml, ecosystem.yaml, dispatch.db, optimus dir, backups dir, git.

## Subcommands

### Read Operations (no confirmation required)

| Command | Description |
|---------|-------------|
| `/dispatch-manager status` | Ecosystem health and version summary |
| `/dispatch-manager validate` | Verify all integration contracts |
| `/dispatch-manager diff [--skill <n>]` | Uncommitted changes across skills |
| `/dispatch-manager changelog [--skill <n>]` | Modification history |
| `/dispatch-manager contracts` | Display the live contract registry |
| `/dispatch-manager log [--skill <n>]` | Modification history |
| `/dispatch-manager optimus list` | Pending Optimus findings |
| `/dispatch-manager skill validate <path>` | DSI compliance check |
| `/dispatch-manager test <skill> <invocation>` | Dry-run trigger test |

### Write Operations (operator confirmation required)

| Command | Description |
|---------|-------------|
| `/dispatch-manager new skill` | Guided dispatch-compatible skill creation |
| `/dispatch-manager skill register <path>` | Add existing skill to ecosystem |
| `/dispatch-manager skill integrate <name>` | Wire skill as dispatch step |
| `/dispatch-manager add step <spec>` | Add workflow.yaml step |
| `/dispatch-manager edit step <id> <changes>` | Modify workflow step |
| `/dispatch-manager remove step <id>` | Remove workflow step |
| `/dispatch-manager add teammate <username>` | Add to review team roster |
| `/dispatch-manager remove teammate <username>` | Remove from roster |
| `/dispatch-manager add bottleneck <spec>` | Add bottleneck rule |
| `/dispatch-manager add notification <template>` | Add Slack template |
| `/dispatch-manager edit config <skill> <key> <val>` | Edit config value |
| `/dispatch-manager implement optimus <id>` | Implement Optimus finding |
| `/dispatch-manager rollback <skill> [--to <ver>]` | Rollback skill version |
| `/dispatch-manager upgrade <skill>` | Upgrade skill version |
| `/dispatch-manager contract update <name>` | Update contract entry |

## Scripts

| Script | Purpose | Implemented |
|--------|---------|-------------|
| `check_env.py` | Environment validation | Full |
| `dsi_validator.py` | DSI compliance checker | Full |
| `contract_validator.py` | Contract assertions | Full |
| `skill_author.py` | Guided skill creation | Stub |
| `ecosystem_map.py` | Ecosystem CRUD | Stub |
| `change_manager.py` | Ten-step write protocol | Stub |
| `backup_manager.py` | Backup/restore/prune | Stub |
| `changelog_writer.py` | Structured changelog | Stub |
| `optimus_manager.py` | Finding lifecycle | Stub |
| `version_manager.py` | Semver management | Stub |

## References

- `references/dsi-guide.md` — DSI requirements with examples and worked example
- `references/recovery.md` — manual recovery procedures
- `references/ecosystem-map.md` — dependency graph and artifact flow
- `references/contract-guide.md` — registry.yaml schema and mutation rules
- `dsi/checklist.yaml` — machine-readable DSI requirements
- `dsi/templates/` — Jinja2 templates for skill generation

## Docs

See docs/ for detailed specifications:

- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)
- **Integration contracts**: [docs/integration.md](docs/integration.md)
- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)
- **Quality grades**: [docs/quality.md](docs/quality.md)
- **Workflow hooks**: [docs/workflow.md](docs/workflow.md)
