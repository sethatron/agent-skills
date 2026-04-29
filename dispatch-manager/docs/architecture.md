# dispatch-manager Architecture


## Contract Registry

Source of truth: `contracts/registry.yaml`. Three core contracts:

1. **jira_caller** — `JIRA_CALLER` env var protocol
2. **review_md_frontmatter** — 23-field schema between mr-review and dispatch
3. **artifact_paths** — filesystem conventions for artifact exchange

Validate with:
```bash
python scripts/contract_validator.py [--verbose] [--json]
```

See `references/contract-guide.md` for mutation rules.

### Contract Mutation Rules

- IMMUTABLE fields can never be renamed, retyped, or removed
- Append new fields to extensible contracts: permitted
- Add new contracts for TYPE A/C skills: permitted
- Remove a contract while producer is registered: blocked


## Idempotency

Read operations (`status`, `validate`, `contracts`, `diff`) are fully
idempotent. Write operations are NOT idempotent — they create backups,
bump versions, and write changelog entries on each invocation.
