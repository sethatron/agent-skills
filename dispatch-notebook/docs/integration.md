# dispatch-notebook Integration


## Notebook Structure

One dedicated notebook: **Dispatch Framework Intelligence** (alias: `dispatch`).
ID stored at `~/.zsh/dispatch/notebook/notebook_id`.
Single-notebook design is intentional: cross-document synthesis is the value.

### Source Tiers

**TIER 1 — Framework Core** (permanent, hash-based update) Max: 15

  [CORE] dispatch SKILL.md, jira SKILL.md, gitlab-mr-review SKILL.md,
  dispatch-manager SKILL.md, dispatch-notebook SKILL.md, DSI Specification,
  Contract Registry, Ecosystem Map, Workflow Schema, DSI Guide,
  Contract Guide, Recovery Procedures, Framework Architecture,
  nlm CLI Reference, Dispatch Operational Guardrails

**TIER 2 — Optimus Intelligence** (rotating, 30-day retention) Max: 20

  [OPTIMUS] Daily reports, resolved findings, pattern library,
  pending improvements, knowledge base entries

**TIER 3 — Recent Activity** (rotating, 7-day retention) Max: 12

  [SESSION] Daily summaries, bottleneck reports
  [WEEKLY] Weekly reports (14-day retention)

Total max: 47 sources (3 under the 50-source hard limit).

### Source Inventory

`~/.zsh/dispatch/notebook/source_inventory.yaml` tracks per entry:
nlm_source_id, title, tier, origin_path, content_hash, uploaded_at,
expires_at (null for TIER 1), last_verified.


## Query Library

All queries via: `nlm notebook query dispatch "<question>" --timeout 180`

Responses cached in `~/.zsh/dispatch/notebook/query_cache/<YYYYMMDD>/<id>.md`.
Cache TTL: 20 hours (reused within same calendar day). Pruned after 7 days.

### Query Sets

| Set | File | Queries | Trigger |
|-----|------|---------|---------|
| Morning Briefing | `queries/morning_briefing.yaml` | MB-01..05 | Post-Optimus EOD |
| Skill Creation | `queries/skill_creation.yaml` | SC-01..03 | Before /dispatch-manager new skill |
| Pre-Implementation | `queries/pre_implementation.yaml` | PI-01..02 | Before implementing finding |
| Bottleneck Context | `queries/bottleneck_context.yaml` | BC-01..02 | Post-bottleneck_scan (CRIT/HIGH) |
| Task Context | `queries/task_context.yaml` | TC-01 | /dispatch task start (if tags) |
| Weekly Synthesis | `queries/weekly_synthesis.yaml` | WS-01 | /dispatch review week |

Ad-hoc: `/dispatch-notebook query "<question>"` — raw response with citations.

### Query Response Format (stored frontmatter)

query_id, question, asked_at, notebook_alias, sources_cited


## Integration Points

### /dispatch Integration (Section 7)

See `references/dispatch-changes.md` for complete instructions.

- Morning briefing injected at session start (compressed bullets)
- Bottleneck context appended inline for CRITICAL/HIGH alerts
- Task context displayed before task confirmation (if tags)
- Briefing re-injected after /compact (file read, no live query)
- Weekly synthesis inserted as opening section of weekly report
- EOD notebook_update is the ONLY point where sources are modified

Briefing staleness (>48h or missing): inject warning, suggest update, continue.

### /dispatch-manager Integration (Section 7A)

See `references/dispatch-manager-changes.md` for complete instructions.

- Pre-skill-creation brief (SC queries before interview Phase 1)
- Pre-implementation research (PI queries before finding confirmation)
- Post-registration source push (new skill's SKILL.md to TIER 1)
- Post-upgrade source refresh (hash-based, fire-and-forget)
- Post-contract-update registry push
- Post-finding-implementation resolved_findings push
- Post-rollback SKILL.md push

All pushes are fire-and-forget. On failure: log "notebook sync pending".


## Initialization (/dispatch-notebook init)

13-step guided process:

1. Auth check. Prompt `nlm login` if unauthenticated.
2. Check for existing dispatch alias. Offer to reuse or reset.
3. Create notebook, set alias, write ID to notebook_id file.
4. Create staging/ and query_cache/ directories.
5. Push all TIER 1 sources (render, hash, upload --wait).
6. Push available TIER 2 sources (last 20 Optimus reports).
7. Push available TIER 3 sources (last 7 days of session files).
8. Generate initial morning briefing (all five MB queries).
9. Add both workflow steps via `/dispatch-manager add step`.
10. Apply dispatch changes (references/dispatch-changes.md).
11. Apply dispatch-manager changes (references/dispatch-manager-changes.md).
12. Register with `/dispatch-manager skill register` (TYPE C).
13. Final: `/dispatch-notebook status` and `/dispatch-manager validate`.

Idempotent: hash detection prevents duplicate uploads. Existing alias
not overwritten without confirmation. Existing steps not duplicated.


## Session Boundary and Auth

NotebookLM sessions last ~20 minutes. On auth failure: run
`nlm login --check`, surface re-auth prompt to operator, retry
after successful re-authentication.
