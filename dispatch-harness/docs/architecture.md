# dispatch-harness Architecture

## Component Map

```
dispatch-harness/
├── scripts/
│   ├── check_env.py          8-check environment validator
│   ├── arch_checker.py        Dependency graph, cycle detection, invocation scanning
│   ├── quality_grader.py      AST-based grading engine, grade change detection
│   ├── telemetry_builder.py   Session aggregation, digest generation
│   ├── grade_reporter.py      [stub] Report formatting
│   └── migrate_skill.py       [stub] docs/ split migration
├── agents/
│   └── entropy-agent.md       Self-contained drift detection agent (claude -p)
├── config/
│   └── harness.yaml           Central config: thresholds, paths, weights
├── docs/                      This directory (self-documenting)
└── references/
    ├── dispatch-changes.md    Checkpoint-resume + telemetry trigger
    ├── optimus-changes.md     Telemetry digest injection
    ├── hook-changes.md        Architecture constraint hook
    ├── migration-plan.md      docs/ split migration order
    └── docs-templates/*.j2    5 Jinja2 templates for /migrate
```

## Runtime State

All runtime artifacts live under `~/.zsh/dispatch/`:

| Path | Owner | Purpose |
|------|-------|---------|
| `contracts/architecture.yaml` | dispatch-harness | Dependency graph + constraint rules |
| `harness/quality-grades.yaml` | quality_grader.py | Per-skill per-component grades |
| `harness/grade-history.yaml` | quality_grader.py | Historical grade snapshots |
| `harness/arch-violations.log` | pre_bash_guard.py | Runtime violation log (append-only) |
| `harness/entropy-reports/` | entropy-agent.md | Monthly entropy audit reports |
| `harness/telemetry/` | telemetry_builder.py | Session telemetry digests for Optimus |

## Data Flow

```
ecosystem.yaml ──┐
registry.yaml ───┤
architecture.yaml┤
SKILL.md files ──┼──> arch_checker.py ──> violations
scripts/*.py ────┤
                 ├──> quality_grader.py ──> quality-grades.yaml
docs/ files ─────┤                          │
                 │                          ├──> grade_reporter.py ──> report
                 │                          └──> beads issues (regressions)
                 │
dispatch.db ─────┼──> telemetry_builder.py ──> telemetry digest ──> Optimus
session files ───┘

entropy-agent.md reads ALL of the above + board state ──> entropy report + beads issues
```

## Internal Dependencies

- All scripts read `config/harness.yaml` for thresholds and paths
- `quality_grader.py` reads ecosystem.yaml to discover skill paths
- `quality_grader.py` reads registry.yaml for contract grading
- `arch_checker.py` reads architecture.yaml (created at init)
- `telemetry_builder.py` reads dispatch.db (may be empty)
- `entropy-agent.md` reads quality-grades.yaml and grade-history.yaml
- No script imports from another script in this skill
- No script imports from other skills (architecture violation by own rules)

## Key Design Decision: No Cross-Skill Imports

dispatch-harness duplicates the AST stub detection logic from beads/board_scanner.py
rather than importing it. Importing across skill boundaries would be an architecture
violation by the very rules this skill enforces.
