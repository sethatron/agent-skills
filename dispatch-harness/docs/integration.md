# dispatch-harness Integration

## Skills This Skill Reads

dispatch-harness reads every skill in the ecosystem to produce health signals:

| Skill | What Is Read | Purpose |
|-------|-------------|---------|
| dispatch | SKILL.md, scripts/*.py, workflow.yaml, dispatch.db, hooks/ | Grade, telemetry, arch check |
| jira | SKILL.md, scripts/*.py | Grade, arch check |
| gitlab-mr-review | SKILL.md, scripts/*.py | Grade, arch check |
| dispatch-manager | SKILL.md, scripts/*.py, ecosystem.yaml, registry.yaml | Grade, arch check, contracts |
| dispatch-notebook | SKILL.md, scripts/*.py | Grade, arch check |
| beads | SKILL.md, scripts/*.py | Grade, arch check |
| dispatch-harness | SKILL.md, scripts/*.py, docs/ | Self-grade (consistency check) |

## Skills This Skill Calls

| Skill | How Called | Purpose |
|-------|-----------|---------|
| beads | `br create`, `br search`, `br comment`, `br sync` via subprocess | Issue creation for regressions/entropy findings |
| dispatch-manager | Registration via ecosystem.yaml + registry.yaml edits | Skill registration at init |

## Contracts

### Produced: architecture.yaml

Location: `~/.zsh/dispatch/contracts/architecture.yaml`

```yaml
version: '1.0'
maintained_by: dispatch-harness
last_validated: <ISO 8601>
dependency_order:
  - slug: <skill_name>
    calls: [<slugs this skill invokes>]
    called_by: [<slugs that invoke this skill>]
rules:
  - id: no_undeclared_calls
    severity: HIGH
  - id: no_circular_dependencies
    severity: CRITICAL
  - id: max_call_depth
    value: 2
    severity: MEDIUM
```

Consumers: dispatch (pre_bash_guard.py hook), entropy-agent, arch_checker.py

### Produced: quality-grades.yaml

Location: `~/.zsh/dispatch/harness/quality-grades.yaml`

```yaml
generated_at: <ISO 8601>
generated_by: dispatch-harness v1.0.0
skills:
  <slug>:
    overall: <A-F>
    components:
      skill_md: <A-F>
      docs_coverage: <A-F>
      <script_name>: <A-F>
      check_env_py: <A-F>
      contracts: <A-F>
    trend: null | improving | stable | regressing
    beads_issues: [<issue_ids>]
```

Consumers: entropy-agent, grade_reporter.py, dispatch weekly report

### Produced: telemetry digest

Location: `~/.zsh/dispatch/harness/telemetry/YYYY-MM-DD-digest.md`

Markdown with step performance stats, fragility ranking, drift events, context window stats.

Consumer: Optimus agent (injected as first context block)

## Registration in Ecosystem

Entry in `dispatch-manager/config/ecosystem.yaml`:
```yaml
dispatch-harness:
  path: /Users/sethallen/agent-skills/dispatch-harness/
  symlink: ~/.claude/skills/dispatch-harness
  config: config/harness.yaml
  dsi_type: B
  dependencies: [dispatch, beads, dispatch-manager]
  produces: [quality_grades, architecture_check, entropy_report, telemetry_digest]
  consumed_by: [dispatch, dispatch-manager]
```

## Downstream Changes Applied at Init

| Target | Change | Reference |
|--------|--------|-----------|
| dispatch_runner.py | Checkpoint-resume functions | references/dispatch-changes.md |
| optimus.md | Telemetry digest context injection | references/optimus-changes.md |
| pre_bash_guard.py | Architecture constraint check | references/hook-changes.md |
