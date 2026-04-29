# Ecosystem Map

## Dependency Graph

```
dispatch-manager (meta)
  ├── dispatch (orchestrator)
  │     ├── jira (data source)
  │     └── gitlab-mr-review (data source)
  │           └── jira (linked issue context)
  └── [extended skills]
```

## Skill Roles

| Skill | DSI Type | Role | Invokes | Produces |
|-------|----------|------|---------|----------|
| jira | B | Data source | — | jira_export |
| gitlab-mr-review | A | Workflow step | jira | review_md |
| dispatch | A | Orchestrator | jira, gitlab-mr-review | session_yaml, task_yaml, optimus_report |
| dispatch-manager | B | Meta-manager | — | changelog, contract_registry_updates |

## Artifact Flow

```
gitlab-mr-review
  └─ writes → ~/.zsh/review/{date}/{branch}/review.md
       └─ read by → dispatch (symlinks into tasks/{jira-id}/mr_review/)

jira
  └─ writes → ~/.zsh/jira/exports/jira_export_{timestamp}.{ext}
       └─ read by → dispatch (referenced in step_log)

dispatch
  └─ writes → ~/.zsh/dispatch/{date}/optimus_report.md
       └─ read by → dispatch-manager (Optimus finding ingestion)
```

## Processing Order

Leaf-first (safe for modifications):
1. jira (no dependents among peers)
2. gitlab-mr-review (depends on jira)
3. dispatch (depends on both)
4. dispatch-manager (depends on all three)

## Contract Boundaries

Three integration contracts bind the ecosystem:

1. **JIRA_CALLER** — env var protocol between callers and jira
2. **review.md frontmatter** — 23-field schema between gitlab-mr-review and dispatch
3. **Artifact paths** — filesystem conventions for artifact exchange

See `contracts/registry.yaml` for authoritative definitions.
See `references/contract-guide.md` for mutation rules.
