---
name: dispatch-harness
version: "1.0.0"
dsi_type: "B"
description: >-
  Use this skill when the user says "check the framework health", "run the
  harness audit", "what is the quality grade for dispatch", "are there any
  architecture violations", "generate the telemetry digest", "run the entropy
  agent", "migrate dispatch to docs format", "what components are below grade B",
  "harness status", "framework quality report", "harness grade", "harness arch",
  "harness entropy", "harness telemetry", "harness enforce", "harness migrate",
  or invokes /dispatch-harness with any subcommand.
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
  workflow: docs/workflow.md
---

+------------------------------------------------------------------------+
| DISPATCH-HARNESS GUARDRAILS                                            |
|                                                                        |
| SUPERVISORY ONLY: This skill reads the ecosystem and produces health  |
|   signals. It does not execute workflow steps, manage skill versions, |
|   or modify skill files directly. All writes route through            |
|   /dispatch-manager.                                                  |
|                                                                        |
| GRADE REGRESSIONS: A grade going down is always a P0/P1 beads bug.   |
|   Never suppress a regression without creating a tracking issue.      |
|                                                                        |
| ARCH VIOLATIONS: Violations are warnings, not blockers. The pre-bash  |
|   hook logs and warns; it does not prevent the invocation.           |
|                                                                        |
| ENTROPY AGENT: Monthly cadence, explicit invocation only. Creates    |
|   issues; never closes them. 20-issue cap per audit run.             |
|                                                                        |
| MIGRATION: docs/ split applied per skill, per upgrade cycle. Never   |
|   force-migrate all skills in a single session.                      |
|                                                                        |
| GIT: git add / git commit / git push are PROHIBITED -- no exceptions. |
|                                                                        |
| This skill does NOT invoke /jira or set JIRA_CALLER.                 |
+------------------------------------------------------------------------+

## Environment Pre-Validation

Run `scripts/check_env.py` first on every invocation:

```bash
python scripts/check_env.py [--verbose] [--json] [--skip-validation]
```

## Role

dispatch-harness is the operating system health layer of the dispatch
framework. It answers: Is the framework structurally sound? What is the
quality of each component? Is the framework accumulating structural drift?
All read operations are idempotent. Init is idempotent (architecture.yaml
not overwritten if present, grades always recomputed, beads issues deduplicated).

## Subcommands

### Read Operations (no confirmation required)

| Command | Description |
|---------|-------------|
| `/dispatch-harness status` | Ecosystem health overview |
| `/dispatch-harness grade` | Compute quality grades for all skills |
| `/dispatch-harness grade <skill>` | Grade a single skill |
| `/dispatch-harness arch` | Architecture constraints and violations |
| `/dispatch-harness telemetry` | Generate telemetry digest |
| `/dispatch-harness report` | Combined health report |

### Write Operations (operator confirmation required)

| Command | Description |
|---------|-------------|
| `/dispatch-harness init` | Full initialization |
| `/dispatch-harness migrate <skill>` | Apply docs/ split to a skill |
| `/dispatch-harness entropy` | Invoke the entropy agent |
| `/dispatch-harness enforce` | Write arch violations to beads |

## Docs

See docs/ for detailed specifications:

- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)
- **Integration contracts**: [docs/integration.md](docs/integration.md)
- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)
- **Quality grades**: [docs/quality.md](docs/quality.md)
- **Workflow hooks**: [docs/workflow.md](docs/workflow.md)

## Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `check_env.py` | Environment validation | Full |
| `arch_checker.py` | Architecture constraint checking | Full |
| `quality_grader.py` | Quality grading engine | Full |
| `telemetry_builder.py` | Telemetry digest generation | Full |
| `grade_reporter.py` | Grade report formatting | Stub |
| `migrate_skill.py` | docs/ split migration | Stub |
