# Dispatch Skill Interface (DSI) Guide

## Overview

The DSI is a set of 10 requirements that any skill must satisfy to be
dispatch-framework compatible. Requirements are evaluated by `dsi_validator.py`
against a target skill directory.

## DSI Types

- **TYPE A** — Workflow Step Skill: dispatch calls it as a workflow step.
  Produces machine-readable artifacts. Requires step snippet and artifact schema.
- **TYPE B** — On-Demand Managed Skill: operator calls directly.
  dispatch-manager handles versioning and backup. No artifact contract needed.
- **TYPE C** — Hybrid: both TYPE A and TYPE B. Must satisfy all requirements.

## Requirements

### DSI-01: Version Field (FAIL)
**Types: A, B, C**

SKILL.md frontmatter must contain `version: "X.Y.Z"` (semver format).

Compliant:
```yaml
---
name: my-skill
version: "1.0.0"
description: ...
---
```

Non-compliant:
```yaml
---
name: my-skill
description: ...
---
```

### DSI-02: Operational Guardrails Block (FAIL)
**Types: A, B, C**

SKILL.md body must contain a clearly delimited guardrails block.

Compliant:
```
┌──── MY-SKILL GUARDRAILS ────┐
│  PROHIBITED                  │
│    - Operation X             │
└──────────────────────────────┘
```

Non-compliant: no guardrails section at all.

### DSI-03: Pre-validation Script (FAIL)
**Types: A, B, C**

`scripts/check_env.py` must exist. It must exit non-zero on failure
and support `--json` for machine-readable output.

### DSI-04: Caller Identification (FAIL)
**Types: A, B, C**

If the skill invokes /jira, it must set `JIRA_CALLER=<skill-slug>`.
If it invokes any managed skill, it must follow that skill's caller protocol.
Skills that don't invoke other managed skills pass automatically.

Compliant (dispatch SKILL.md):
```
JIRA_CALLER=dispatch always set when invoking /jira skill
```

### DSI-05: Git Permission Propagation (FAIL)
**Types: A, B, C**

Git write operations (add, commit, push) must be guarded. Two valid approaches:
1. Check dispatch.db for `git_permission: true` on active task
2. Blanket prohibition (like gitlab-mr-review's PROHIBITED block)

Compliant (gitlab-mr-review):
```
PROHIBITED — NO EXCEPTIONS
  - git add / git commit / git push (any variant)
```

### DSI-06: Symlink Convention (WARN)
**Types: A, B, C**

Source at `/Users/sethallen/agent-skills/<slug>/`, symlink at
`~/.claude/skills/<slug>`.

### DSI-07: Workflow Step Snippet (FAIL)
**Types: A, C only (skip for B)**

`references/step-snippet.yaml` must exist and contain a valid workflow.yaml
step definition.

Example:
```yaml
- id: standup_report
  name: "Standup Report"
  skill: /standup-reporter
  args: "generate"
  description: "Generate daily standup report"
  timeout_minutes: 15
  tags: [standup, morning]
  enabled: true
```

### DSI-08: Artifact Frontmatter (FAIL)
**Types: A, C only (skip for B)**

`references/artifact-schema.yaml` must exist and contain at minimum
these required fields: skill_name, skill_version, produced_at,
artifact_path, status.

### DSI-09: Idempotency Declaration (WARN)
**Types: A, B, C**

SKILL.md must state whether invocations are idempotent.

### DSI-10: Failure Mode Documentation (WARN)
**Types: A, B, C**

SKILL.md or a referenced file must document behavior for major failure modes.

---

## Worked Example: standup-reporter (TYPE A)

A fictional skill that generates daily standup reports from dispatch task data
and posts a summary to Slack.

### Phase 1 — Identity
- Slug: `standup-reporter`
- Name: Standup Reporter
- Purpose: Generate daily standup reports from dispatch task history
- Description: Reads dispatch.db task data, generates a Markdown standup
  report, and optionally sends a summary to Slack.

### Phase 2 — Integration Type
- **TYPE A**: dispatch calls it as a workflow step after the morning review.

### Phase 3 — Dependencies
- Invokes /jira? **No** (reads dispatch.db directly)
- Invokes /mr-review? **No**
- Git write ops? **No** (read-only, generates reports)

### Phase 4 — Artifact Contract
- Filename pattern: `standup_{YYYYMMDD_HHMMSS}.md`
- Directory: `~/.zsh/standup/{YYYY}/{MM}/{DD}/`
- Custom fields:
  - `tasks_completed: integer`
  - `tasks_in_progress: integer`
  - `blockers: list[string]`
  - `standup_date: string`

### Phase 5 — Guardrails
- Prohibited: git add/commit/push, modifying dispatch.db, modifying task state
- Operator-only: posting to Slack channels other than #dispatch

### Phase 6 — Triggers
- Primary: `/standup-reporter generate`
- Phrases: "generate standup", "standup report", "what did I do yesterday"
- Pushy: yes

### DSI Validation Result
```
╔══ DSI Compliance Report ═══════════════════════════════════════╗
║  Skill: standup-reporter   Path: .../standup-reporter  Type: A ║
╠════════════════════════════════════════════════════════════════╣
║  [PASS] DSI-01  version field present (v1.0.0)                ║
║  [PASS] DSI-02  OPERATIONAL GUARDRAILS block present           ║
║  [PASS] DSI-03  check_env.py found                            ║
║  [PASS] DSI-04  No managed skill invocations — N/A            ║
║  [PASS] DSI-05  Git write operations prohibited               ║
║  [PASS] DSI-06  Symlink at ~/.claude/skills/standup-reporter   ║
║  [PASS] DSI-07  references/step-snippet.yaml present           ║
║  [PASS] DSI-08  Artifact schema has all required fields        ║
║  [PASS] DSI-09  Idempotency declared                          ║
║  [PASS] DSI-10  Failure modes documented                      ║
╠════════════════════════════════════════════════════════════════╣
║  10 PASS   0 WARN   0 FAIL                                    ║
║  Result:  COMPLIANT                                            ║
╚════════════════════════════════════════════════════════════════╝
```
