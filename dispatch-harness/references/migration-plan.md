# docs/ Split Migration Plan

## Target Format

Every SKILL.md after migration:

```yaml
---
name: <skill>
version: "<semver>"
dsi_type: "<A|B|C>"
description: >-
  <natural language triggers>
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
  workflow: docs/workflow.md  # TYPE A and C only
---

<GUARDRAILS BLOCK>

## Role
<2-3 sentences>

## Triggers / Subcommands
<table>

## Docs
<pointers to docs/ files>
```

Target: under 120 lines. Hard limit: 200 lines.

## Required docs/ Files

| File | Content |
|------|---------|
| `architecture.md` | Component map, data flow, state model, internal deps |
| `integration.md` | Cross-skill calls, contracts, producers/consumers |
| `failure-modes.md` | Failure scenarios with root cause and recovery |
| `quality.md` | Current grade per component |
| `workflow.md` | Step definitions (TYPE A/C only) |

## Migration Order

Each migration is operator-triggered. The entropy agent flags unmigrated skills.

| Order | Skill | Rationale | Complexity |
|-------|-------|-----------|------------|
| 1 | dispatch-harness | Reference implementation (already in target format) | Done |
| 2 | dispatch | Largest SKILL.md, most sections to split | Large |
| 3 | dispatch-manager | Complex, many cross-references | Large |
| 4 | dispatch-notebook | Medium size, well-structured | Medium |
| 5 | beads | Medium size | Medium |
| 6 | gitlab-mr-review | Moderate size | Small |
| 7 | jira | Smallest, simplest | Small |

## Per-Skill Migration Process

Run: `/dispatch-harness migrate <skill>`

1. Read existing SKILL.md in full
2. Classify each section: triggers, guardrails, architecture, integration, failure-modes, quality, workflow, or other
3. Present classification to operator for confirmation
4. On confirmation:
   a. Create `docs/` directory if absent
   b. Render each section to appropriate docs/ file via `references/docs-templates/*.j2`
   c. Rewrite SKILL.md in target format with pointers
   d. Run `/dispatch-harness grade <skill>` to verify
5. Operator runs `/dispatch-manager upgrade <skill>` to commit

## Expected Results Per Skill

### dispatch (Order 2)
- Current: ~850 lines
- After: ~100 lines SKILL.md + 5 docs/ files
- Sections moving to docs/: workflow step definitions, Optimus integration, session management, checkpoint-resume, bottleneck detection, priority queue, cron definitions, guard chain

### dispatch-manager (Order 3)
- Current: ~700 lines
- After: ~90 lines SKILL.md + 5 docs/ files
- Sections moving to docs/: DSI spec, contract management, ecosystem discovery, rollback procedures, upgrade protocol, registration protocol

### dispatch-notebook (Order 4)
- Current: ~350 lines
- After: ~80 lines SKILL.md + 5 docs/ files
- Sections moving to docs/: source tier definitions, update sequence, query library, integration points, initialization steps

### beads (Order 5)
- Current: ~340 lines
- After: ~80 lines SKILL.md + 5 docs/ files
- Sections moving to docs/: label taxonomy, epic structure, integration points, auditor invocation

### gitlab-mr-review (Order 6)
- Current: ~250 lines
- After: ~70 lines SKILL.md + 4 docs/ files (no workflow.md -- TYPE A)
- Sections moving to docs/: review phases, frontmatter schema, Jira integration

### jira (Order 7)
- Current: ~200 lines
- After: ~60 lines SKILL.md + 4 docs/ files (no workflow.md -- TYPE B)
- Sections moving to docs/: JQL patterns, caching, JIRA_CALLER behavior
